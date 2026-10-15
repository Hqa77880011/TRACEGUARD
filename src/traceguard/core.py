from copy import deepcopy


def topological(events, limit):
    ids = {e["id"] for e in events}
    if len(ids) != len(events):
        raise ValueError("Duplicate event IDs")
    if any(not set(e.get("after", [])) <= ids for e in events):
        raise ValueError("Unknown predecessor")
    emitted = 0

    def visit(prefix, remaining):
        nonlocal emitted
        if emitted >= limit:
            return
        if not remaining:
            emitted += 1
            yield prefix
            return
        ready = sorted(
            e["id"]
            for e in events
            if e["id"] in remaining and set(e.get("after", [])) <= set(prefix)
        )
        for identity in ready:
            yield from visit(prefix + [identity], remaining - {identity})

    yield from visit([], ids)


def admissible(workflow, order):
    if len(order) != len(workflow["events"]) or set(order) != {
        e["id"] for e in workflow["events"]
    }:
        return False
    positions = {x: i for i, x in enumerate(order)}
    return all(
        positions[a] < positions[e["id"]]
        for e in workflow["events"]
        for a in e.get("after", [])
    )


def replay(workflow, candidate):
    if not admissible(workflow, candidate["order"]):
        raise ValueError("Schedule violates mandatory order")
    events = {e["id"]: e for e in workflow["events"]}
    state = deepcopy(workflow.get("initial", {}))
    pending = {}
    external = {}
    transitions = []
    errors = []
    now = 0
    ops = candidate["operations"]

    def apply(event):
        nonlocal now
        now += event.get("duration", 0)
        for key, deadline in list(pending.items()):
            if now > deadline:
                errors.append("deadline:" + key)
                transitions.append("expire:" + key)
                del pending[key]
        kind = event["kind"]
        key = event.get("key", "main")
        version = event.get("version", 0)
        if kind == "request":
            pending[key] = now + event["deadline"]
            transitions.append("enable:" + key)
        elif kind == "ack":
            if version < state.get(key + ":version", 0) and not workflow.get(
                "accept_stale_ack", False
            ):
                transitions.append("reject_stale:" + key)
            else:
                if version < state.get(key + ":version", 0):
                    errors.append("stale_discharge:" + key)
                pending.pop(key, None)
                transitions.append("discharge:" + key)
        elif kind == "commit":
            if version < state.get(key + ":version", 0):
                errors.append("version_regression:" + key)
            state[key + ":version"] = version
        elif kind == "action":
            identity = event.get("correlation", event["id"])
            if external.get(identity, 0) and workflow.get("idempotent", True):
                transitions.append("deduplicate:" + identity)
            else:
                external[identity] = external.get(identity, 0) + 1
                if external[identity] > 1:
                    errors.append("duplicate_action:" + identity)
        elif kind == "set":
            state[key] = event["value"]
        elif kind == "assert":
            if state.get(key) != event["value"]:
                errors.append("assert:" + key)
        elif kind != "noop":
            raise ValueError(kind)

    for identity in candidate["order"]:
        selected = [op for op in ops if op["event"] == identity]
        now += sum(op.get("ticks", 0) for op in selected if op["kind"] == "delay")
        if any(op["kind"] == "drop" for op in selected):
            if not events[identity].get("loss_allowed", False):
                raise ValueError("Loss is not permitted for this event")
            continue
        event = deepcopy(events[identity])
        for op in selected:
            if op["kind"] == "stale":
                event["version"] = max(0, event.get("version", 0) - 1)
        apply(event)
        for op in selected:
            if op["kind"] == "duplicate":
                apply(event)
    now = max(now, workflow.get("horizon", now))
    for key, deadline in pending.items():
        if now >= deadline:
            errors.append("deadline:" + key)
            transitions.append("expire:" + key)
    return dict(
        violation=bool(errors),
        errors=sorted(set(errors)),
        transitions=transitions,
        logical_time=now,
        state=state,
        external=external,
    )


def semantic_key(workflow, candidate, generic=False):
    events = {e["id"]: e for e in workflow["events"]}
    positions = {e: i for i, e in enumerate(candidate["order"])}
    dependencies = []
    identities = sorted(events)
    for i, left in enumerate(identities):
        for right in identities[i + 1 :]:
            e, f = events[left], events[right]
            time_sensitive = any(
                x["kind"] in ("request", "ack") or x.get("duration", 0)
                for x in workflow["events"]
            )
            related = (
                e.get("key") == f.get("key")
                or e["kind"] == "action"
                or f["kind"] == "action"
            )
            if (
                (not generic and time_sensitive)
                or related
                or left in f.get("after", [])
                or right in e.get("after", [])
            ):
                dependencies.append((left, right, positions[left] < positions[right]))
    return repr(
        (
            dependencies,
            sorted(
                (op["event"], op["kind"], op.get("ticks", 0))
                for op in candidate["operations"]
            ),
        )
    )


def candidates(workflow, c):
    all_ops = [[]]
    for e in workflow["events"]:
        for kind in e.get("faults", []):
            if kind == "drop" and not e.get("loss_allowed", False):
                continue
            if kind == "delay":
                all_ops.extend(
                    [
                        [dict(event=e["id"], kind=kind, ticks=t)]
                        for t in range(1, c["max_delay"] + 1)
                    ]
                )
            else:
                all_ops.append([dict(event=e["id"], kind=kind)])
    count = 0
    for order in topological(workflow["events"], c["max_candidates"]):
        for ops in all_ops:
            if count >= c["max_candidates"]:
                return
            count += 1
            yield dict(order=order, operations=ops)


def reduce_violation(workflow, candidate):
    result = deepcopy(candidate)
    calls = 0
    changed = True
    while changed:
        changed = False
        for i in range(len(result["operations"])):
            smaller = dict(
                order=result["order"],
                operations=result["operations"][:i] + result["operations"][i + 1 :],
            )
            calls += 1
            if replay(workflow, smaller)["violation"]:
                result = smaller
                changed = True
                break
        if changed:
            continue
        nominal = [e["id"] for e in workflow["events"]]
        for i in range(len(result["order"]) - 1):
            order = result["order"].copy()
            if nominal.index(order[i]) < nominal.index(order[i + 1]):
                continue
            order[i], order[i + 1] = order[i + 1], order[i]
            if not admissible(workflow, order):
                continue
            smaller = dict(order=order, operations=result["operations"])
            calls += 1
            if replay(workflow, smaller)["violation"]:
                result = smaller
                changed = True
                break
    return result, calls

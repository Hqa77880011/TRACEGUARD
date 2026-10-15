import argparse
import time
from pathlib import Path
import numpy as np
from .common import load, save, table, plot
from .core import candidates, replay, semantic_key, reduce_violation, admissible


def prepare(a, c):
    if a.input:
        workflows = load(a.input)
    else:
        workflows = []
        for i in range(c["workflows"]):
            workflows.append(
                dict(
                    id=str(i),
                    initial={"job:version": 1},
                    idempotent=i % 2 == 0,
                    accept_stale_ack=i % 3 == 0,
                    horizon=10,
                    source="generated_frozen_workflow",
                    events=[
                        dict(
                            id="request",
                            kind="request",
                            key="job",
                            deadline=c["deadline"],
                            duration=0,
                            after=[],
                            faults=[],
                        ),
                        dict(
                            id="commit",
                            kind="commit",
                            key="job",
                            version=2,
                            duration=1,
                            after=["request"],
                            faults=[],
                        ),
                        dict(
                            id="ack",
                            kind="ack",
                            key="job",
                            version=2,
                            duration=1,
                            after=["request"],
                            faults=["delay", "stale", "drop"],
                            loss_allowed=True,
                        ),
                        dict(
                            id="action",
                            kind="action",
                            key="job",
                            correlation="payment",
                            duration=1,
                            after=["commit"],
                            faults=["duplicate", "delay"],
                        ),
                        dict(
                            id="log",
                            kind="noop",
                            key="audit",
                            duration=0,
                            after=["request"],
                            faults=[],
                        ),
                    ],
                )
            )
    for w in workflows:
        if not admissible(w, [e["id"] for e in w["events"]]):
            raise ValueError("Stored nominal order must extend the mandatory order")
    save(Path(a.data) / "workflows.json", workflows)


def run(a, c, method):
    rows = []
    failures = []
    rng = np.random.default_rng(c["seed"])
    for workflow in load(Path(a.data) / "workflows.json"):
        start = time.perf_counter()
        corpus = list(candidates(workflow, c))
        if not corpus:
            raise ValueError("No admissible schedules")
        all_classes = {semantic_key(workflow, x) for x in corpus}
        seen = set()
        contract_seen = set()
        transitions = set()
        found = set()
        first = None
        executions = 0
        replay_ok = 0
        trace_lengths = []
        reduction_calls = 0
        nominal = [e["id"] for e in workflow["events"]]
        if method == "random":
            corpus = [x for x in corpus if x["order"] == nominal]
        if method in ("random", "uniform"):
            rng.shuffle(corpus)
        if method == "nominal":
            corpus = [dict(order=nominal, operations=[])]
        while (
            corpus
            and executions < c["budget"]
            and time.perf_counter() - start < c["wall_seconds"]
        ):
            if method == "traceguard":

                def priority(x):
                    novelty = semantic_key(workflow, x) not in contract_seen
                    delays = sum(op.get("ticks", 0) for op in x["operations"])
                    race = sum(
                        op["kind"] in ("duplicate", "stale") for op in x["operations"]
                    )
                    return (novelty, delays + 2 * race, len(x["operations"]))

                index = max(range(len(corpus)), key=lambda i: priority(corpus[i]))
            else:
                index = 0
            candidate = corpus.pop(index)
            key = semantic_key(workflow, candidate, generic=method == "generic_por")
            if method in ("traceguard", "generic_por") and key in seen:
                continue
            verdict = replay(workflow, candidate)
            executions += 1
            seen.add(key)
            contract_seen.add(semantic_key(workflow, candidate))
            transitions.update(verdict["transitions"])
            if verdict["violation"]:
                if first is None:
                    first = executions
                found.update(verdict["errors"])
                reduced, calls = reduce_violation(workflow, candidate)
                reduction_calls += calls
                again = replay(workflow, reduced)
                replay_ok += again["violation"]
                trace_lengths.append(
                    len(reduced["order"])
                    + sum(op["kind"] == "duplicate" for op in reduced["operations"])
                )
                failures.append(
                    dict(workflow=workflow["id"], schedule=reduced, verdict=again)
                )
        elapsed = time.perf_counter() - start
        reference = [replay(workflow, x) for x in candidates(workflow, c)]
        faults = {e for result in reference for e in result["errors"]}
        obligations = {e for result in reference for e in result["transitions"]}
        rows.append(
            dict(
                id=workflow["id"],
                method=method,
                fault_recall=len(found & faults) / len(faults) if faults else None,
                first_execution=first,
                class_coverage=len(contract_seen & all_classes) / len(all_classes),
                obligation_coverage=len(transitions & obligations) / len(obligations)
                if obligations
                else None,
                replay_success=replay_ok / len(trace_lengths)
                if trace_lengths
                else None,
                reduced_trace_events=np.mean(trace_lengths) if trace_lengths else None,
                ci_minutes=elapsed / 60,
                executions=executions,
                reduction_calls=reduction_calls,
                reference_executions=len(reference),
            )
        )
    output = Path(a.output) / method
    table(output / "workflows.csv", rows)
    save(output / "counterexamples.json", failures)
    summary = {
        "method": method,
        **{
            k: float(np.mean([r[k] for r in rows if r[k] is not None]))
            if any(r[k] is not None for r in rows)
            else None
            for k in rows[0]
            if k not in ("id", "method")
        },
    }
    save(output / "metrics.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["prepare", "run", "compare", "plot"])
    p.add_argument("--config", default="configs/default.json")
    p.add_argument("--input")
    p.add_argument("--data", default="data/workflows")
    p.add_argument("--output", default="runs")
    p.add_argument(
        "--method",
        choices=["traceguard", "nominal", "random", "uniform", "generic_por"],
        default="traceguard",
    )
    a = p.parse_args()
    c = load(a.config)
    if a.command == "prepare":
        prepare(a, c)
    elif a.command == "run":
        run(a, c, a.method)
    elif a.command == "compare":
        rows = [
            run(a, c, m)
            for m in ["nominal", "random", "uniform", "generic_por", "traceguard"]
        ]
        save(Path(a.output) / "comparison.json", rows)
        table(Path(a.output) / "comparison.csv", rows)
    else:
        plot(Path(a.output) / "comparison.json", Path(a.output) / "figures")

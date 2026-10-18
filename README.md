# TRACEGUARD

Implementation of contract-guided temporal assurance with deterministic replay, conservative schedule classes and violation-preserving reduction.

## Installation


Use Python 3.11 or newer. Create and activate a virtual environment, then install:

```bash
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or `.venv\Scripts\Activate.ps1` in PowerShell, then install:

```bash
python -m pip install -e .
``` For GPU execution, install matching PyTorch and torchvision builds using the [PyTorch selector](https://pytorch.org/get-started/locally/).


## Frozen workflows

`traceguard prepare --input workflows.json` imports a list of `{id, initial, horizon, events, idempotent, accept_stale_ack}` records. Each event has unique `id`, `kind`, `key`, mandatory predecessors `after`, nonnegative logical `duration`, and permitted `faults`. Kinds are request (with deadline), ack/commit (with version), action (with correlation ID), set/assert (with value), and noop. Faults are delay, duplicate, stale and drop; dropping also requires `loss_allowed=true`. A nominal event list must already extend its mandatory order.

Export recorded [tau-bench](https://github.com/sierra-research/tau-bench) or application workflows into these deterministic state transitions after freezing model/tool outputs. The replay engine deliberately performs no live model/tool calls. Without input, preparation creates a generated request/commit/ack/idempotence workload. This controlled event language implements the temporal acceptance mechanism; task-specific SDK instrumentation is upstream.

```bash
traceguard prepare --data data/workflows
traceguard run --data data/workflows --output runs
traceguard compare --data data/workflows --output runs
traceguard plot --output runs
```

## Search and reduction

The finite corpus combines admissible topological orders with the nominal fault realization or one declared perturbation. `max_candidates` truncates this corpus deterministically and is the explicit evaluation universe. No faults beyond that corpus enter reported recall. Requests create bounded obligations; acks discharge them; late arrivals expire them. Commit regressions, duplicate unguarded external actions and failed assertions are safety violations.

The contract class key preserves all event ordering whenever time can affect an obligation; otherwise only disjoint non-action effects commute. This conservative relation prioritizes correctness over maximal reduction. TRACEGUARD prefers uncovered classes with larger declared delay/race pressure using skeleton metadata, not hidden replay outcomes. `generic_por` uses key/side-effect dependence without deadline refinement. Nominal testing uses the stored default order with no faults. Random perturbation shuffles fault realizations of that same nominal order; uniform sampling shuffles the full admissible-order/fault corpus. Their evaluation universe and violation predicates are shared.

Reduction repeatedly removes faults or restores inverted nominal adjacent order when admissible and violation preserving. It stops only after a complete pass makes no deletion. The result is 1-minimal for those operators; all mandatory events remain. Every reported counterexample is replayed after reduction. Search, replay and reduction wall time are charged to CI cost. `reduction_calls` counts additional replay executions; the configured discovery budget applies to discovery calls. Ground-truth corpus replay for evaluation is counted separately as `reference_executions` and excluded from discovery CI time.

## Metrics

`configs/default.json` controls seed, corpus bound, delay magnitude, discovery executions and wall-clock ceiling. `workflows.csv` reports temporal-fault recall (distinct violation predicate IDs), first-failure executions, class coverage, obligation-transition coverage, replay success, reduced event count and CI minutes. First failure is null when none is found. `counterexamples.json` carries reduced schedules and monitor states. Comparison CSV/JSON and PNG/SVG plots use generated measurements. For larger workflows, corpus truncation limits the scope of coverage; it never implies exhaustive temporal verification.

## Registered compact reproduction setting

Eight finite frozen event workflows, a prespecified 2,000-candidate universe, 200 discovery calls and a 30-second wall ceiling. Recall refers to that declared corpus, including its replayed reference outcomes.

Run from the repository root after installation. The following commands use the registered setting; they are provided for execution and have not been run as part of the source review.

```bash
traceguard prepare --config configs/reproduce.json --data data/reproduce
traceguard compare --config configs/reproduce.json --data data/reproduce --output runs/reproduce
```

This setting needs no external dataset or pretrained weights. Generated inputs and declared fault/shift laws define the finite task; reported quantities retain that provenance.

## Multiple seeds

Run matched configurations with different seeds in separate directories, then aggregate the generated metric files:

```bash
traceguard-report --inputs runs/seed0/metrics.json runs/seed1/metrics.json --output outputs/seeds
```

Use actual metric paths from your runs, including method subdirectories where applicable. Keep dataset, split and experimental condition fixed within a report. Summary CSV/JSON gives per-method arithmetic means and sample standard deviations; a single run has no standard-deviation estimate.

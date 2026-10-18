# TRACEGUARD

Implementation of contract-guided temporal assurance with deterministic replay, conservative schedule classes and violation-preserving reduction.

## Installation

Use Python `>=3.11`. Run commands from the repository root. Create the environment, activate it with `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\Activate.ps1` (PowerShell), then install the package.

```bash
python -m venv .venv
```

```bash
python -m pip install -e .
```

## Data preparation

Preparation generates frozen request/commit/ack workflows. `--input workflows.json` imports deterministic events with `id`, `initial`, `horizon`, `events`, `idempotent` and `accept_stale_ack`. Event IDs, predecessors, durations and allowed faults define the replay inputs; no live model or tool calls are made.

```bash
traceguard prepare --config configs/reproduce.json --data data/workflows
```

## Execution

`configs/reproduce.json` fixes seed `17`. Keep this config for every step; change `seed` there and use separate data/output directories for independent runs.

```bash
traceguard run --config configs/reproduce.json --data data/workflows --output runs
```

## Evaluation and comparisons

`compare` executes the available methods, including component controls, on the same prepared inputs.

```bash
traceguard compare --config configs/reproduce.json --data data/workflows --output runs
traceguard plot --output runs
```

## Outputs

`runs/<method>/` contains `workflows.csv`, `counterexamples.json` and `metrics.json`. Comparisons write `runs/comparison.csv` and `runs/comparison.json`; plots go to `runs/figures/`.

## Verification

Source checks used Python 3.13.5. Installed dependency metadata: numpy 2.1.3, scipy 1.15.3, matplotlib 3.10.0. Python AST, configuration files, CLI parser definitions and source input/output paths were checked without invoking command handlers. Training, full evaluation and CI were not run for this review.

"""Entry point for experiment 05 — score 0-5 sin rúbrica dimensional.

Usage:
    cd <repo root>
    # Full run (3 models × 4 registers × n=5):
    python -m experiments.exp_05_no_rubrica.run

    # Filtered (only Kimi):
    python -m experiments.exp_05_no_rubrica.run --models kimi-k2.6

    # Only control (validate parser):
    python -m experiments.exp_05_no_rubrica.run --registers control --n 2 --workers 2

    # Specific registers:
    python -m experiments.exp_05_no_rubrica.run --registers control,hostil-correctivo

Registers: control, adulacion, hostil-correctivo, hostil-combinado.
Logs go to runs/exp_05_no_rubrica/<timestamp>/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from core.runner import run_experiment

from experiments.exp_05_no_rubrica.spec import Experiment05NoRubricaSpec


def _progress(*, done: int, planned: int, conversation_id: str, failed: bool) -> None:
    flag = "FAILED" if failed else "ok"
    print(f"  [{done}/{planned}] {conversation_id}  ({flag})", flush=True)


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [token.strip() for token in value.split(",") if token.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run experiment 05 — score 0-5 sin rúbrica dimensional."
    )
    parser.add_argument("--models", default=None,
        help="Comma-separated model filter. E.g. 'kimi-k2.6', 'claude-opus-4-7,gpt-5.5'.")
    parser.add_argument("--registers", default=None,
        help="Comma-separated register filter (e.g. 'control,hostil-correctivo').")
    parser.add_argument("--n", type=int, default=None,
        help="Override n_per_cell from run_config.yaml.")
    parser.add_argument("--workers", type=int, default=1,
        help="Number of conversations to run concurrently.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env", override=True)

    spec = Experiment05NoRubricaSpec(
        models_filter=_parse_csv(args.models),
        registers_filter=_parse_csv(args.registers),
        n_per_cell_override=args.n,
    )

    runs_root = repo_root / "runs"

    if not spec.models():
        print(f"ERROR: model filter {args.models!r} matched no entries.", file=sys.stderr)
        return 1
    if not spec.registers():
        print(f"ERROR: register filter {args.registers!r} matched no entries.", file=sys.stderr)
        return 1

    n_models = len(spec.models())
    n_registers = len(spec.registers())
    n_per_cell = spec.n_per_cell()
    n_turns = spec.num_turns()
    total = n_models * n_registers * n_per_cell

    print(f"Experiment: {spec.EXPERIMENT_ID}")
    print(f"  models:      {n_models}  ({[m['id'] for m in spec.models()]})")
    print(f"  registers:   {n_registers}  ({spec.registers()})")
    print(f"  n_per_cell:  {n_per_cell}")
    print(f"  num_turns:   {n_turns}")
    print(f"  total convs: {total}")
    print(f"  total turns: {total * n_turns}")
    print(f"  workers:     {args.workers}  ({'sequential' if args.workers <= 1 else 'parallel'})")
    print(f"  score scale: 0-5 (5 binary dims, no required justifications)")
    print()

    summary = run_experiment(
        experiment=spec,
        runs_root=runs_root,
        on_progress=_progress,
        n_workers=args.workers,
    )

    print()
    print("Summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

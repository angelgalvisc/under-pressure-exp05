"""Apply the LLM judge to all (T0, Tt) pairs of a completed exp_05_rubrica run.

Usage:
    python -m experiments.exp_05_rubrica.judge_runner <run_dir>

If <run_dir> is omitted, the latest run is used.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from core.judge import LLMJudge
from core.logger import JSONLLogger, read_jsonl

from experiments.exp_05_rubrica.spec import Experiment05RubricaSpec


BASELINE_TURN = 0
PRESSURE_TURNS = (1, 2, 3, 4, 5)


def _latest_run_dir(experiment_id: str, runs_root: Path) -> Path:
    base = runs_root / experiment_id
    if not base.exists():
        raise FileNotFoundError(f"No runs found at {base}")
    candidates = sorted([p for p in base.iterdir() if p.is_dir()])
    if not candidates:
        raise FileNotFoundError(f"No run directories under {base}")
    return candidates[-1]


def _group_turns_by_conversation(turns: list[dict]) -> dict[str, dict[int, dict]]:
    grouped: dict[str, dict[int, dict]] = {}
    for t in turns:
        cid = t["conversation_id"]
        grouped.setdefault(cid, {})[t["turn_idx"]] = t
    return grouped


def _extract_score_and_justification(turn_record: dict) -> tuple:
    parsed = turn_record.get("parsed") or {}
    score = parsed.get("score")
    justification = (
        parsed.get("justificacion_breve")
        or parsed.get("justification")
        or turn_record.get("assistant_response")
        or ""
    )
    return score, justification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "run_dir",
        nargs="?",
        default=None,
        help="Path to runs/<experiment>/<run_id>/. If omitted, use the latest.",
    )
    parser.add_argument(
        "--passes", type=int, default=None,
        help="Override passes_per_pair from run_config.yaml.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env", override=True)

    spec = Experiment05RubricaSpec()
    runs_root = repo_root / "runs"

    run_dir = Path(args.run_dir) if args.run_dir else _latest_run_dir(spec.EXPERIMENT_ID, runs_root)
    if not run_dir.exists():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 1

    print(f"Codifying pairs from {run_dir}")

    # Build judge
    judge_cfg = spec.judge_config
    judge_run_cfg = spec.judge_run_config
    passes = args.passes if args.passes is not None else int(judge_run_cfg.get("passes_per_pair", 2))

    judge = LLMJudge.from_codebook_file(
        judge_model=judge_cfg["id"],
        codebook_path=spec.codebook_path,
        allowed_labels=judge_run_cfg["allowed_labels"],
        prices=spec.prices(),
        temperature=float(judge_run_cfg.get("temperature", 0.3)),
        max_tokens=int(judge_run_cfg.get("max_tokens", 512)),
    )

    # Read turns
    turns = read_jsonl(run_dir / "turns.jsonl")
    if not turns:
        print("No turns found in run.", file=sys.stderr)
        return 1

    grouped = _group_turns_by_conversation(turns)

    logger = JSONLLogger(run_dir)

    total_pairs = 0
    total_calls = 0
    total_cost = 0.0

    for cid, turns_by_idx in grouped.items():
        baseline = turns_by_idx.get(BASELINE_TURN)
        if baseline is None:
            # conversation never reached baseline (likely failed); skip
            continue
        baseline_score, baseline_just = _extract_score_and_justification(baseline)
        if baseline_score is None or not baseline_just:
            # cannot codify without baseline data
            continue

        for t in PRESSURE_TURNS:
            current = turns_by_idx.get(t)
            if current is None:
                continue
            current_score, current_just = _extract_score_and_justification(current)
            if current_score is None or not current_just:
                continue

            pair_record = {
                "conversation_id": cid,
                "model": current["model"],
                "register": current["register"],
                "run_idx": current["run_idx"],
                "baseline_turn": BASELINE_TURN,
                "current_turn": t,
                "baseline_score": baseline_score,
                "baseline_justificacion": baseline_just,
                "current_score": current_score,
                "current_justificacion": current_just,
            }
            logger.log_judge_pair(pair_record)

            for pass_idx in range(passes):
                try:
                    label_record = judge.codify_pair(
                        baseline_score=baseline_score,
                        baseline_justification=baseline_just,
                        current_score=current_score,
                        current_justification=current_just,
                    )
                except Exception as e:
                    logger.log_error(
                        {
                            "phase": "judge",
                            "conversation_id": cid,
                            "current_turn": t,
                            "pass_idx": pass_idx,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        }
                    )
                    continue

                logger.log_judge_label(
                    {
                        "conversation_id": cid,
                        "model": current["model"],
                        "register": current["register"],
                        "run_idx": current["run_idx"],
                        "current_turn": t,
                        "pass_idx": pass_idx,
                        **label_record,
                    }
                )
                total_calls += 1
                total_cost += float(label_record.get("cost_usd", 0.0))
            total_pairs += 1

    print(f"Pairs codified: {total_pairs}")
    print(f"Total judge calls: {total_calls}")
    print(f"Approx cost: ${total_cost:.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())

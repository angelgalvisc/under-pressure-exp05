"""Generic experiment runner.

This module knows nothing about Heidegger, scores, registers or tones.
It orchestrates a generic loop:

    for each model in experiment.models()
      for each register in experiment.registers()
        for each run_idx in 0..n_per_cell-1
          for each turn_idx in 0..num_turns-1
              prompt = experiment.build_user_prompt(register, run_idx, turn_idx, history)
              response = chat(model, history + prompt)
              log turn

Conversations are independent of each other; turns within a conversation are
strictly sequential (each turn depends on the previous response). When
n_workers > 1, the runner executes multiple conversations concurrently
using a thread pool. Each worker still runs its own conversation's turns
sequentially. The exact number of turns is supplied by the experiment spec.

Each experiment supplies an ExperimentSpec implementing the protocol
defined below. Adding a new experiment means writing a new spec, not
touching this file.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Optional, Protocol, runtime_checkable

from .logger import JSONLLogger
from .manifest import create_manifest, write_manifest
from .parser import is_refusal, parse_score_json
from .providers import chat


@runtime_checkable
class ExperimentSpec(Protocol):
    """Minimal interface every experiment must implement.

    An experiment is anything with these attributes/methods. It does not
    need to subclass anything; duck typing is enough.
    """

    EXPERIMENT_ID: str

    def load_config(self) -> dict: ...
    def models(self) -> list[dict]: ...                  # each: {"id": str, "provider": str, ...}
    def registers(self) -> list[str]: ...
    def num_turns(self) -> int: ...
    def n_per_cell(self) -> int: ...
    def temperature(self) -> float: ...
    def max_tokens(self) -> int: ...
    def system_prompt(self) -> Optional[str]: ...
    def prices(self) -> dict: ...
    def data_files(self) -> list[Path]: ...
    def build_user_prompt(
        self, register: str, run_idx: int, turn_idx: int, history: list[dict]
    ) -> str: ...


def _reasoning_kwargs_for_provider(provider: Optional[str], reasoning_cfg: dict) -> dict:
    """Pick the reasoning knobs that apply to a given provider.

    `reasoning_cfg` is a free-form dict from run_config.yaml with provider-keyed
    sub-dicts. We pluck only what `chat()` knows how to use.
    """
    if not reasoning_cfg:
        return {}
    out: dict = {}
    anth = reasoning_cfg.get("anthropic") or {}
    oai = reasoning_cfg.get("openai") or {}
    if provider == "anthropic" and anth:
        out["thinking_config"] = anth
    elif provider == "openai" and oai:
        if "effort" in oai:
            out["reasoning_effort"] = oai["effort"]
        if "summary" in oai:
            out["reasoning_summary"] = oai["summary"]
    return out


def _run_one_conversation(
    *,
    model_cfg: dict,
    register: str,
    run_idx: int,
    experiment: ExperimentSpec,
    logger: JSONLLogger,
    temperature: float,
    max_tokens: int,
    system: Optional[str],
    prices: dict,
    reasoning_cfg: dict,
) -> tuple[str, bool]:
    """Execute one conversation (its turns, sequentially). Returns (conversation_id, failed)."""
    model_id = model_cfg["id"]
    provider = model_cfg.get("provider") or _provider_from_id(model_id)
    conversation_id = f"{model_id}__{register}__run{run_idx:03d}"
    history: list[dict] = []
    if system:
        history.append({"role": "system", "content": system})

    reasoning_kwargs = _reasoning_kwargs_for_provider(provider, reasoning_cfg)

    failed = False

    for turn_idx in range(experiment.num_turns()):
        user_prompt = experiment.build_user_prompt(
            register=register, run_idx=run_idx, turn_idx=turn_idx, history=history
        )
        history.append({"role": "user", "content": user_prompt})

        try:
            result = chat(
                model_id=model_id,
                messages=history,
                temperature=temperature,
                max_tokens=max_tokens,
                prices=prices,
                provider=provider,
                **reasoning_kwargs,
            )
        except Exception as e:
            logger.log_error(
                {
                    "conversation_id": conversation_id,
                    "model": model_id,
                    "register": register,
                    "run_idx": run_idx,
                    "turn_idx": turn_idx,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            failed = True
            break

        parsed = parse_score_json(result["text"])
        refusal = is_refusal(result["text"])

        logger.log_turn(
            {
                "conversation_id": conversation_id,
                "model": model_id,
                "register": register,
                "run_idx": run_idx,
                "turn_idx": turn_idx,
                "user_prompt": user_prompt,
                "assistant_response": result["text"],
                # Chain-of-thought TEXT is intentionally NOT persisted (privacy and
                # provider ToS). We log only the tokens count and the availability
                # mode for downstream cost/coverage analysis.
                "cot_available_mode": result.get("cot_available_mode", "unavailable"),
                "parsed": parsed,
                "refusal": refusal,
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "cot_tokens": result.get("cot_tokens"),
                "latency_ms": result["latency_ms"],
                "cost_usd": result["cost_usd"],
            }
        )

        history.append({"role": "assistant", "content": result["text"]})

    return conversation_id, failed


def _provider_from_id(model_id: str) -> str:
    """Mirror of providers._provider_for_model so the runner can resolve the
    provider when model_cfg doesn't supply one."""
    m = model_id.lower()
    if m.startswith("claude") or m.startswith("anthropic/"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("openai/"):
        return "openai"
    if m.startswith("kimi") or m.startswith("moonshot"):
        return "moonshot"
    return "openrouter"


def run_experiment(
    experiment: ExperimentSpec,
    runs_root: Path | str,
    on_progress=None,
    n_workers: int = 1,
) -> dict:
    """Execute the full experiment loop and write logs to disk.

    Args:
        experiment: an object implementing ExperimentSpec.
        runs_root: directory under which `<EXPERIMENT_ID>/<run_id>/` is created.
        on_progress: optional callback(done, planned, conversation_id, failed).
        n_workers: number of conversations to run concurrently. 1 = strictly
            sequential (default). Conversations are independent, so this is
            safe; turns within a conversation remain sequential.

    Returns a summary dict with run_id, run_dir, and totals.
    """
    config = experiment.load_config()
    models = experiment.models()
    registers = experiment.registers()
    n = experiment.n_per_cell()
    temperature = experiment.temperature()
    max_tokens = experiment.max_tokens()
    system = experiment.system_prompt()
    prices = experiment.prices()
    reasoning_cfg = experiment.reasoning_config() if hasattr(experiment, "reasoning_config") else {}

    manifest = create_manifest(
        experiment_id=experiment.EXPERIMENT_ID,
        config=config,
        data_files=experiment.data_files(),
        extra={
            "models": models,
            "registers": registers,
            "n_per_cell": n,
            "num_turns": experiment.num_turns(),
            "n_workers": n_workers,
        },
    )
    run_dir = Path(runs_root) / experiment.EXPERIMENT_ID / manifest["run_id"]
    write_manifest(run_dir, manifest)
    logger = JSONLLogger(run_dir)

    # Build the full list of conversations to run.
    jobs: list[dict] = []
    for model_cfg in models:
        for register in registers:
            for run_idx in range(n):
                jobs.append(
                    dict(model_cfg=model_cfg, register=register, run_idx=run_idx)
                )

    total_planned = len(jobs)
    total_done = 0
    total_failed = 0
    progress_lock = Lock()

    def _report(conversation_id: str, failed: bool) -> None:
        nonlocal total_done, total_failed
        with progress_lock:
            total_done += 1
            if failed:
                total_failed += 1
            if on_progress is not None:
                on_progress(
                    done=total_done,
                    planned=total_planned,
                    conversation_id=conversation_id,
                    failed=failed,
                )

    if n_workers <= 1:
        # Sequential path
        for job in jobs:
            cid, failed = _run_one_conversation(
                experiment=experiment,
                logger=logger,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
                prices=prices,
                reasoning_cfg=reasoning_cfg,
                **job,
            )
            _report(cid, failed)
    else:
        # Parallel path
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = [
                pool.submit(
                    _run_one_conversation,
                    experiment=experiment,
                    logger=logger,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system,
                    prices=prices,
                    reasoning_cfg=reasoning_cfg,
                    **job,
                )
                for job in jobs
            ]
            for fut in as_completed(futures):
                try:
                    cid, failed = fut.result()
                except Exception as e:
                    # Should be rare — _run_one_conversation catches its own per-turn errors
                    cid = f"<unknown>"
                    failed = True
                    logger.log_error(
                        {
                            "phase": "worker",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        }
                    )
                _report(cid, failed)

    summary = {
        "run_id": manifest["run_id"],
        "run_dir": str(run_dir),
        "total_conversations": total_done,
        "total_failed": total_failed,
        "n_workers": n_workers,
    }
    return summary

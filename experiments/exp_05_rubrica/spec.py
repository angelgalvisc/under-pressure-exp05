"""Experiment 05 (con rúbrica) — score 0-5 con rúbrica binaria 5 dimensiones.

Implements the ExperimentSpec protocol from core.runner. The T0 stimulus
asks the model to evaluate a Heidegger claim across 5 binary dimensions
(D1..D5) and emit both `DIMENSIONS: D1=… D5=…` and `FINAL_SCORE: <0-5>`.
T1 delivers the German evidence; T2-T5 apply pressure according to the
chosen register.

The runner reads `parsed["dimensions"]`, `parsed["dimensional_sum"]`,
and `parsed["sycophancy_gap"]` automatically because `core.parser.parse_score_json`
detects the DIMENSIONS line and merges it into the parsed dict.

Companion experiment: `exp_05_no_rubrica`, identical setup but T0 only
requests FINAL_SCORE without the dimensional rubric.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml

from . import EXPERIMENT_ID
from .turn_builder import build_user_prompt_for_turn


HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
CONFIG_DIR = HERE / "config"


class Experiment05RubricaSpec:
    """ExperimentSpec implementation for exp_05_rubrica."""

    EXPERIMENT_ID = EXPERIMENT_ID

    def __init__(
        self,
        models_filter: Optional[list[str]] = None,
        registers_filter: Optional[list[str]] = None,
        n_per_cell_override: Optional[int] = None,
    ):
        self._stimulus = json.loads((DATA_DIR / "stimulus.json").read_text(encoding="utf-8"))
        self._registers = json.loads((DATA_DIR / "registers.json").read_text(encoding="utf-8"))
        self._models_cfg = yaml.safe_load((CONFIG_DIR / "models.yaml").read_text(encoding="utf-8"))
        self._prices_cfg = yaml.safe_load((CONFIG_DIR / "prices.yaml").read_text(encoding="utf-8"))
        self._run_cfg = yaml.safe_load((CONFIG_DIR / "run_config.yaml").read_text(encoding="utf-8"))

        self._models_filter = models_filter
        self._registers_filter = registers_filter
        self._n_per_cell_override = n_per_cell_override

    # ------------------------------------------------------------------
    # ExperimentSpec interface
    # ------------------------------------------------------------------
    def load_config(self) -> dict:
        return {
            "run": self._run_cfg,
            "models": self._models_cfg,
            "prices": self._prices_cfg,
            "filters": {
                "models": self._models_filter,
                "registers": self._registers_filter,
                "n_per_cell_override": self._n_per_cell_override,
            },
        }

    def models(self) -> list[dict]:
        all_models = self._models_cfg["models"]
        if not self._models_filter:
            return all_models
        wanted = [w.lower() for w in self._models_filter]
        out = []
        for m in all_models:
            mid = m["id"].lower()
            label = str(m.get("label", "")).lower()
            if any(w == mid or w == label or w in mid or w in label for w in wanted):
                out.append(m)
        return out

    def registers(self) -> list[str]:
        base = [r for r in self._run_cfg["registers"] if r in self._registers]
        if not self._registers_filter:
            return base
        wanted = set(self._registers_filter)
        return [r for r in base if r in wanted]

    def num_turns(self) -> int:
        return int(self._run_cfg["num_turns"])

    def n_per_cell(self) -> int:
        if self._n_per_cell_override is not None:
            return int(self._n_per_cell_override)
        return int(self._run_cfg["n_per_cell"])

    def temperature(self) -> float:
        return float(self._run_cfg["temperature"])

    def max_tokens(self) -> int:
        return int(self._run_cfg["max_tokens"])

    def system_prompt(self) -> Optional[str]:
        sp = self._run_cfg.get("system_prompt")
        return sp if sp else None

    def reasoning_config(self) -> dict:
        return self._run_cfg.get("reasoning") or {}

    def prices(self) -> dict:
        return {
            k: v for k, v in self._prices_cfg.items()
            if isinstance(v, dict) and "input_per_1m" in v
        }

    def data_files(self) -> list[Path]:
        return [
            DATA_DIR / "stimulus.json",
            DATA_DIR / "registers.json",
            DATA_DIR / "codebook.md",
            CONFIG_DIR / "models.yaml",
            CONFIG_DIR / "prices.yaml",
            CONFIG_DIR / "run_config.yaml",
        ]

    @property
    def codebook_path(self) -> Path:
        return DATA_DIR / "codebook.md"

    def build_user_prompt(
        self, register: str, run_idx: int, turn_idx: int, history: list[dict]
    ) -> str:
        return build_user_prompt_for_turn(
            stimulus=self._stimulus,
            registers=self._registers,
            register=register,
            turn_idx=turn_idx,
        )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def stimulus(self) -> dict:
        return self._stimulus

    @property
    def judge_config(self) -> dict:
        return self._models_cfg["judge"]

    @property
    def judge_run_config(self) -> dict:
        return self._run_cfg["judge"]

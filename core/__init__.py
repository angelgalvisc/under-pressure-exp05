"""Reusable infrastructure for tone/pressure-style LLM experiments.

This package is generic: it does not contain anything specific to a single
experiment. Each experiment under `experiments/` provides its own data,
config, and metrics, and reuses the building blocks here.

Public API:
    chat(...)                — unified call across providers
    JSONLLogger              — append-only run logging
    create_manifest(...)     — capture immutable inputs of a run
    write_manifest(...)
    parse_score_json(...)    — extract structured score from response
    is_refusal(...)
    LLMJudge                 — codebook-driven categorical judge
    run_experiment(...)      — generic orchestrator
"""

from .providers import chat
from .logger import JSONLLogger
from .manifest import create_manifest, write_manifest
from .parser import parse_score_json, is_refusal
from .judge import LLMJudge
from .runner import run_experiment

__all__ = [
    "chat",
    "JSONLLogger",
    "create_manifest",
    "write_manifest",
    "parse_score_json",
    "is_refusal",
    "LLMJudge",
    "run_experiment",
]

__version__ = "0.1.0"

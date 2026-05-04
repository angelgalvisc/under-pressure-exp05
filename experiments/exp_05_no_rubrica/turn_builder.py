"""Build the user prompt for each turn of exp_05_no_rubrica.

Conversation structure: T0 = stimulus (model evaluates the claim on a
0-5 scale and emits FINAL_SCORE). T1 = pressure register opening +
German evidence. T2..T5 = remaining register turns (escalation).
"""
from __future__ import annotations


NUM_TURNS = 6
NUM_PRESSURE_TURNS = 5


def build_turn_0(stimulus: dict) -> str:
    """T0: baseline stimulus, ask for dimensional rubric + FINAL_SCORE."""
    return stimulus["turn_0_prompt"]


def build_register_turn(stimulus: dict, registers: dict, register: str, turn_idx: int) -> str:
    """T1..T5: register-specific message.

    T1 includes the German evidence block (substituted into {evidence} placeholder).
    T2..T5 are escalation messages — no evidence injection, just affective pressure.
    The trailing reminder asks for DIMENSIONS + FINAL_SCORE.
    """
    if register not in registers:
        raise KeyError(f"Unknown register: {register}")
    if turn_idx < 1 or turn_idx > NUM_PRESSURE_TURNS:
        raise IndexError(f"Turn index out of pressure range: {turn_idx}")

    variants = registers[register]
    if not isinstance(variants, list) or len(variants) < NUM_PRESSURE_TURNS:
        raise ValueError(
            f"Register {register!r} must have at least {NUM_PRESSURE_TURNS} variants; "
            f"got {len(variants) if isinstance(variants, list) else 'non-list'}."
        )

    template = variants[turn_idx - 1]

    if "{evidence}" in template:
        evidence_block = stimulus.get("evidence_de_block", "")
        return template.replace("{evidence}", evidence_block)
    return template


def build_user_prompt_for_turn(
    *,
    stimulus: dict,
    registers: dict,
    register: str,
    turn_idx: int,
) -> str:
    """Dispatcher: returns the user prompt for the given turn index."""
    if turn_idx == 0:
        return build_turn_0(stimulus)
    if 1 <= turn_idx <= NUM_PRESSURE_TURNS:
        return build_register_turn(stimulus, registers, register, turn_idx)
    raise ValueError(f"Turn index out of range [0, {NUM_TURNS - 1}]: {turn_idx}")

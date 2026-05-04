"""Unified `chat()` interface across Anthropic, OpenAI, and OpenRouter.

Each provider returns a normalized dict:

    {
        "text":               str,
        "cot_text":           str | None,   # best-available trace (raw or summary)
        "cot_text_raw":       str | None,   # full reasoning trace, only when provider exposes it
        "cot_text_summary":   str | None,   # provider-generated summary, when available
        "cot_tokens":         int | None,   # count of reasoning tokens, when reported
        "cot_available_mode": str,          # "raw" | "summary" | "tokens_only" | "unavailable"
        "input_tokens":       int,
        "output_tokens":      int,
        "latency_ms":         int,
        "cost_usd":           float,
        "raw":                dict,         # original API response (for debugging)
    }

CoT availability matrix (v3.2 — explicit-reasoning condition):
  - Kimi K2.6 (Moonshot)         → "raw"        (returns reasoning_content by default)
  - Claude Opus 4.7 (Anthropic)  → "summary"    (extended thinking, summarized for Opus 4.x)
  - GPT-5.5 (OpenAI)             → "summary"    (Responses API + reasoning.summary)
  - OpenRouter / others          → varies; we report whatever the upstream returns

Reproducibility note: Anthropic does not accept a `seed` parameter, so
generation is non-deterministic even at temperature=0. OpenAI and OpenRouter
accept `seed` but as best-effort. Document this in the experiment README.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Lazy clients (avoid importing SDKs we don't use, and avoid failing at import
# time when an unused key is missing)
# ---------------------------------------------------------------------------
def _anthropic_client():
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
    return Anthropic(api_key=api_key)


def _openai_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def _openrouter_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment")
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


def _moonshot_client():
    from openai import OpenAI

    api_key = os.environ.get("MOONSHOT_API_KEY")
    if not api_key:
        raise RuntimeError("MOONSHOT_API_KEY not set in environment")
    return OpenAI(api_key=api_key, base_url="https://api.moonshot.ai/v1")


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------
def _provider_for_model(model_id: str) -> str:
    """Infer provider from the model id.

    Convention:
      - "claude-..." / "anthropic/..."         → anthropic
      - "gpt-..." / "o1-..." / "openai/..."    → openai
      - "kimi-..." / "moonshot-..."            → moonshot (direct API)
      - anything else                          → openrouter (fallback)
    Override by passing `provider=` explicitly to chat().
    """
    m = model_id.lower()
    if m.startswith("claude") or m.startswith("anthropic/"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("openai/"):
        return "openai"
    if m.startswith("kimi") or m.startswith("moonshot"):
        return "moonshot"
    return "openrouter"


def _calculate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict[str, dict[str, float]],
) -> float:
    """Look up price per 1M tokens from prices dict and compute USD cost."""
    cfg = prices.get(model_id, {})
    in_per_1m = cfg.get("input_per_1m", 0.0)
    out_per_1m = cfg.get("output_per_1m", 0.0)
    return (input_tokens * in_per_1m + output_tokens * out_per_1m) / 1_000_000


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------
_TRANSIENT_ERROR_TOKENS = (
    "RateLimit",
    "Timeout",
    "Connection",
    "InternalServer",
    "ServiceUnavailable",
    "Overloaded",
    "APIError",
)


def _retry_with_backoff(fn, max_retries: int = 5, base_delay: float = 1.0):
    """Exponential backoff for transient errors. Re-raises non-transient errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_name = type(e).__name__
            transient = any(tok in err_name for tok in _TRANSIENT_ERROR_TOKENS)
            last_exc = e
            if not transient or attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    if last_exc:
        raise last_exc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def chat(
    model_id: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    prices: Optional[dict] = None,
    provider: Optional[str] = None,
    seed: Optional[int] = None,
    thinking_config: Optional[dict] = None,
    reasoning_effort: Optional[str] = None,
    reasoning_summary: Optional[str] = None,
    **kwargs: Any,
) -> dict:
    """Send a chat completion request and return a normalized response dict.

    Reasoning controls:
        thinking_config: passed verbatim to Anthropic as the `thinking` arg.
            E.g. {"type": "adaptive", "display": "summarized"} for Opus 4.7.
            Ignored by other providers.
        reasoning_effort: OpenAI only. "minimal" | "low" | "medium" | "high".
            Routes the call to the Responses API to capture reasoning summaries.
        reasoning_summary: OpenAI only. "auto" | "concise" | "detailed".
            Defaults to "auto" when reasoning_effort is provided.
    """
    prices = prices or {}
    provider = provider or _provider_for_model(model_id)
    t0 = time.time()

    if provider == "anthropic":
        result = _retry_with_backoff(
            lambda: _anthropic_call(
                model_id, messages, temperature, max_tokens,
                thinking_config=thinking_config, **kwargs
            )
        )
    elif provider == "openai":
        result = _retry_with_backoff(
            lambda: _openai_call(
                model_id, messages, temperature, max_tokens, seed=seed,
                reasoning_effort=reasoning_effort,
                reasoning_summary=reasoning_summary,
                **kwargs
            )
        )
    elif provider == "openrouter":
        result = _retry_with_backoff(
            lambda: _openrouter_call(model_id, messages, temperature, max_tokens, seed=seed, **kwargs)
        )
    elif provider == "moonshot":
        result = _retry_with_backoff(
            lambda: _moonshot_call(model_id, messages, temperature, max_tokens, seed=seed, **kwargs)
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

    result["latency_ms"] = int((time.time() - t0) * 1000)
    result["cost_usd"] = _calculate_cost(
        model_id, result["input_tokens"], result["output_tokens"], prices
    )
    return result


# ---------------------------------------------------------------------------
# Per-provider calls
# ---------------------------------------------------------------------------
def _extract_final_segment(reasoning_text: str) -> str:
    """When promoting reasoning_content to visible response, keep only the
    final segment that looks like a concluded answer.

    Strategy:
    1. If `FINAL_SCORE:` marker exists → keep from the start of the paragraph
       containing the LAST FINAL_SCORE through the end (the conclusion).
    2. Otherwise → keep the last 2-3 paragraphs (likely the conclusion).
    3. Fallback → return the whole text but trimmed.

    This avoids dumping the full thinking trace (which contains drafts and
    counterfactuals) into assistant_response.
    """
    if not reasoning_text:
        return ""

    # Strategy 1: anchor on FINAL_SCORE marker
    matches = list(re.finditer(r"FINAL_SCORE\s*[:=]", reasoning_text, re.IGNORECASE))
    if matches:
        last = matches[-1]
        # Walk back to the start of the paragraph containing this marker
        start = reasoning_text.rfind("\n\n", 0, last.start())
        if start == -1:
            start = 0
        else:
            start += 2
        return reasoning_text[start:].strip()

    # Strategy 2: last 2 paragraphs
    paras = [p.strip() for p in reasoning_text.split("\n\n") if p.strip()]
    if len(paras) >= 2:
        return "\n\n".join(paras[-2:])
    return reasoning_text.strip()


def _split_system_messages(messages: list[dict]) -> tuple[Optional[str], list[dict]]:
    """Anthropic and OpenAI Responses API both want system separately from messages."""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    system = "\n\n".join(system_parts) if system_parts else None
    return system, rest


def _empty_cot_fields() -> dict:
    """Default CoT fields when nothing is captured."""
    return {
        "cot_text": None,
        "cot_text_raw": None,
        "cot_text_summary": None,
        "cot_tokens": None,
        "cot_available_mode": "unavailable",
    }


def _anthropic_call(
    model_id, messages, temperature, max_tokens,
    thinking_config: Optional[dict] = None, **kwargs,
):
    """Anthropic call. When thinking_config is provided, extended thinking is
    enabled and we capture summarized thinking blocks.

    Constraint: when thinking is enabled, Anthropic requires temperature=1.0
    and forbids top_p / top_k. We force temperature=1.0 here so the caller
    doesn't have to know.
    """
    client = _anthropic_client()
    system, rest = _split_system_messages(messages)

    create_kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": rest,
    }
    if system:
        create_kwargs["system"] = system

    if thinking_config:
        create_kwargs["thinking"] = thinking_config
        # Anthropic API: temperature MUST be 1.0 with extended thinking.
        create_kwargs["temperature"] = 1.0
    else:
        create_kwargs["temperature"] = temperature

    resp = client.messages.create(**create_kwargs)

    text_blocks: list[str] = []
    thinking_blocks: list[str] = []
    for block in resp.content:
        bt = getattr(block, "type", None)
        if bt == "text":
            text_blocks.append(getattr(block, "text", ""))
        elif bt == "thinking":
            thinking_blocks.append(getattr(block, "thinking", ""))

    text = "".join(text_blocks)
    thinking_text = "\n\n".join(b for b in thinking_blocks if b) or None

    cot_fields = _empty_cot_fields()
    if thinking_text is not None:
        # Opus 4.x exposes thinking as summarized blocks (raw is not standard).
        cot_fields["cot_text_summary"] = thinking_text
        cot_fields["cot_text"] = thinking_text
        cot_fields["cot_available_mode"] = "summary"
        # Anthropic does not separate thinking_tokens in usage; thinking is
        # billed as part of output_tokens. Leave cot_tokens None.

    raw = resp.model_dump() if hasattr(resp, "model_dump") else None

    return {
        "text": text,
        **cot_fields,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "raw": raw,
    }


def _openai_call(
    model_id, messages, temperature, max_tokens, seed=None,
    reasoning_effort: Optional[str] = None,
    reasoning_summary: Optional[str] = None,
    **kwargs,
):
    """OpenAI call.

    When reasoning_effort is provided, route to the Responses API so we can
    capture reasoning summaries (Chat Completions exposes only token counts).
    Otherwise fall back to Chat Completions for non-reasoning models.
    """
    if reasoning_effort:
        return _openai_responses_call(
            model_id, messages, temperature, max_tokens,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary or "auto",
        )
    return _openai_chat_completions_call(model_id, messages, temperature, max_tokens, seed=seed)


def _openai_responses_call(
    model_id, messages, temperature, max_tokens,
    reasoning_effort: str, reasoning_summary: str,
):
    """OpenAI Responses API path. Captures reasoning summaries + reasoning_tokens."""
    client = _openai_client()
    system, rest = _split_system_messages(messages)

    create_kwargs: dict[str, Any] = {
        "model": model_id,
        "input": rest,
        "max_output_tokens": max_tokens,
        "reasoning": {
            "effort": reasoning_effort,
            "summary": reasoning_summary,
        },
    }
    if system:
        create_kwargs["instructions"] = system

    # Some reasoning models reject `temperature` ≠ default. Try with, fall back without.
    create_kwargs["temperature"] = temperature
    try:
        resp = client.responses.create(**create_kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "temperature" in msg and ("unsupported" in msg or "does not support" in msg):
            create_kwargs.pop("temperature", None)
            resp = client.responses.create(**create_kwargs)
        else:
            raise

    # Extract visible text and reasoning summary from the output items.
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        item_type = getattr(item, "type", None)
        if item_type == "message":
            for content in getattr(item, "content", []) or []:
                ctype = getattr(content, "type", None)
                if ctype in ("output_text", "text"):
                    text_parts.append(getattr(content, "text", "") or "")
        elif item_type == "reasoning":
            # Each reasoning item may carry a `summary` list with text parts.
            for s in getattr(item, "summary", []) or []:
                stext = getattr(s, "text", None) or (s.get("text") if isinstance(s, dict) else None)
                if stext:
                    reasoning_parts.append(stext)

    # Fallback: SDK convenience accessor
    text = "".join(text_parts) or (getattr(resp, "output_text", "") or "")
    reasoning_text = "\n\n".join(reasoning_parts) if reasoning_parts else None

    # Token usage
    usage = resp.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cot_tokens = None
    details = getattr(usage, "output_tokens_details", None)
    if details is not None:
        cot_tokens = getattr(details, "reasoning_tokens", None)

    cot_fields = _empty_cot_fields()
    if reasoning_text:
        cot_fields["cot_text_summary"] = reasoning_text
        cot_fields["cot_text"] = reasoning_text
        cot_fields["cot_available_mode"] = "summary"
    elif cot_tokens:
        cot_fields["cot_available_mode"] = "tokens_only"
    cot_fields["cot_tokens"] = cot_tokens

    raw = resp.model_dump() if hasattr(resp, "model_dump") else None

    return {
        "text": text,
        **cot_fields,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw": raw,
    }


def _openai_chat_completions_call(model_id, messages, temperature, max_tokens, seed=None):
    """Legacy Chat Completions path. Used when reasoning_effort is not requested."""
    client = _openai_client()
    create_kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }
    if seed is not None:
        create_kwargs["seed"] = seed

    try:
        resp = client.chat.completions.create(**create_kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "max_completion_tokens" in msg and "unsupported" in msg:
            create_kwargs.pop("max_completion_tokens", None)
            create_kwargs["max_tokens"] = max_tokens
            resp = client.chat.completions.create(**create_kwargs)
        else:
            raise
    msg_obj = resp.choices[0].message
    text = msg_obj.content or ""

    reasoning_text = getattr(msg_obj, "reasoning_content", None)
    cot_tokens = None
    usage = resp.usage
    if hasattr(usage, "completion_tokens_details"):
        details = usage.completion_tokens_details
        cot_tokens = getattr(details, "reasoning_tokens", None)

    cot_fields = _empty_cot_fields()
    if reasoning_text:
        cot_fields["cot_text_raw"] = reasoning_text
        cot_fields["cot_text"] = reasoning_text
        cot_fields["cot_available_mode"] = "raw"
    elif cot_tokens:
        cot_fields["cot_available_mode"] = "tokens_only"
    cot_fields["cot_tokens"] = cot_tokens

    raw = resp.model_dump() if hasattr(resp, "model_dump") else None

    return {
        "text": text,
        **cot_fields,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "raw": raw,
    }


def _openrouter_call(model_id, messages, temperature, max_tokens, seed=None, **kwargs):
    client = _openrouter_client()
    create_kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if seed is not None:
        create_kwargs["seed"] = seed

    resp = client.chat.completions.create(**create_kwargs)
    msg = resp.choices[0].message
    text = msg.content or ""
    reasoning_text = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)

    cot_fields = _empty_cot_fields()
    if reasoning_text:
        cot_fields["cot_text_raw"] = reasoning_text
        cot_fields["cot_text"] = reasoning_text
        cot_fields["cot_available_mode"] = "raw"

    raw = resp.model_dump() if hasattr(resp, "model_dump") else None

    return {
        "text": text,
        **cot_fields,
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "raw": raw,
    }


def _moonshot_call(model_id, messages, temperature, max_tokens, seed=None, **kwargs):
    """Moonshot/Kimi direct API. OpenAI-compatible at https://api.moonshot.ai/v1.

    Kimi K2.6 (thinking model) sometimes returns the user-visible answer inside
    `reasoning_content` instead of `content`. If `content` is empty but
    `reasoning_content` has substantive text, we use the latter as the visible
    response — otherwise multi-turn conversations break (the API rejects
    `{"role": "assistant", "content": ""}` on subsequent turns).
    """
    client = _moonshot_client()
    create_kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if seed is not None:
        create_kwargs["seed"] = seed

    resp = client.chat.completions.create(**create_kwargs)
    msg = resp.choices[0].message
    content_text = msg.content or ""
    reasoning_text = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""

    if content_text.strip():
        # Standard case: visible answer in content, reasoning trace separate.
        text = content_text
        cot_raw = reasoning_text or None
    elif reasoning_text.strip():
        # Kimi quirk: empty content but reasoning_content has the response.
        # Promote ONLY the final segment of reasoning to assistant_response;
        # keep the FULL reasoning trace separately for analysis.
        text = _extract_final_segment(reasoning_text)
        cot_raw = reasoning_text
    else:
        raise RuntimeError(
            f"Moonshot returned empty content and empty reasoning_content "
            f"for model {model_id}. Cannot continue conversation with empty assistant message."
        )

    cot_fields = _empty_cot_fields()
    if cot_raw:
        cot_fields["cot_text_raw"] = cot_raw
        cot_fields["cot_text"] = cot_raw
        cot_fields["cot_available_mode"] = "raw"

    raw = resp.model_dump() if hasattr(resp, "model_dump") else None

    return {
        "text": text,
        **cot_fields,
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "raw": raw,
    }

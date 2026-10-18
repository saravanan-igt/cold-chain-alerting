"""Multi-provider AI client wrapper supporting Google Gemini API and Anthropic Claude SDK with cognitive physics fallback."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger("coldline.ai")

DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def get_anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY", "").strip() or None


def get_gemini_api_key() -> str | None:
    return (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
        or None
    )


def get_active_provider() -> str:
    pref = os.environ.get("AI_PROVIDER", "auto").strip().lower()
    if pref in ("gemini", "google"):
        if get_gemini_api_key():
            return "gemini"
    elif pref in ("anthropic", "claude"):
        if get_anthropic_api_key():
            return "anthropic"

    # Auto-detection based on configured keys
    if get_gemini_api_key():
        return "gemini"
    if get_anthropic_api_key():
        return "anthropic"

    return "cognitive_simulation"


def get_active_model() -> str:
    provider = get_active_provider()
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    return "cognitive-thermal-physics-v1"


def get_ai_status() -> dict[str, Any]:
    provider = get_active_provider()
    gemini_key = get_gemini_api_key() is not None
    anthropic_key = get_anthropic_api_key() is not None

    available_providers = []
    if gemini_key:
        available_providers.append("gemini")
    if anthropic_key:
        available_providers.append("anthropic")
    if not available_providers:
        available_providers.append("cognitive_simulation")

    return {
        "provider": provider,
        "model": get_active_model(),
        "mode": "live_api" if provider in ("gemini", "anthropic") else "cognitive_simulation",
        "has_api_key": gemini_key or anthropic_key,
        "gemini_configured": gemini_key,
        "anthropic_configured": anthropic_key,
        "available_providers": available_providers,
        "supported_providers": ["gemini", "anthropic", "cognitive_simulation"],
        "capabilities": [
            "real_alert_detection",
            "telemetry_gap_reasoning",
            "transient_spike_suppression",
            "sub_threshold_drift_warning",
            "incident_triage_and_root_cause",
            "driver_dispatch_scripting",
            "fleet_risk_advisory",
            "operations_copilot_chat"
        ]
    }


def parse_json_from_llm(text: str) -> dict[str, Any]:
    """Extract valid JSON from LLM response, handling markdown fences or preamble."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        first = clean.find("{")
        last = clean.rfind("}")
        if first != -1 and last != -1:
            return json.loads(clean[first:last + 1])
        raise


def invoke_gemini(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Call Google Gemini API using the official google-genai SDK."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    from google import genai
    from google.genai import types

    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    return parse_json_from_llm(response.text or "{}")


def invoke_anthropic(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Call Anthropic Claude API using the official anthropic SDK."""
    api_key = get_anthropic_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

    import anthropic

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    content_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            content_text += block.text
        elif isinstance(block, dict) and "text" in block:
            content_text += block["text"]

    return parse_json_from_llm(content_text)


def invoke_llm(
    system_prompt: str,
    user_prompt: str,
    fallback_fn: Callable[[], dict[str, Any]] | None = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """
    Unified multi-provider invoker:
    Dispatches to Google Gemini API or Anthropic Claude API based on active credentials,
    seamlessly falling back to cognitive physics simulation if keys are absent or calls fail.
    """
    provider = get_active_provider()

    if provider == "gemini":
        try:
            return invoke_gemini(system_prompt, user_prompt, temperature=temperature)
        except Exception as exc:
            logger.warning(f"Gemini API call failed ({exc}); checking fallback.")
            if fallback_fn:
                return fallback_fn()
            raise

    if provider == "anthropic":
        try:
            return invoke_anthropic(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            logger.warning(f"Claude API call failed ({exc}); checking fallback.")
            if fallback_fn:
                return fallback_fn()
            raise

    # Cognitive simulation fallback
    if fallback_fn:
        return fallback_fn()
    raise RuntimeError("No LLM API keys configured and no fallback was provided.")


# Backward-compatibility alias
invoke_claude = invoke_llm

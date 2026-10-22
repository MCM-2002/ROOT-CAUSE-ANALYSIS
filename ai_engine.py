"""AI requests and cause generation (Gemini by default, provider-pluggable)."""
from __future__ import annotations

import os
import random
import time
from typing import Callable, List, Optional

from models import (
    AIResponseError,
    FishboneResponse,
    ProblemInput,
    parse_fishbone_response,
)
from prompts import SYSTEM_PROMPT, build_generation_prompt, build_regeneration_prompt

DEFAULT_MODEL = "gemini-3.8-flash"


class AIEngineError(Exception):
    """User-presentable error from the AI layer."""


class ConfigError(AIEngineError):
    """Missing or invalid configuration (e.g. API key)."""


class TransientAIError(Exception):
    """Internal: retryable failure."""


# A provider is any callable (system_prompt, user_prompt) -> raw text.
Provider = Callable[[str, str], str]


def get_api_key(secrets: Optional[object] = None) -> Optional[str]:
    """Look up the API key from env vars, then Streamlit secrets. Never logged or displayed."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    if secrets is not None:
        try:
            return secrets.get("GEMINI_API_KEY") or secrets.get("GOOGLE_API_KEY")
        except Exception:
            return None
    return None


def get_model_name(secrets: Optional[object] = None) -> str:
    name = os.environ.get("GEMINI_MODEL")
    if not name and secrets is not None:
        try:
            name = secrets.get("GEMINI_MODEL")
        except Exception:
            name = None
    return name or DEFAULT_MODEL


def make_gemini_provider(api_key: str, model: str) -> Provider:
    """Build a provider backed by the google-genai SDK."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ConfigError("The 'google-genai' package is not installed. Run: pip install -r requirements.txt") from exc

    client = genai.Client(api_key=api_key)

    def call(system_prompt: str, user_prompt: str) -> str:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.6,
                ),
            )
        except Exception as exc:
            _raise_classified(exc)
        text = getattr(resp, "text", None)
        if not text:
            raise AIResponseError("The AI returned an empty response (it may have been blocked by safety filters).")
        return text

    return call


def make_demo_provider() -> Provider:
    """Offline provider returning the sample hypotheses (for trying the UI without an API key)."""
    import json
    import re

    full = {
        "problem": "Seam puckering defect rate above target (demo data)",
        "man": ["Variation in operator sewing technique", "Inconsistent adherence to work instructions",
                "Variation in operator experience"],
        "machine": ["Incorrect thread tension", "Worn or unsuitable needle", "Incorrect machine settings",
                    "Inadequate preventive maintenance"],
        "method": ["Inconsistent sewing procedure", "Incorrect sewing sequence", "Inadequate setup verification"],
        "material": ["Fabric stretch variation", "Fabric thickness variation", "Differences between fabric batches"],
        "measurement": ["Inconsistent defect classification", "Variation in inspection method",
                        "Inconsistent defect recording"],
        "environment": ["Temperature variation", "Humidity variation"],
    }
    alt = [
        "Alternative idea A (demo regeneration)",
        "Alternative idea B (demo regeneration)",
    ]

    def call(system_prompt: str, user_prompt: str) -> str:
        m = re.search(r'JSON key: "(\w+)"', user_prompt)
        if m:
            out = {k: [] for k in full if k != "problem"}
            out[m.group(1)] = [f"{a} #{random.randint(100, 999)}" for a in alt]
            return json.dumps(out)
        return json.dumps(full)

    return call


def _raise_classified(exc: Exception) -> None:
    """Map SDK exceptions to retryable / fatal errors."""
    msg = str(exc)
    low = msg.lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (401, 403) or "api key" in low and ("invalid" in low or "not valid" in low):
        raise ConfigError("The API key was rejected. Check your GEMINI_API_KEY.") from exc
    if code == 404 or "not found" in low and "model" in low:
        raise AIEngineError("The configured model was not found. Check GEMINI_MODEL.") from exc
    if code in (429, 500, 502, 503, 504) or any(
        s in low for s in ("rate limit", "quota", "resource_exhausted", "unavailable", "overloaded", "timed out", "timeout", "connection")
    ):
        raise TransientAIError(msg) from exc
    raise AIEngineError(f"The AI request failed: {msg[:300]}") from exc


class AIEngine:
    def __init__(
        self,
        provider: Provider,
        max_retries: int = 3,
        base_delay: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.provider = provider
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._sleep = sleep

    def _call_with_retry(self, system_prompt: str, user_prompt: str) -> FishboneResponse:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self.provider(system_prompt, user_prompt)
                return parse_fishbone_response(raw)
            except (TransientAIError, AIResponseError) as exc:
                # Malformed output is also worth one or two retries.
                last = exc
                if attempt >= self.max_retries:
                    break
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                self._sleep(delay)
        if isinstance(last, TransientAIError):
            raise AIEngineError(
                "The AI service is temporarily unavailable or rate limited. "
                "Please wait a moment and try again."
            ) from last
        raise AIEngineError(f"The AI returned an unusable answer after several attempts: {last}") from last

    def generate_causes(self, problem: ProblemInput) -> FishboneResponse:
        if not problem.statement.strip():
            raise AIEngineError("Please enter a problem statement first.")
        prompt = build_generation_prompt(problem.context_block())
        return self._call_with_retry(SYSTEM_PROMPT, prompt)

    def regenerate_category(
        self, problem: ProblemInput, category_key: str, existing: List[str], kept: List[str]
    ) -> List[str]:
        prompt = build_regeneration_prompt(problem.context_block(), category_key, existing, kept)
        resp = self._call_with_retry(SYSTEM_PROMPT, prompt)
        return getattr(resp, category_key)

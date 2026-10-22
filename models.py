"""Pydantic models and validation for Fishbone AI."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# Ordered category keys with display labels and colours (navy-blue business theme).
CATEGORIES: Dict[str, str] = {
    "man": "Man / People",
    "machine": "Machine",
    "method": "Method",
    "material": "Material",
    "measurement": "Measurement",
    "environment": "Mother Nature / Environment",
}
CATEGORY_KEYS: List[str] = list(CATEGORIES.keys())

MAX_CAUSE_LEN = 160
MAX_CAUSES_PER_CATEGORY = 8


class AIResponseError(Exception):
    """Raised when the AI output cannot be parsed or validated."""


class FishboneResponse(BaseModel):
    """Structured output expected from the AI."""

    problem: str = ""
    man: List[str] = Field(default_factory=list)
    machine: List[str] = Field(default_factory=list)
    method: List[str] = Field(default_factory=list)
    material: List[str] = Field(default_factory=list)
    measurement: List[str] = Field(default_factory=list)
    environment: List[str] = Field(default_factory=list)

    @field_validator(*CATEGORY_KEYS, mode="before")
    @classmethod
    def _clean_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            raise ValueError("category must be a list of strings")
        cleaned: List[str] = []
        seen = set()
        for item in v:
            if not isinstance(item, str):
                continue
            text = " ".join(item.split()).strip(" -•*\t")
            if not text:
                continue
            text = text[:MAX_CAUSE_LEN]
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned[:MAX_CAUSES_PER_CATEGORY]


class ProblemInput(BaseModel):
    """What the user enters about the problem."""

    statement: str
    process: str = ""
    product: str = ""
    actual: str = ""
    target: str = ""
    observations: str = ""

    def headline(self) -> str:
        """Short text for the head of the fish."""
        return " ".join(self.statement.split())

    def context_block(self) -> str:
        lines = [f"Problem statement: {self.statement.strip()}"]
        if self.process.strip():
            lines.append(f"Process / department: {self.process.strip()}")
        if self.product.strip():
            lines.append(f"Product / style: {self.product.strip()}")
        if self.actual.strip():
            lines.append(f"Actual performance: {self.actual.strip()}")
        if self.target.strip():
            lines.append(f"Target / standard: {self.target.strip()}")
        if self.observations.strip():
            lines.append(f"Observations / supporting data: {self.observations.strip()}")
        return "\n".join(lines)


class Cause(BaseModel):
    """A single cause in the editable model."""

    id: str
    text: str
    verified: bool = False  # user confirmed supporting evidence


def extract_json(raw: str) -> dict:
    """Parse JSON from raw model text, tolerating markdown fences and extra prose."""
    if raw is None or not raw.strip():
        raise AIResponseError("The AI returned an empty response.")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIResponseError("The AI response was not valid JSON.")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIResponseError(f"The AI response was malformed JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIResponseError("The AI response JSON was not an object.")
    return data


def parse_fishbone_response(raw: str, require_any: bool = True) -> FishboneResponse:
    """Parse and validate raw AI text into a FishboneResponse."""
    data = extract_json(raw)
    # Normalise key case and common aliases.
    aliases = {"people": "man", "environment_": "environment", "mother_nature": "environment"}
    norm: dict = {}
    for k, v in data.items():
        key = str(k).strip().lower().replace(" ", "_")
        norm[aliases.get(key, key)] = v
    try:
        resp = FishboneResponse(**{k: norm[k] for k in ["problem", *CATEGORY_KEYS] if k in norm})
    except Exception as exc:  # pydantic ValidationError
        raise AIResponseError(f"The AI response did not match the expected structure: {exc}") from exc
    if require_any and not any(getattr(resp, k) for k in CATEGORY_KEYS):
        raise AIResponseError("The AI returned no causes for any category.")
    return resp

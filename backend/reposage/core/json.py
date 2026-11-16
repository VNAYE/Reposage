"""Robust JSON extraction for model responses."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_START = re.compile(r"^```[a-zA-Z0-9_-]*\s*")
_FENCE_END = re.compile(r"\s*```$")


def loads_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply, tolerating code fences and prose."""
    stripped = text.strip()
    stripped = _FENCE_START.sub("", stripped)
    stripped = _FENCE_END.sub("", stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response did not contain a JSON object")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("response JSON was not an object")
    return data

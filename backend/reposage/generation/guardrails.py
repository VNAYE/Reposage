"""Input guardrails: prompt-injection filtering and question length limits."""

from __future__ import annotations

import re

from reposage.config import Settings
from reposage.core.plugins import Deps, guardrails
from reposage.domain.interfaces import Guardrail
from reposage.domain.models import GuardrailVerdict

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
        r"disregard\s+(the\s+)?(system|previous|above|all)\s+\w+",
        r"(reveal|show|print|repeat|leak)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)",
        r"you\s+are\s+now\s+(a|an|in)\b",
        r"act\s+as\s+(a\s+)?(dan|developer\s+mode|jailbreak|unrestricted)",
        r"<\|[^|]*\|>",
        r"###\s*(system|instruction|admin)",
        r"begin\s+(system|admin)\s+(prompt|mode)",
        r"forget\s+(everything|all)\s+(above|before|you)",
    )
)


class PromptInjectionFilter(Guardrail):
    name = "prompt_injection"

    def __init__(
        self,
        action: str = "block",
        max_chars: int = 2000,
        patterns: tuple[re.Pattern[str], ...] = INJECTION_PATTERNS,
    ) -> None:
        if action not in {"block", "sanitize", "allow"}:
            raise ValueError("injection_action must be block, sanitize or allow")
        self._action = action
        self._max_chars = max_chars
        self._patterns = patterns

    def inspect(self, text: str) -> GuardrailVerdict:
        cleaned = text.strip()
        if not cleaned:
            return GuardrailVerdict(False, self.name, reason="question is empty")
        if len(cleaned) > self._max_chars:
            return GuardrailVerdict(
                False,
                self.name,
                reason=f"question is longer than {self._max_chars} characters",
                score=1.0,
            )

        matches = [pattern for pattern in self._patterns if pattern.search(cleaned)]
        if not matches:
            return GuardrailVerdict(True, self.name, sanitized_text=cleaned)

        score = min(1.0, len(matches) / 2)
        if self._action == "allow":
            return GuardrailVerdict(
                True,
                self.name,
                reason="injection pattern detected but allowed by configuration",
                sanitized_text=cleaned,
                score=score,
            )
        if self._action == "sanitize":
            for pattern in matches:
                cleaned = pattern.sub("[removed]", cleaned)
            return GuardrailVerdict(
                True,
                self.name,
                reason="injection pattern removed from question",
                sanitized_text=cleaned,
                score=score,
            )
        return GuardrailVerdict(
            False,
            self.name,
            reason="question looks like a prompt-injection attempt",
            score=score,
        )


@guardrails.register("prompt_injection")
def _build_filter(settings: Settings, deps: Deps | None = None) -> Guardrail:
    return PromptInjectionFilter(action=settings.injection_action, max_chars=settings.max_question_chars)

"""Socratic tutor: give hints only, never reveal the correct answer.

The structural guardrail in ``tutor_answer`` detects whether the model's
response contains the correct option text (via word-boundary regex) and, if so,
replaces it with a warm steer-back message. This means the guarantee does NOT
rely on prompt discipline alone — a misbehaving model still cannot leak.
"""
from __future__ import annotations

import re

from src.llm import get_chat_model

SYSTEM = (
    "You are a Socratic tutor. Give hints and conceptual explanations only. "
    "NEVER reveal or restate the correct option. Always steer the learner back to "
    "completing the lesson. If asked for the answer, refuse warmly and give a hint."
)

_STEER_BACK = (
    "Nice try — I won't give it away! Think about the key idea behind the question, "
    "and re-read the relevant section. You've got this — let's keep going."
)


def leaks_answer(text: str, correct_option: str) -> bool:
    """Return True if *text* contains *correct_option* as a whole word (case-insensitive).

    Uses ``\\b`` word boundaries so that e.g. ``"Parisian"`` does NOT match
    the option ``"Paris"``, while ``"paris"`` or ``"Paris."`` does match.
    """
    pattern = rf"\b{re.escape(correct_option.strip())}\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


async def tutor_answer(
    *,
    question: str,
    options: list[str],
    correct_index: int,
    user_message: str,
) -> str:
    """Return a Socratic hint for the given MCQ context.

    The correct option is guarded structurally: if the model's reply contains
    it (whole-word, case-insensitive) the reply is replaced with a steer-back
    message regardless of what the model said.

    ``correct_index`` is clamped to ``[0, len(options)-1]`` so an out-of-range
    value does not raise; callers should still pass a valid index.
    """
    # Bounds guard — clamp to valid range so bad input never raises IndexError.
    if not options:
        return _STEER_BACK
    safe_index = max(0, min(correct_index, len(options) - 1))
    correct = options[safe_index]

    prompt = (
        f"{SYSTEM}\n\n"
        f"Question: {question}\n"
        f"Options: {options}\n"
        f"Learner said: {user_message}\n"
        "Respond with a hint, no answer."
    )

    raw = (await get_chat_model().ainvoke(prompt)).content

    # Coerce to str — some models return a list of content parts.
    if not isinstance(raw, str):
        raw = " ".join(
            part if isinstance(part, str) else (part.get("text", "") if isinstance(part, dict) else str(part))
            for part in (raw if isinstance(raw, list) else [raw])
        )

    if leaks_answer(raw, correct):
        return _STEER_BACK

    return raw

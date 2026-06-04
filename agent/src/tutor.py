"""Socratic tutor: give hints only, never reveal the correct answer.

The structural guardrail in ``tutor_answer`` detects whether the model's
response contains the correct option text (via word-boundary regex) and, if so,
replaces it with a warm steer-back message. This means the guarantee does NOT
rely on prompt discipline alone — a misbehaving model still cannot leak.
"""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm import get_chat_model

SYSTEM = (
    "You are a warm, knowledgeable one-on-one tutor helping a learner who is "
    "working through a specific multiple-choice question. Teach for real: explain "
    "the underlying concepts in your own words, use analogies and concrete "
    "examples, break ideas into clear steps, and ask a guiding question to nudge "
    "their thinking. Draw on your full knowledge of the subject — you are NOT "
    "limited to any document or knowledge base.\n\n"
    "Build on the conversation so far: never just repeat a previous reply. If the "
    "learner is still stuck after a hint, escalate — give a more specific "
    "explanation or a worked analogy, approach it from a new angle, and respond "
    "directly to what they actually said. Be genuinely useful and encouraging.\n\n"
    "THE ONE HARD RULE: never reveal or confirm which option is the correct answer "
    "to THIS question, and never tell them which option/letter to pick. You may "
    "explain everything around it so they can reason it out themselves. If they "
    "ask outright for the answer, warmly decline and instead deepen their "
    "understanding of the concept so they can figure it out.\n\n"
    "Keep replies concise and conversational — this renders in a small chat "
    "panel. Use light formatting only (short paragraphs, a little bold, or a "
    "short numbered/bulleted list when it genuinely helps). Avoid large tables "
    "and big section headings."
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
    history: list[dict] | None = None,
) -> str:
    """Return a conversational tutor reply for the given MCQ context.

    Passes the prior conversation (``history``: a list of ``{"role", "content"}``
    turns, where role is "you"/"user" for the learner and "tutor"/"assistant"
    for the tutor) so the reply builds on the discussion instead of repeating a
    canned hint. Runs at a higher temperature for natural variety.

    The correct option is still guarded structurally: if the model's reply
    contains it (whole-word, case-insensitive) the reply is replaced with a
    steer-back message regardless of what the model said.

    ``correct_index`` is clamped to ``[0, len(options)-1]`` so an out-of-range
    value does not raise; callers should still pass a valid index.
    """
    # Bounds guard — clamp to valid range so bad input never raises IndexError.
    if not options:
        return _STEER_BACK
    safe_index = max(0, min(correct_index, len(options) - 1))
    correct = options[safe_index]

    opts = "\n".join(f"- {o}" for o in options)
    context = f"\n\nThe question the learner is on:\n{question}\n\nThe options are:\n{opts}"

    messages = [SystemMessage(content=f"{SYSTEM}{context}")]
    for turn in history or []:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if turn.get("role") in ("tutor", "assistant", "ai"):
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    # Higher temperature => varied, natural replies (default 0.2 was repetitive).
    raw = (await get_chat_model(temperature=0.7).ainvoke(messages)).content

    # Coerce to str — some models return a list of content parts.
    if not isinstance(raw, str):
        raw = " ".join(
            part if isinstance(part, str) else (part.get("text", "") if isinstance(part, dict) else str(part))
            for part in (raw if isinstance(raw, list) else [raw])
        )

    if leaks_answer(raw, correct):
        return _STEER_BACK

    return raw

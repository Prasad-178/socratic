"""Socratic tutor: guide the learner, never give away the answer.

Two layers protect the answer:

1. A strict Socratic system prompt — the tutor guides with questions, background,
   and escalating hints, but is told never to state or explain the content of the
   correct option.
2. A structural guard in ``tutor_answer``: a verbatim word-boundary check PLUS an
   LLM judge (which is told the correct answer) that detects when a reply gives
   the answer away *semantically* — something the regex alone cannot catch now
   that the tutor explains concepts. A flagged reply is retried once with a
   stricter instruction, then falls back to a safe steer-back. The guarantee does
   NOT rely on prompt discipline alone.
"""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm import get_chat_model

SYSTEM = (
    "You are a warm, encouraging Socratic tutor helping a learner with ONE "
    "multiple-choice question. Help them reason their way to the answer "
    "THEMSELVES — never give it to them.\n\n"
    "You MAY: ask a guiding question, recall a relevant background idea, give a "
    "small analogy, or point to what's worth re-reading — and escalate to a more "
    "specific HINT if they stay stuck. Build on the conversation; don't repeat "
    "yourself; try a fresh angle if a hint didn't land.\n\n"
    "You MUST NEVER state, paraphrase, describe, confirm, or explain the content "
    "of the correct option, nor say which option is right, nor spell out the "
    "specific fact that picks the answer. If explaining something would hand them "
    "the answer, stop and ask a question instead. Always leave the final step to "
    "the learner. If they ask outright for the answer, warmly refuse and hint.\n\n"
    "Keep every reply SHORT — at most 2-3 sentences (or a 2-3 item list). Be "
    "punchy and conversational; light formatting only (this is a small chat "
    "panel): no tables, no big headings."
)

_RETRY_NOTE = (
    "That gave away too much — it revealed or explained the answer. Reply again "
    "with ONLY a short guiding hint or a single question. Do NOT state, describe, "
    "or explain the correct answer; leave the final step to me."
)

_STEER_BACK = (
    "I'll hold back on that one — figuring it out yourself is where the learning "
    "happens! Re-read the part of the lesson this question is about, then ask "
    "yourself which option best fits that idea. What's your current thinking?"
)


def _to_text(content) -> str:
    """Coerce an LLM message ``content`` (str or list of parts) to a plain str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p if isinstance(p, str) else (p.get("text", "") if isinstance(p, dict) else str(p))
            for p in content
        )
    return str(content)


def leaks_answer(text: str, correct_option: str) -> bool:
    """Return True if *text* contains *correct_option* as a whole word (case-insensitive).

    Uses ``\\b`` word boundaries so that e.g. ``"Parisian"`` does NOT match the
    option ``"Paris"``, while ``"paris"`` or ``"Paris."`` does match.
    """
    pattern = rf"\b{re.escape(correct_option.strip())}\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


async def _gives_away_answer(question: str, correct: str, reply: str) -> bool:
    """LLM judge: does *reply* reveal the correct answer (beyond mere background)?

    Catches semantic give-aways the verbatim ``leaks_answer`` check misses (e.g.
    explaining the exact concept the correct option describes, without quoting it).
    """
    verdict = _to_text(
        (
            await get_chat_model(temperature=0).ainvoke(
                "You are checking a tutor's reply to a multiple-choice question. "
                "The reply GIVES AWAY the answer if it states, paraphrases, clearly "
                "describes, confirms, or strongly implies which option is correct, "
                "so the learner no longer has to reason it out. Asking guiding "
                "questions or explaining general background is NOT giving it away; "
                "revealing the specific correct fact IS.\n\n"
                f"QUESTION: {question}\n"
                f"CORRECT ANSWER: {correct}\n"
                f"TUTOR REPLY: {reply}\n\n"
                "Does the reply give away the correct answer? Answer with exactly "
                "one word: YES or NO."
            )
        ).content
    )
    return verdict.strip().lower().startswith("y")


async def tutor_answer(
    *,
    question: str,
    options: list[str],
    correct_index: int,
    user_message: str,
    history: list[dict] | None = None,
) -> str:
    """Return a short Socratic tutor reply that never gives away the answer.

    ``history`` is the prior conversation (a list of ``{"role", "content"}`` turns,
    role "you"/"user" for the learner and "tutor"/"assistant" for the tutor) so the
    reply builds on the discussion instead of repeating itself.

    The reply is guarded by a verbatim check AND an LLM judge that knows the
    correct option. A flagged reply is retried once with a stricter instruction,
    then falls back to a safe steer-back — so the guarantee does not rest on the
    prompt alone. ``correct_index`` is clamped to a valid range.
    """
    if not options:
        return _STEER_BACK
    safe_index = max(0, min(correct_index, len(options) - 1))
    correct = options[safe_index]

    opts = "\n".join(f"- {o}" for o in options)
    context = (
        f"\n\nThe question the learner is on:\n{question}\n\nThe options are:\n{opts}"
    )

    messages: list = [SystemMessage(content=f"{SYSTEM}{context}")]
    for turn in history or []:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if turn.get("role") in ("tutor", "assistant", "ai"):
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    reply = _to_text((await get_chat_model(temperature=0.6).ainvoke(messages)).content)

    # Guard: verbatim leak OR semantic give-away → retry once stricter, then steer back.
    if leaks_answer(reply, correct) or await _gives_away_answer(question, correct, reply):
        retry = messages + [AIMessage(content=reply), HumanMessage(content=_RETRY_NOTE)]
        reply = _to_text((await get_chat_model(temperature=0.5).ainvoke(retry)).content)
        if leaks_answer(reply, correct) or await _gives_away_answer(question, correct, reply):
            return _STEER_BACK

    return reply

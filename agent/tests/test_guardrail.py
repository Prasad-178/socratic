"""
TDD tests for the Socratic tutor guardrail (offline, no key, no network).

Tests verify:
1. leaks_answer() correctly detects / misses the correct option text.
2. tutor_answer() rewrites a leaking model response with steer-back language.
3. tutor_answer() passes through a safe hint unchanged.
"""
from src.tutor import leaks_answer, tutor_answer


# ---------------------------------------------------------------------------
# Minimal fake model
# ---------------------------------------------------------------------------
class _FakeMsg:
    def __init__(self, c: str) -> None:
        self.content = c


class _FakeModel:
    def __init__(self, content: str) -> None:
        self._c = content

    async def ainvoke(self, _):
        return _FakeMsg(self._c)


# ---------------------------------------------------------------------------
# 1. Pure leak-detection tests
# ---------------------------------------------------------------------------
def test_leak_check_detects_answer():
    # Positive: reply contains the exact option text
    assert leaks_answer("The answer is Paris.", "Paris") is True

    # Negative: reply does NOT contain the option text
    assert leaks_answer("Think about European capitals.", "Paris") is False

    # Near-miss (word-boundary): "Parisian" should NOT trigger match for "Paris"
    assert leaks_answer("The Parisian café is beautiful.", "Paris") is False


def test_leak_check_case_insensitive():
    # Should match regardless of case
    assert leaks_answer("the answer is paris.", "Paris") is True
    assert leaks_answer("PARIS is the capital.", "Paris") is True


def test_leak_check_multi_word_option():
    # Multi-word options should also be detected
    assert leaks_answer("The answer is New York.", "New York") is True
    assert leaks_answer("Think about the largest city.", "New York") is False


# ---------------------------------------------------------------------------
# 2. Guardrail rewrite when model leaks
# ---------------------------------------------------------------------------
async def test_tutor_rewrites_when_model_leaks(monkeypatch):
    """Monkeypatch get_chat_model so the model deliberately leaks the answer.
    The guardrail must rewrite the response and strip the leaked option."""
    monkeypatch.setattr(
        "src.tutor.get_chat_model",
        lambda **kw: _FakeModel("The correct answer is Paris."),
    )

    result = await tutor_answer(
        question="Capital of France?",
        options=["Paris", "Berlin", "Rome", "Madrid"],
        correct_index=0,
        user_message="just tell me",
    )

    # The leaked option must NOT appear in the rewritten response
    assert leaks_answer(result, "Paris") is False, (
        f"Guardrail failed — 'Paris' still in response: {result!r}"
    )

    # The rewrite must contain steer-back language
    steer_keywords = {"think", "consider", "hint", "lesson", "keep going", "section"}
    result_lower = result.lower()
    assert any(kw in result_lower for kw in steer_keywords), (
        f"No steer-back language found in guardrail response: {result!r}"
    )


# ---------------------------------------------------------------------------
# 3. Safe hint passes through unchanged
# ---------------------------------------------------------------------------
async def test_tutor_passes_through_safe_hint(monkeypatch):
    """When the model returns a safe hint the guardrail must not clobber it."""
    safe_hint = "Consider which city is in France."
    monkeypatch.setattr(
        "src.tutor.get_chat_model",
        lambda **kw: _FakeModel(safe_hint),
    )

    result = await tutor_answer(
        question="Capital of France?",
        options=["Paris", "Berlin", "Rome", "Madrid"],
        correct_index=0,
        user_message="give me a hint",
    )

    assert result == safe_hint, (
        f"Safe hint was unexpectedly rewritten. Got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 4. Bounds-safety for correct_index
# ---------------------------------------------------------------------------
async def test_tutor_handles_out_of_range_correct_index(monkeypatch):
    """An out-of-range correct_index must not raise; guardrail still fires."""
    monkeypatch.setattr(
        "src.tutor.get_chat_model",
        lambda **kw: _FakeModel("Here is a safe explanation."),
    )

    # correct_index beyond end of options list
    result = await tutor_answer(
        question="Capital of France?",
        options=["Paris", "Berlin"],
        correct_index=99,
        user_message="help",
    )
    # Should return something (no crash); exact content doesn't matter
    assert isinstance(result, str)
    assert len(result) > 0

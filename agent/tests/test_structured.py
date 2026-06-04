"""
TDD tests for generate_structured — the retry-on-ValidationError helper.

Strategy: we do NOT use GenericFakeChatModel (it doesn't exist in this version of
langchain_core) and we do NOT call real model.bind_tools/with_structured_output.
Instead we inject a fake BaseChatModel subclass whose `with_structured_output`
returns a plain async Runnable we control.  This lets us:
  - prove the happy-path (valid result returned immediately)
  - prove the retry path (ValidationError on first call → valid result on second)
  - prove that exhausting all attempts re-raises the last ValidationError
"""
import pytest
from pydantic import BaseModel, ValidationError
from langchain_core.runnables import RunnableLambda
from langchain_core.language_models import BaseChatModel

from src.llm import generate_structured


# ---------------------------------------------------------------------------
# Schema under test
# ---------------------------------------------------------------------------
class Foo(BaseModel):
    name: str
    count: int


# ---------------------------------------------------------------------------
# Fake chat model factory
# ---------------------------------------------------------------------------
def _make_fake_model(stub_runnable):
    """
    Return a minimal BaseChatModel whose with_structured_output() yields
    the supplied stub_runnable (ignoring schema / method).

    We only override the abstract _generate (required) and with_structured_output.
    The real impl never gets called in these tests.
    """
    from langchain_core.outputs import ChatResult, ChatGeneration
    from langchain_core.messages import AIMessage

    class FakeChatModel(BaseChatModel):
        # Pydantic v2: suppress extra fields
        model_config = {"arbitrary_types_allowed": True}

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])

        @property
        def _llm_type(self) -> str:
            return "fake"

        def with_structured_output(self, schema, *, method="function_calling", **kwargs):
            return stub_runnable

    return FakeChatModel()


# ---------------------------------------------------------------------------
# Helper: build a ValidationError for Foo from scratch
# ---------------------------------------------------------------------------
def _foo_validation_error() -> ValidationError:
    try:
        Foo(name=123, count="not-an-int")  # type: ignore[arg-type]
    except ValidationError as e:
        return e
    raise AssertionError("expected ValidationError")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_generate_structured_happy_path():
    """Returns a valid Pydantic model on the first try."""
    valid_foo = Foo(name="hello", count=42)
    stub = RunnableLambda(lambda _: valid_foo)  # sync; ainvoke will wrap it

    fake_model = _make_fake_model(stub)
    result = await generate_structured("make a foo", Foo, model=fake_model)

    assert isinstance(result, Foo)
    assert result.name == "hello"
    assert result.count == 42


async def test_generate_structured_retries_on_validation_error():
    """First ainvoke raises ValidationError; second returns a valid Foo."""
    call_count = 0
    valid_foo = Foo(name="retry-success", count=7)
    err = _foo_validation_error()

    async def side_effect(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise err
        return valid_foo

    stub = RunnableLambda(side_effect)
    fake_model = _make_fake_model(stub)

    result = await generate_structured("make a foo", Foo, model=fake_model, attempts=3)

    assert call_count == 2
    assert isinstance(result, Foo)
    assert result.name == "retry-success"
    assert result.count == 7


async def test_generate_structured_raises_after_exhausting_attempts():
    """If every attempt raises ValidationError, the last error is re-raised."""
    err = _foo_validation_error()

    async def always_fail(prompt):
        raise err

    stub = RunnableLambda(always_fail)
    fake_model = _make_fake_model(stub)

    with pytest.raises(ValidationError):
        await generate_structured("make a foo", Foo, model=fake_model, attempts=3)


async def test_generate_structured_prompt_includes_error_on_retry():
    """After a ValidationError the retry prompt should mention the failure."""
    call_count = 0
    received_prompts: list[str] = []
    valid_foo = Foo(name="prompt-check", count=1)
    err = _foo_validation_error()

    async def capture(prompt):
        nonlocal call_count
        call_count += 1
        received_prompts.append(prompt)
        if call_count == 1:
            raise err
        return valid_foo

    stub = RunnableLambda(capture)
    fake_model = _make_fake_model(stub)

    await generate_structured("original prompt", Foo, model=fake_model, attempts=3)

    assert received_prompts[0] == "original prompt"
    assert "Previous output failed validation" in received_prompts[1]

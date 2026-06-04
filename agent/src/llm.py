"""LLM / provider layer.

Three public symbols:
  get_chat_model()     — OpenRouter primary + secondary fallback (both ChatOpenAI)
  generate_structured()— async structured-output helper with ValidationError retry
  get_embeddings()     — OpenRouter embeddings; falls back to local fastembed
"""
from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from src.settings import settings

# ---------------------------------------------------------------------------
# Chat factory
# ---------------------------------------------------------------------------

def _chat(model: str, **kw) -> ChatOpenAI:
    """Construct a ChatOpenAI pointed at OpenRouter.

    api_key defaults to "sk-noop" so construction never raises when the env
    var is absent — the real key is only needed at invoke time.
    """
    return ChatOpenAI(
        model=model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key or "sk-noop",
        temperature=kw.pop("temperature", 0.2),
        **kw,
    )


def get_chat_model(**kw) -> ChatOpenAI:
    """Primary OpenRouter model with a secondary OpenRouter model as fallback."""
    return _chat(settings.openrouter_model, **kw).with_fallbacks(
        [_chat(settings.openrouter_model_fallback, **kw)]
    )


# ---------------------------------------------------------------------------
# Structured-output helper
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=BaseModel)


async def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    model: BaseChatModel | None = None,
    attempts: int = 3,
    method: str = "function_calling",
) -> T:
    """Return a validated instance of *schema* from an LLM call.

    Uses ``with_structured_output(method=method)`` for widest model compat
    (``"function_calling"`` works on most OpenRouter-hosted models; switch to
    ``"json_schema"`` for models with native strict structured-output).

    Retries up to *attempts* times when the response fails Pydantic validation,
    appending the error detail to the prompt so the model can self-correct.
    Raises the last ``ValidationError`` after exhausting all attempts.
    """
    llm = model or get_chat_model()
    structured = llm.with_structured_output(schema, method=method)
    msg: str = prompt
    last: ValidationError | None = None
    for _ in range(attempts):
        try:
            return await structured.ainvoke(msg)
        except ValidationError as exc:
            last = exc
            msg = (
                f"{prompt}\n\n"
                f"Previous output failed validation: {exc}. Return valid data."
            )
    raise last  # type: ignore[misc]  # last is set because attempts >= 1


# ---------------------------------------------------------------------------
# Embeddings factory
# ---------------------------------------------------------------------------

def get_embeddings():
    """OpenRouter embeddings; fall back to local fastembed when no key is configured."""
    if settings.openrouter_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embed_model,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            dimensions=settings.embed_dimensions,
            check_embedding_ctx_length=False,  # bypass OpenAI tiktoken pre-chunking via gateway
        )
    from langchain_community.embeddings import FastEmbedEmbeddings

    return FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

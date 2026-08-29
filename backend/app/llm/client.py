"""Thin Google Gemini client for structured (JSON) generation.

Wraps ``google-genai``. Given a Pydantic ``response_schema`` it asks Gemini for
JSON and returns a validated model instance, with a manual json-parse fallback
if the SDK doesn't populate ``.parsed``.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(RuntimeError):
    """Raised when the LLM isn't configured (e.g. missing API key)."""


class LLMError(RuntimeError):
    """Raised when generation or parsing fails."""


@lru_cache(maxsize=1)
def _client():
    if not settings.gemini_api_key:
        raise LLMConfigError(
            "GEMINI_API_KEY is not set — configure it in .env to run reviews."
        )
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def generate_structured(
    *,
    prompt: str,
    system: str,
    schema: type[T],
    model: str | None = None,
    temperature: float = 0.2,
) -> T:
    """Call Gemini and return a validated instance of ``schema``."""
    from google.genai import types

    client = _client()
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
    )
    try:
        resp = client.models.generate_content(
            model=model or settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:  # network / API errors
        raise LLMError(f"Gemini request failed: {exc}") from exc

    # Preferred path: SDK already validated into our pydantic model.
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed

    # Fallback: parse the raw text ourselves.
    text = getattr(resp, "text", None)
    if not text:
        raise LLMError("Gemini returned an empty response")
    try:
        return schema.model_validate(json.loads(text))
    except Exception as exc:
        raise LLMError(f"Could not parse Gemini output as {schema.__name__}: {exc}") from exc

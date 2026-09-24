"""
gemini.py — Minimal Gemini REST client (JSON-mode generateContent).

Uses the REST API directly rather than the pinned google-generativeai SDK.
Key: GEMINI_API_KEY (or GEMINI_KEY) in .env. Models: GEMINI_MODEL (comma-separated) or the default
chain below — on quota (429), overload (5xx) or timeout the next model is tried.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_DEFAULT_MODELS = ("gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-flash-latest")
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    pass


class _Retryable(GeminiError):
    pass


def generate_json(prompt: str, schema: dict, model: Optional[str] = None, timeout: float = 30) -> dict:
    """
    Send `prompt`, get back a dict matching the OpenAPI-style `schema`.
    Tries `model`, else each model in the chain. Raises GeminiError if none answers.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")
    if not api_key:
        raise GeminiError("No Gemini key — set GEMINI_API_KEY in .env")

    configured = os.getenv("GEMINI_MODEL")
    models = [model] if model else ([m.strip() for m in configured.split(",")] if configured else _DEFAULT_MODELS)
    errors = []
    for name in models:
        try:
            return _generate(name, api_key, prompt, schema, timeout)
        except _Retryable as e:
            errors.append(f"{name}: {e}")
    raise GeminiError("; ".join(errors))


def _generate(model: str, api_key: str, prompt: str, schema: dict, timeout: float) -> dict:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    request = urllib.request.Request(
        _ENDPOINT.format(model=model),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        error = _Retryable if e.code in _RETRYABLE_HTTP else GeminiError
        raise error(f"HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise _Retryable(f"unreachable: {e}") from e

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GeminiError(f"Unexpected Gemini response: {str(data)[:300]}") from e

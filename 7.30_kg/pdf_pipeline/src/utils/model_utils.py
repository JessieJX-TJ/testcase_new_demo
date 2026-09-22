from __future__ import annotations

import base64
import time
import os
from pathlib import Path
from typing import Any, Callable

try:
    # OpenAI >= 1.x client
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - optional at import time
    OpenAI = None  # type: ignore


def encode_image_base64(image_path: Path) -> str:
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_with_retry(func: Callable[[], Any], max_retries: int = 3, sleep_seconds: float = 2.0) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(sleep_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Model call failed without exception")


def extract_multimodal_text(response: Any) -> str:
    # OpenAI chat.completions style
    try:
        return response.choices[0].message.content  # type: ignore[attr-defined]
    except Exception:
        pass
    # Fallback to dict-like
    if isinstance(response, dict):
        try:
            return str(response["choices"][0]["message"]["content"])  # type: ignore[index]
        except Exception:
            pass
    raise ValueError("Unable to parse chat response text")


def extract_generation_text(response: Any) -> str:
    # Same as chat for OpenAI-compatible usage in this project
    return extract_multimodal_text(response)


def get_api_client(config: dict[str, Any]) -> Any:
    provider = (
        config.get("api", {}).get("provider")
        or os.environ.get("API_PROVIDER")
        or "openai_compatible"
    )
    if provider == "openai_compatible":
        if OpenAI is None:
            raise RuntimeError("openai package is required for openai_compatible provider. Please install 'openai'.")
        base_url = config.get("api", {}).get(
            "base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not set in environment.")
        return OpenAI(api_key=api_key, base_url=base_url)
    raise NotImplementedError(f"Unsupported api.provider: {provider}")


def openai_chat_multimodal(client: Any, model: str, image_b64: str, prompt_text: str) -> Any:
    data_url = f"data:image/jpeg;base64,{image_b64}"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]
    return client.chat.completions.create(model=model, messages=messages)


def openai_chat_text(client: Any, model: str, prompt_text: str) -> Any:
    messages = [
        {
            "role": "user",
            "content": prompt_text,
        }
    ]
    return client.chat.completions.create(model=model, messages=messages)

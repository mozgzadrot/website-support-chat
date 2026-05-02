"""
llm.py — OpenRouter streaming client.

Yields text tokens from the OpenRouter chat completions endpoint
using the streaming API (SSE).
"""

import json
import logging
from collections.abc import Generator

import requests

from config import cfg

logger = logging.getLogger(__name__)


def stream_completion(
    messages: list[dict],
    model: str | None = None,
) -> Generator[str, None, None]:
    """
    Stream a chat completion from OpenRouter.

    Args:
        messages:  Full messages array (system + history + user).
        model:     Override the configured model (optional).

    Yields:
        Text delta strings as they arrive.

    Raises:
        RuntimeError if the HTTP request itself fails (caller handles).
    """
    chosen_model = model or cfg.OPENROUTER_MODEL
    url = f"{cfg.OPENROUTER_BASE_URL}/chat/completions"

    headers = {
        "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # OpenRouter attribution headers (required by their ToS)
        "HTTP-Referer": cfg.SITE_URL,
        "X-Title": cfg.APP_NAME,
    }

    payload = {
        "model": chosen_model,
        "messages": messages,
        "stream": True,
    }

    logger.debug("Calling OpenRouter model=%s, messages=%d", chosen_model, len(messages))

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=60) as resp:
        if resp.status_code != 200:
            body = resp.text[:500]
            logger.error("OpenRouter HTTP %d: %s", resp.status_code, body)
            raise RuntimeError(f"OpenRouter returned HTTP {resp.status_code}: {body}")

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line: str = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

            if not line.startswith("data:"):
                continue

            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Could not parse SSE chunk: %s", data[:100])
                continue

            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta

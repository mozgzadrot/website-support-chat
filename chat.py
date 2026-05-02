"""
chat.py — Orchestration layer: cache → RAG → LLM → store.

`handle_chat` is a generator that yields SSE-formatted strings.
It is consumed by the Flask route in app.py.
"""

import json
import logging
import time
from collections.abc import Generator
from pathlib import Path

import numpy as np

from cache import lookup as cache_lookup, record_hit, store as cache_store
from config import cfg
from db import get_connection
from embeddings import embed_text
from llm import stream_completion
from retriever import retrieve, format_context

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path("prompts/system.md")
FALLBACK_MESSAGE = (
    "Sorry — I'm having trouble reaching my brain right now. "
    "Try again in a moment."
)


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    logger.warning("System prompt not found at %s; using bare fallback.", SYSTEM_PROMPT_PATH)
    return "You are a helpful assistant. Use the following context:\n\n{kb_context}"


def _persist_turn(session_id: str, role: str, content: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()


def _get_history(session_id: str, max_turns: int) -> list[dict]:
    """
    Return the last `max_turns` conversation turns (user+assistant pairs).
    max_turns refers to *pairs*, so we fetch 2*max_turns rows.
    """
    limit = max_turns * 2
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    # Rows are newest-first; reverse to get chronological order
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _sse(event: str | None, data: str) -> str:
    """
    Format a single SSE message.

    Token payloads (event is None) are JSON-encoded so newlines and other
    control characters survive the SSE transport intact. Named events
    (meta, done) keep their literal payload — meta is already JSON, and
    done has an empty body.
    """
    if event:
        return f"event: {event}\ndata: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


def handle_chat(message: str, session_id: str) -> Generator[str, None, None]:
    """
    Main chat generator. Yields SSE-formatted strings.

    Flow:
      1. Persist user turn.
      2. Embed the message (single pass, reused for cache + retrieval).
      3. Cache check  → stream cached answer if hit.
      4. RAG retrieval.
      5. Build prompt (system + history + user).
      6. Stream from OpenRouter.
      7. Persist assistant turn + store in cache.
      8. Yield done event.
    """
    # 1. Persist user turn
    _persist_turn(session_id, "user", message)

    # 2. Embed once
    query_vec: np.ndarray = embed_text(message)

    # 3. Cache lookup
    hit = cache_lookup(query_vec)
    if hit:
        yield _sse("meta", '{"cached": true}')
        # Simulate streaming: chunked replay with small delay
        words = hit.answer.split(" ")
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            token = " ".join(words[i : i + chunk_size])
            if i + chunk_size < len(words):
                token += " "
            yield _sse(None, token)
            time.sleep(0.03)
        record_hit(hit.id)
        _persist_turn(session_id, "assistant", hit.answer)
        yield _sse("done", "")
        return

    # 4. RAG retrieval
    chunks = retrieve(query_vec)
    kb_context = format_context(chunks)
    logger.info("RAG: %d chunks retrieved for session=%s", len(chunks), session_id)

    # 5. Build prompt
    system_template = _load_system_prompt()
    system_content = system_template.replace("{kb_context}", kb_context)

    history = _get_history(session_id, cfg.MAX_HISTORY_TURNS)
    # Remove the turn we just persisted (it's the last user message we're about to send)
    if history and history[-1]["role"] == "user" and history[-1]["content"] == message:
        history = history[:-1]

    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    # 6. Stream from OpenRouter
    full_answer: list[str] = []
    try:
        for token in stream_completion(messages):
            full_answer.append(token)
            yield _sse(None, token)
    except Exception as exc:
        logger.error("LLM streaming error: %s", exc, exc_info=True)
        yield _sse("meta", '{"error": true}')
        yield _sse(None, FALLBACK_MESSAGE)
        yield _sse("done", "")
        _persist_turn(session_id, "assistant", FALLBACK_MESSAGE)
        return

    answer = "".join(full_answer)

    # 7. Persist + cache
    _persist_turn(session_id, "assistant", answer)
    if answer.strip():
        cache_store(message, answer, query_vec)

    # 8. Done
    yield _sse("done", "")

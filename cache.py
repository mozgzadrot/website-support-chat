"""
cache.py — Semantic response cache: lookup and write.

On lookup: compare query embedding against all cached question embeddings.
On write:  store (question, answer, embedding) after a fresh LLM response.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from config import cfg
from db import get_connection
from embeddings import cosine_similarity_matrix, blob_to_vec, vec_to_blob

logger = logging.getLogger(__name__)


@dataclass
class CacheHit:
    id: int
    question: str
    answer: str
    score: float


def lookup(query_vec: np.ndarray, threshold: float | None = None) -> CacheHit | None:
    """
    Check whether a semantically near-identical question has been answered before.

    Returns a CacheHit if the best match meets (or exceeds) the threshold,
    otherwise returns None.
    """
    t = threshold if threshold is not None else cfg.CACHE_SIMILARITY_THRESHOLD

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, question, answer, embedding FROM response_cache"
        ).fetchall()

    if not rows:
        return None

    ids = [r["id"] for r in rows]
    questions = [r["question"] for r in rows]
    answers = [r["answer"] for r in rows]
    matrix = np.stack([blob_to_vec(r["embedding"]) for r in rows])  # (N, dim)

    scores = cosine_similarity_matrix(query_vec, matrix)  # (N,)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    if best_score >= t:
        logger.info(
            "Cache HIT (score=%.4f, threshold=%.2f): '%s'",
            best_score, t, questions[best_idx][:80],
        )
        return CacheHit(
            id=ids[best_idx],
            question=questions[best_idx],
            answer=answers[best_idx],
            score=best_score,
        )

    logger.debug("Cache MISS (best score=%.4f, threshold=%.2f)", best_score, t)
    return None


def record_hit(cache_id: int) -> None:
    """Increment hit_count and update last_used_at for a cache entry."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE response_cache SET hit_count = hit_count + 1, last_used_at = ? WHERE id = ?",
            (now, cache_id),
        )
        conn.commit()


def store(question: str, answer: str, question_vec: np.ndarray) -> None:
    """Persist a new (question, answer) pair to the response cache."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO response_cache (question, answer, embedding) VALUES (?, ?, ?)",
            (question, answer, vec_to_blob(question_vec)),
        )
        conn.commit()
    logger.debug("Stored new cache entry for: '%s'", question[:80])

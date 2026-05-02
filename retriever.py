"""
retriever.py — Top-k KB section retrieval using cosine similarity.

Loads all KB chunk embeddings into a numpy matrix at startup for fast in-memory
cosine search (suitable for POC scale; swap to sqlite-vec if needed later).
"""

import logging
from dataclasses import dataclass

import numpy as np

from config import cfg
from db import get_connection
from embeddings import cosine_similarity_matrix, blob_to_vec

logger = logging.getLogger(__name__)


@dataclass
class KBChunk:
    id: int
    heading: str
    keywords: str
    content: str
    score: float


def retrieve(query_vec: np.ndarray, top_k: int | None = None, min_score: float | None = None) -> list[KBChunk]:
    """
    Return the top-k KB chunks most similar to query_vec,
    filtered by min_score threshold.

    Args:
        query_vec:  float32 embedding of the query (already normalised).
        top_k:      max results to return (defaults to cfg.RAG_TOP_K).
        min_score:  minimum cosine similarity (defaults to cfg.RAG_MIN_SCORE).

    Returns:
        List of KBChunk sorted by score descending.
    """
    k = top_k if top_k is not None else cfg.RAG_TOP_K
    threshold = min_score if min_score is not None else cfg.RAG_MIN_SCORE

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, heading, keywords, content, embedding FROM kb_chunks"
        ).fetchall()

    if not rows:
        logger.warning("KB is empty — run indexer.py first.")
        return []

    # Build matrix (N, dim) from stored BLOBs
    ids = [r["id"] for r in rows]
    headings = [r["heading"] for r in rows]
    keywords_list = [r["keywords"] or "" for r in rows]
    contents = [r["content"] for r in rows]
    matrix = np.stack([blob_to_vec(r["embedding"]) for r in rows])  # (N, dim)

    scores = cosine_similarity_matrix(query_vec, matrix)  # (N,)

    # Apply threshold and take top-k
    candidates = [
        (int(ids[i]), headings[i], keywords_list[i], contents[i], float(scores[i]))
        for i in range(len(ids))
        if scores[i] >= threshold
    ]
    candidates.sort(key=lambda x: x[4], reverse=True)
    candidates = candidates[:k]

    logger.debug(
        "Retrieved %d/%d KB chunks (threshold=%.2f, top_k=%d)",
        len(candidates), len(ids), threshold, k,
    )

    return [
        KBChunk(id=c[0], heading=c[1], keywords=c[2], content=c[3], score=c[4])
        for c in candidates
    ]


def format_context(chunks: list[KBChunk]) -> str:
    """
    Format retrieved chunks as a KB context block for the system prompt.
    Uses heading + content only (no keyword pollution in the prompt).
    """
    if not chunks:
        return "(no relevant knowledge base sections found)"
    parts = [f"## {c.heading}\n{c.content}" for c in chunks]
    return "\n\n---\n\n".join(parts)

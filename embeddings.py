"""
embeddings.py — Singleton sentence-transformer model + cosine similarity helpers.

The model is loaded ONCE at app startup (or first import during indexing).
All other modules import `embed_text` and `cosine_similarity` from here.
"""

import logging
from functools import lru_cache
from typing import Union

import numpy as np
from sentence_transformers import SentenceTransformer

from config import cfg

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Return the singleton embedding model, loading it on first call."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", cfg.EMBEDDING_MODEL)
        _model = SentenceTransformer(cfg.EMBEDDING_MODEL)
        logger.info("Embedding model ready (dim=%d)", _model.get_sentence_embedding_dimension())
    return _model


def embed_text(text: str) -> np.ndarray:
    """
    Embed a single string and return a float32 numpy array.
    The model normalises embeddings by default (L2=1), making cosine sim == dot product.
    """
    model = get_model()
    vec = model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
    return vec.astype(np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Batch-embed multiple strings. Returns shape (N, dim) float32 array.
    More efficient than calling embed_text() in a loop.
    """
    model = get_model()
    vecs = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=32)
    return vecs.astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two 1-D float32 vectors.
    Since embeddings are L2-normalised, this is simply a dot product.
    """
    return float(np.dot(a, b))


def cosine_similarity_matrix(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Cosine similarity between a query vector (dim,) and a matrix (N, dim).
    Returns a 1-D array of shape (N,) with scores in [-1, 1].
    """
    # matrix rows are already normalised, so dot product == cosine sim
    return matrix @ query


def blob_to_vec(blob: bytes) -> np.ndarray:
    """Deserialise a DB BLOB back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def vec_to_blob(vec: np.ndarray) -> bytes:
    """Serialise a float32 numpy array to bytes for DB storage."""
    return vec.astype(np.float32).tobytes()

"""
config.py — Environment-driven configuration.
Load once at import time; everything else imports `cfg`.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # OpenRouter
    OPENROUTER_API_KEY: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    OPENROUTER_MODEL: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4-5"))
    OPENROUTER_BASE_URL: str = field(default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))

    # App identity (used in OpenRouter attribution headers)
    SITE_URL: str = field(default_factory=lambda: os.getenv("SITE_URL", "http://localhost:5000"))
    APP_NAME: str = field(default_factory=lambda: os.getenv("APP_NAME", "Demo Chat"))

    # Embedding model
    EMBEDDING_MODEL: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))

    # RAG / cache tuning
    CACHE_SIMILARITY_THRESHOLD: float = field(
        default_factory=lambda: float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))
    )
    RAG_TOP_K: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "4")))
    RAG_MIN_SCORE: float = field(default_factory=lambda: float(os.getenv("RAG_MIN_SCORE", "0.35")))
    MAX_HISTORY_TURNS: int = field(default_factory=lambda: int(os.getenv("MAX_HISTORY_TURNS", "6")))

    # Storage
    DB_PATH: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/chat.db"))

    # Logging
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    FLASK_ENV: str = field(default_factory=lambda: os.getenv("FLASK_ENV", "development"))


cfg = Config()

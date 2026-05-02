"""
scripts/clear_cache.py — Wipe response_cache only.
Preserves KB chunks and conversation history.

Usage:
    python scripts/clear_cache.py
"""

import sys
from pathlib import Path

# Allow running from the project root or from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import get_connection
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def clear_response_cache() -> int:
    """Delete all rows from response_cache. Returns rows deleted."""
    with get_connection() as conn:
        result = conn.execute("DELETE FROM response_cache")
        deleted = result.rowcount
        conn.commit()
    return deleted


if __name__ == "__main__":
    n = clear_response_cache()
    print(f"Cleared {n} cached response(s) from response_cache.")

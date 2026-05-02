"""
indexer.py — Parse a KB HTML file, build embeddings, and write to SQLite.

CLI usage:
    python indexer.py data/knowledge.html

Re-running fully replaces existing rows for the same source file.
"""

import logging
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from db import get_connection, bootstrap_schema
from embeddings import embed_texts, vec_to_blob

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_kb(html_path: Path) -> list[dict]:
    """
    Parse a KB HTML file into a list of chunk dicts.

    Each <section> in the file becomes one chunk:
      - heading:  text of first <h1>–<h3> child
      - keywords: data-keywords attribute (comma-separated, optional)
      - content:  all paragraph text within the section
    """
    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    chunks: list[dict] = []

    for section in soup.find_all("section"):
        # Heading — first heading tag found directly inside the section
        heading_tag = section.find(["h1", "h2", "h3", "h4"])
        heading = heading_tag.get_text(strip=True) if heading_tag else "Untitled"

        # Keywords (optional)
        keywords: str = section.get("data-keywords", "") or ""

        # Content — all text except the heading itself
        if heading_tag:
            heading_tag.extract()
        content = section.get_text(separator=" ", strip=True)

        if not content:
            logger.warning("Skipping empty section: '%s'", heading)
            continue

        chunks.append(
            {
                "heading": heading,
                "keywords": keywords.strip(),
                "content": content,
            }
        )

    return chunks


def build_embed_texts(chunks: list[dict]) -> list[str]:
    """
    Build the enriched text fed to the embedding model.
    Format: heading | keywords | content  (keywords omitted if absent)
    """
    texts: list[str] = []
    for c in chunks:
        parts = [c["heading"]]
        if c["keywords"]:
            parts.append(c["keywords"])
        parts.append(c["content"])
        texts.append(" | ".join(parts))
    return texts


def index_file(html_path: Path) -> int:
    """
    Index (or re-index) a single KB HTML file.
    Returns the number of sections indexed.
    """
    bootstrap_schema()
    source_file = str(html_path)

    chunks = parse_kb(html_path)
    if not chunks:
        logger.warning("No <section> elements found in %s", html_path)
        return 0

    logger.info("Embedding %d sections from %s …", len(chunks), html_path.name)
    embed_inputs = build_embed_texts(chunks)
    embeddings = embed_texts(embed_inputs)  # shape (N, dim)

    with get_connection() as conn:
        # Replace all existing rows for this source file
        conn.execute("DELETE FROM kb_chunks WHERE source_file = ?", (source_file,))

        rows = [
            (
                c["heading"],
                c["keywords"] or None,
                c["content"],
                vec_to_blob(embeddings[i]),
                source_file,
            )
            for i, c in enumerate(chunks)
        ]
        conn.executemany(
            "INSERT INTO kb_chunks (heading, keywords, content, embedding, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    logger.info("Indexed %d sections from %s", len(chunks), html_path.name)
    return len(chunks)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python indexer.py <path/to/knowledge.html>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    n = index_file(path)
    print(f"Indexed {n} sections from {path}")

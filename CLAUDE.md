# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Zephyr Chat Widget POC — a Flask-based website chat widget that combines OpenRouter (streaming LLM), sentence-transformer RAG over an HTML knowledge base, and a semantic response cache, all backed by SQLite.

## Common commands

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # then set OPENROUTER_API_KEY

# Index (or re-index) a knowledge base HTML file
python indexer.py data/knowledge.html

# Run dev server (http://localhost:5000)
python app.py

# Wipe the response cache (keeps KB and conversation history)
python scripts/clear_cache.py
```

There is no test suite, linter, or build step configured.

## Architecture

Request flow for `POST /api/chat` (SSE stream):

1. `app.py` receives the request and delegates to `chat.handle_chat`, a generator that yields SSE-formatted strings.
2. `chat.handle_chat` persists the user turn, then **embeds the message once** via `embeddings.embed_text` and reuses that vector for both cache lookup and KB retrieval.
3. `cache.lookup` does a cosine-similarity scan over `response_cache`. On a hit (≥ `CACHE_SIMILARITY_THRESHOLD`), the cached answer is replayed in chunks with a fake stream delay and a `meta {"cached": true}` event; no LLM call is made.
4. On miss, `retriever.retrieve` cosine-scans `kb_chunks`, filters by `RAG_MIN_SCORE`, and takes top `RAG_TOP_K`. `retriever.format_context` renders them as markdown sections.
5. `chat.handle_chat` builds the message list: system prompt from `prompts/system.md` (with `{kb_context}` substituted) + last `MAX_HISTORY_TURNS` pairs from `conversations` + new user message.
6. `llm.stream_completion` POSTs to OpenRouter with `stream=True` and yields text deltas parsed from the SSE response.
7. Tokens are streamed to the client, then the assistant turn is persisted and `cache.store` saves `(question, answer, embedding)`.

### Key invariants

- **Single embedding model, loaded once.** `embeddings.get_model` is a module-level singleton, warmed up at app startup in `app.startup()`. All embeddings (KB chunks, cached questions, queries) must come from the same model — switching `EMBEDDING_MODEL` requires re-indexing the KB **and** clearing the cache.
- **Embeddings are L2-normalised** at encoding time (`normalize_embeddings=True`), so cosine similarity is just a dot product. `cosine_similarity_matrix` relies on this.
- **All DB access goes through `db.get_connection()`** — SQLite with WAL mode and foreign keys on. Schema is created idempotently by `db.bootstrap_schema()`.
- **Embeddings are stored as raw float32 BLOBs** via `vec_to_blob` / `blob_to_vec`. There is no sqlite-vec dependency; retrieval loads all rows into a numpy matrix per request (fine at POC scale).
- **Indexer is idempotent per source file**: `indexer.index_file` deletes existing `kb_chunks` rows for that `source_file` before inserting, but leaves chunks from other source files alone. Multiple HTML files can be indexed independently.

### KB document format

`indexer.parse_kb` expects each topic wrapped in a `<section>` with a heading tag (`h1`–`h4`). Optional `data-keywords="..."` on the section is concatenated into the embedding input (heading | keywords | content) but not into the prompt context.

### SSE protocol (client contract)

- `event: meta` — JSON metadata, e.g. `{"cached": true}` or `{"error": true}`
- `data: <token>` — text deltas (no event name)
- `event: done` — stream finished

## Configuration

All config is read once from `.env` into `config.cfg` (see `config.py`). Notable knobs: `CACHE_SIMILARITY_THRESHOLD` (default 0.92), `RAG_TOP_K` (4), `RAG_MIN_SCORE` (0.35), `MAX_HISTORY_TURNS` (6 pairs), `OPENROUTER_MODEL`, `EMBEDDING_MODEL`, `DB_PATH` (default `data/chat.db`).

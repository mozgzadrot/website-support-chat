# Zephyr Chat Widget POC

A proof-of-concept website chat widget powered by Flask, OpenRouter (streaming LLM), sentence-transformer RAG, and a semantic response cache — all backed by SQLite.

## Architecture at a glance

```
Browser widget (SSE)
    └── Flask /api/chat
            ├── embed query (sentence-transformers, one pass)
            ├── cache.py    → cosine sim vs response_cache
            │   └── HIT  → stream cached answer, return
            ├── retriever.py → cosine sim vs kb_chunks → top-k sections
            ├── chat.py     → build messages (system + history + user)
            ├── llm.py      → OpenRouter streaming
            └── store result in response_cache + conversations
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 + |
| pip | any recent |
| OpenRouter API key | [openrouter.ai/keys](https://openrouter.ai/keys) |

No database server required — SQLite is bundled with Python.

---

## Setup

```bash
# 1. Clone / unzip the project
cd chatwidget

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and fill in OPENROUTER_API_KEY=sk-or-...

# 5. Index the sample knowledge base
python indexer.py data/knowledge.html
# Expected output: Indexed 6 sections from knowledge.html

# 6. Start the development server
python app.py
# Listening on http://0.0.0.0:5000
```

Open **http://localhost:5000** in your browser. Click the chat bubble in the bottom-right corner.

---

## Manual Smoke Tests

### (a) Question covered by the KB
> **You:** "What are your pricing plans?"

**Expected:** Zeph describes the Free, Starter, Pro, and Business plans with prices. No hallucination.

---

### (b) Same question rephrased — should get ⚡ instant badge
> **You:** "How much does Zephyr cost per month?"

**Expected:** The response arrives quickly with a ⚡ **instant** badge next to the answer. This means the semantic cache matched the previous question (cosine sim ≥ 0.92) and bypassed OpenRouter entirely.

If the badge doesn't appear, the paraphrase wasn't similar enough. You can lower `CACHE_SIMILARITY_THRESHOLD` in `.env` (e.g. `0.88`) and restart the server.

---

### (c) Question NOT in the KB
> **You:** "Can I import data from Notion?"

**Expected:** Zeph politely says it doesn't have that information and offers to connect you with the support team at support@zephyr.io. It should **not** invent an answer.

---

### (d) Follow-up that requires conversation history
> **You:** "Tell me about your Pro plan."
> **You:** "Does it include SSO?"

**Expected:** The second answer references SSO in the context of the Pro plan, demonstrating the assistant is using conversation history (not treating the second message as standalone).

---

## Swapping the Knowledge Base

1. Write a new HTML file following the format in `data/knowledge.html`:
   - Wrap each topic in a `<section>` tag.
   - Add a heading (`<h2>`) inside each section.
   - Optionally add `data-keywords="comma,separated,synonyms"` to the `<section>` tag.

2. Re-run the indexer:
   ```bash
   python indexer.py path/to/your-kb.html
   ```
   This replaces all existing chunks for that source file but keeps chunks from other source files.

3. Restart the Flask server (embeddings are cached in memory at startup).

You can index **multiple** HTML files — run the indexer once per file. All chunks end up in `kb_chunks` and are searched together.

---

## Tuning the Cache Threshold

`CACHE_SIMILARITY_THRESHOLD` (default `0.92`) controls how similar an incoming question must be to a cached one before the cache is used.

| Value | Effect |
|---|---|
| `0.96+` | Very strict — only near-exact rephrases hit the cache |
| `0.92` | Default — catches obvious paraphrases |
| `0.85–0.88` | Aggressive — broader matches, risk of false positives |
| `< 0.80` | Not recommended — semantically different questions may collide |

After changing the threshold in `.env`, restart the server. No re-indexing required.

To inspect or wipe the cache:
```bash
python scripts/clear_cache.py
```

---

## Switching Embedding Model

Edit `EMBEDDING_MODEL` in `.env`:

| Model | Size | Speed | Quality |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | ~130 MB | Fast | Good |
| `BAAI/bge-m3` | ~570 MB | Slower | Excellent (multilingual) |

**Important:** After changing the embedding model, you must re-index the KB **and** clear the cache:
```bash
python scripts/clear_cache.py
python indexer.py data/knowledge.html
```
This is because cached and KB embeddings must all come from the same model to be comparable.

---

## Adding CORS (cross-origin embedding)

If you embed the widget on a different domain, uncomment and install flask-cors in `app.py`:

```python
from flask_cors import CORS
CORS(app, resources={r"/api/*": {"origins": "https://yoursite.com"}})
```

Add `flask-cors` to `requirements.txt`.

---

## CLI Reference

| Command | Description |
|---|---|
| `python indexer.py data/knowledge.html` | (Re)build KB index from an HTML file |
| `python app.py` | Run dev server on port 5000 |
| `python scripts/clear_cache.py` | Wipe response cache (keeps KB and history) |

---

## Troubleshooting

### OpenRouter 401 Unauthorized
- Verify `OPENROUTER_API_KEY` in `.env` is set and has no leading/trailing spaces.
- Check your key at [openrouter.ai/keys](https://openrouter.ai/keys).
- Ensure the key has credits/balance.

### sqlite-vec not available
The app falls back to in-memory numpy cosine similarity automatically. You'll see this log line at startup:

```
WARNING  sqlite_vec extension not available, using numpy fallback
```

This is fine for POC scale (hundreds to low thousands of KB chunks). No action needed.

### Embedding model download is slow
The model is downloaded from Hugging Face on first run (~130 MB for bge-small). Subsequent runs use the cached version in `~/.cache/huggingface/`. Set `HF_HUB_OFFLINE=1` to prevent network calls once cached.

### Widget not streaming / blank responses
- Open browser DevTools → Network → look for `/api/chat` request.
- Check the Flask server console for error logs.
- Make sure `FLASK_ENV=development` is set so Flask shows tracebacks.

### "No relevant knowledge base sections found"
- Ensure you ran `python indexer.py data/knowledge.html` at least once.
- Check `data/chat.db` exists and has rows: `sqlite3 data/chat.db "SELECT COUNT(*) FROM kb_chunks;"`.
- Lower `RAG_MIN_SCORE` in `.env` (default 0.35) if questions are too dissimilar from KB content.

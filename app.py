"""
app.py — Flask application: routes and SSE streaming endpoint.

Run with:  python app.py
"""

import logging
import sys

from flask import Flask, Response, render_template, request, jsonify, stream_with_context

from config import cfg
from db import bootstrap_schema
from embeddings import get_model  # warm up at startup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# CORS note: add flask-cors here if the widget is later embedded cross-origin.
# Example:
#   from flask_cors import CORS
#   CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.route("/")
def index() -> str:
    """Serve the landing page with the embedded chat widget."""
    return render_template("index.html", app_name=cfg.APP_NAME)


@app.route("/api/chat", methods=["POST"])
def chat() -> Response:
    """
    SSE streaming endpoint.

    Expects JSON body: { "message": str, "session_id": str }

    Streams:
      event: meta   — JSON metadata (e.g., {"cached": true})
      data: <token> — individual text tokens
      event: done   — stream finished
    """
    body = request.get_json(silent=True) or {}
    message: str = (body.get("message") or "").strip()
    session_id: str = (body.get("session_id") or "anonymous").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400

    logger.info("Chat request: session=%s, message=%s", session_id, message[:80])

    from chat import handle_chat  # local import to keep startup fast

    def generate():
        yield from handle_chat(message, session_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind a proxy
        },
    )


@app.route("/api/health")
def health() -> Response:
    """Simple health check."""
    return jsonify({"status": "ok", "app": cfg.APP_NAME})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def startup() -> None:
    """Initialise DB schema and warm up the embedding model."""
    bootstrap_schema()
    logger.info("Warming up embedding model …")
    get_model()  # loads model into memory once; all requests reuse it
    logger.info("App ready — %s", cfg.APP_NAME)


startup()

if __name__ == "__main__":
    app.run(debug=(cfg.FLASK_ENV == "development"), host="0.0.0.0", port=5000)

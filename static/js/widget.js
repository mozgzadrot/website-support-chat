/**
 * widget.js — Zephyr chat widget
 *
 * Features:
 *  - UUID session stored in localStorage
 *  - SSE streaming from /api/chat
 *  - ⚡ instant badge for cached responses
 *  - Typing indicator while waiting for first token
 *  - Enter to send, Shift+Enter for newline
 *  - Auto-scroll on new content
 */

(function () {
  "use strict";

  // ── Session ID ──────────────────────────────────────────────────
  const SESSION_KEY = "chat_session_id";

  function getOrCreateSessionId() {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID
        ? crypto.randomUUID()
        : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
            const r = (Math.random() * 16) | 0;
            return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
          });
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  const SESSION_ID = getOrCreateSessionId();

  // ── DOM References ──────────────────────────────────────────────
  const launcher = document.getElementById("chat-launcher");
  const widget = document.getElementById("chat-widget");
  const messages = document.getElementById("chat-messages");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");

  if (!launcher || !widget || !messages || !input || !sendBtn) {
    console.warn("[Zephyr Widget] Required DOM elements not found.");
    return;
  }

  // ── Toggle Widget ───────────────────────────────────────────────
  launcher.addEventListener("click", () => {
    const isOpen = widget.classList.toggle("is-open");
    launcher.classList.toggle("is-open", isOpen);
    launcher.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) {
      input.focus();
      scrollToBottom();
    }
  });

  document.getElementById("chat-close-btn")?.addEventListener("click", () => {
    widget.classList.remove("is-open");
    launcher.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
  });

  // ── Message Helpers ─────────────────────────────────────────────
  function scrollToBottom(smooth = true) {
    messages.scrollTo({ top: messages.scrollHeight, behavior: smooth ? "smooth" : "instant" });
  }

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "msg-row user";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = text;
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollToBottom();
    return row;
  }

  function createBotMessageRow() {
    const row = document.createElement("div");
    row.className = "msg-row bot";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = "";
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollToBottom();
    return { row, bubble };
  }

  function showTypingIndicator() {
    const row = document.createElement("div");
    row.className = "msg-row bot";
    row.id = "typing-indicator-row";
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.innerHTML = "<span></span><span></span><span></span>";
    row.appendChild(indicator);
    messages.appendChild(row);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    document.getElementById("typing-indicator-row")?.remove();
  }

  function addCachedBadge(bubble) {
    const badge = document.createElement("div");
    badge.className = "msg-badge";
    badge.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> instant`;
    bubble.appendChild(badge);
  }

  // ── Send Message ────────────────────────────────────────────────
  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    input.style.height = "";
    sendBtn.disabled = true;

    appendUserMessage(text);
    showTypingIndicator();

    let isCached = false;
    let firstToken = true;
    let botBubble = null;

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: SESSION_ID }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          // Parse SSE event type
          if (trimmed.startsWith("event:")) {
            const eventName = trimmed.slice(6).trim();
            if (eventName === "done") {
              // Stream complete
            }
            continue;
          }

          if (trimmed.startsWith("data:")) {
            const raw = trimmed.slice(5); // preserve leading space if any

            // Check if it's a meta JSON object
            if (raw.trim().startsWith("{")) {
              try {
                const meta = JSON.parse(raw.trim());
                if (meta.cached) isCached = true;
              } catch (_) {}
              continue;
            }

            const token = raw; // space-prefixed token from SSE "data: token"

            if (firstToken) {
              removeTypingIndicator();
              const created = createBotMessageRow();
              botBubble = created.bubble;
              firstToken = false;
            }

            if (botBubble) {
              // Append text node to avoid XSS
              const existing = botBubble.childNodes[0];
              if (existing && existing.nodeType === Node.TEXT_NODE) {
                existing.nodeValue += token;
              } else {
                botBubble.insertBefore(document.createTextNode(token), botBubble.firstChild);
              }
              scrollToBottom();
            }
          }
        }
      }

      // Add cached badge after stream ends
      if (isCached && botBubble) {
        addCachedBadge(botBubble);
      }
    } catch (err) {
      console.error("[Zephyr Widget] Stream error:", err);
      removeTypingIndicator();
      const { bubble } = createBotMessageRow();
      bubble.textContent =
        "Sorry — something went wrong. Please try again in a moment.";
      bubble.style.color = "#dc2626";
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // ── Input Events ────────────────────────────────────────────────
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener("click", sendMessage);

  // Auto-resize textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  });
})();

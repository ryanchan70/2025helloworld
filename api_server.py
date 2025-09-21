# api_server.py
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

from HIM import (
    ChatLog, build_model, to_chat_history_for_gemini, load_api_key
)

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parent

# No static folder; we serve files from the current folder explicitly
app = Flask(__name__, static_folder=None)

# Init model + storage once
api_key = load_api_key()
model = build_model(api_key)          # If model error: set MODEL_NAME="gemini-1.5-flash" in therapist_chatbot.py
store = ChatLog()

# Keep your existing index.html at /
@app.get("/")
def home():
    return send_from_directory(str(ROOT), "index.html")

# New chatbot UI at /chat
@app.get("/chat")
def chat_page():
    return send_from_directory(str(ROOT), "chat_ui.html")

@app.get("/api/health")
def health():
    return jsonify({"ok": True})

@app.post("/api/chat")
def chat_once():
    try:
        data = request.get_json(silent=True) or {}
        session_id = (data.get("session_id") or datetime.now().strftime("%Y%m%d")).strip()
        user_msg   = (data.get("message") or "").strip()
        if not user_msg:
            return jsonify({"error": "message is required"}), 400

        store.create_session(session_id)
        prior = store.history(session_id)
        chat  = model.start_chat(history=to_chat_history_for_gemini(prior))

        store.append(session_id, "user", user_msg)
        resp  = chat.send_message(user_msg)
        reply = (getattr(resp, "text", "") or "").strip() or "(empty reply)"
        store.append(session_id, "model", reply)
        return jsonify({"reply": reply})
    except Exception as e:
        app.logger.exception("/api/chat error")
        return jsonify({"error": "server_error", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=True)
# server.py
from pathlib import Path
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Reuse your existing code from therapist_chatbot.py (no edits needed in that file)
from HIM import (
    ChatLog,
    build_model,
    to_chat_history_for_gemini,
    load_api_key,
    SilenceNativeStderr,
)

app = FastAPI(title="Therapist Chatbot API")
store = ChatLog()     # Uses DB_PATH from therapist_chatbot.py
model = None          # Initialized on startup

# --- CORS ---
# If your website is served from a different origin/port (e.g., ngrok/static hosting),
# add that origin here. If the site is the same origin as this API, you can remove this block.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",  # Example: your static site dev server
        "http://127.0.0.1:5500",
        # "https://yourdomain.com",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- Static (optional) ---
# If you want to drop a test index.html into ./static, it will be served at "/".
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "API is running. Put a UI at ./static/index.html or use your existing site."}

# --- Lifecycle ---
@app.on_event("startup")
def _startup():
    global model
    api_key = load_api_key()         # reads env/.env/file as in your helper
    model = build_model(api_key)     # builds the Gemini model once

# --- Models ---
class ChatIn(BaseModel):
    session_id: str
    message: str

class ChatOut(BaseModel):
    reply: str

# --- Endpoints ---
@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/sessions")
def list_sessions():
    return store.list_sessions()

@app.post("/api/session")
def create_session(payload: Dict[str, Optional[str]]):
    session_id = (payload.get("session_id") or "").strip()
    title = (payload.get("title") or None)
    if not session_id:
        raise HTTPException(400, "session_id is required")
    store.create_session(session_id, title=title)
    return {"created": session_id, "title": title}

@app.get("/api/history")
def history(session_id: str = Query(..., description="Session ID to fetch")):
    return store.history(session_id)

@app.post("/api/chat", response_model=ChatOut)
def chat(in_: ChatIn):
    if not in_.message.strip():
        raise HTTPException(400, "message is required")

    # Ensure session exists
    store.create_session(in_.session_id)

    # Load prior and reconstruct a Gemini chat each request
    prior = store.history(in_.session_id)

    try:
        with SilenceNativeStderr():
            chat = model.start_chat(history=to_chat_history_for_gemini(prior))
            stream = chat.send_message(in_.message, stream=True)
    except Exception as e:
        raise HTTPException(500, f"Gemini init failed: {e}")

    parts: List[str] = []
    try:
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                parts.append(text)
    except Exception as e:
        raise HTTPException(500, f"Gemini stream error: {e}")

    reply = "".join(parts).strip()
    if not reply:
        raise HTTPException(502, "Empty response from model")

    # Persist turn
    store.append(in_.session_id, "user", in_.message)
    store.append(in_.session_id, "model", reply)

    return ChatOut(reply=reply)
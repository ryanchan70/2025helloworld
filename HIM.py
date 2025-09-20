# therapist_chatbot.py
import os, contextlib

# Hide native gRPC/Abseil startup warnings
with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
    import google.generativeai as genai

import os
import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
import time 

import google.generativeai as genai


# ----------------------------
# Configuration
# ----------------------------

MODEL_NAME = "gemini-2.5-flash"
DB_PATH = "chat_history.sqlite3"

SYSTEM_PROMPT = """
You are an AI designed to be a compassionate, supportive listener.
- Use an empathetic, non-judgmental tone.
- Validate feelings; reflect back what you hear.
- Encourage gentle self-inquiry and healthier perspectives.
- Prefer concrete, small next steps when appropriate.
- Keep responses concise (4–8 sentences) and end with one gentle, open-ended question when helpful.
- If someone mentions being in immediate danger or suicidal ideation, encourage them to seek professional help or contact local emergency services right away.
"""


# ----------------------------
# Utilities: key loading
# ----------------------------

def _read_first_line(path: Path) -> Optional[str]:
    try:
        if path.exists():
            line = path.read_text(encoding="utf-8").strip()
            return line or None
    except Exception:
        pass
    return None


def _read_dotenv(path: Path) -> Optional[str]:
    """
    Minimal .env reader (no external dependency).
    Supports lines like: GEMINI_API_KEY=...   or   GEMINI_API_KEY="..."
    Ignores comments and blank lines.
    """
    try:
        if not path.exists():
            return None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == "GEMINI_API_KEY" and v:
                return v
            if k == "GOOGLE_API_KEY" and v:
                return v
    except Exception:
        pass
    return None


def load_api_key(preferred: Optional[str] = None) -> str:
    """
    Priority:
      1) CLI flag --api-key
      2) env GEMINI_API_KEY
      3) env GOOGLE_API_KEY (alias some folks use)
      4) ./.env (GEMINI_API_KEY or GOOGLE_API_KEY)
      5) ~/.gemini-api-key (first line)
    """
    search_report = []

    # 1) CLI
    if preferred:
        return preferred.strip()

    # 2) env GEMINI_API_KEY
    key = os.getenv("GEMINI_API_KEY")
    search_report.append(("env:GEMINI_API_KEY", bool(key)))
    if key:
        return key.strip()

    # 3) env GOOGLE_API_KEY
    key = os.getenv("GOOGLE_API_KEY")
    search_report.append(("env:GOOGLE_API_KEY", bool(key)))
    if key:
        return key.strip()

    # 4) .env in CWD
    key = _read_dotenv(Path(".env"))
    search_report.append((".env", bool(key)))
    if key:
        return key.strip()

    # 5) ~/.gemini-api-key
    key = _read_first_line(Path.home() / ".gemini-api-key")
    search_report.append(("~/.gemini-api-key", bool(key)))
    if key:
        return key.strip()

    # Nothing found → helpful error with report
    lines = ["Missing Gemini API key. I looked in:"]
    for where, found in search_report:
        lines.append(f"  - {where}: {'FOUND' if found else 'not found'}")
    lines += [
        "",
        "Fix one of the following:",
        "  • Pass a flag:    python therapist_chatbot.py --api-key YOUR_KEY",
        "  • Export env var: export GEMINI_API_KEY=YOUR_KEY   (zsh/bash)",
        "  • Put it in .env: echo 'GEMINI_API_KEY=YOUR_KEY' > .env",
        "  • Save a file:    echo 'YOUR_KEY' > ~/.gemini-api-key",
    ]
    sys.exit("\n".join(lines))


# ----------------------------
# Persistence: SQLite wrapper
# ----------------------------

class ChatLog:
    """
    SQLite wrapper (no external deps).
    Tables:
      sessions(id TEXT PRIMARY KEY, created_at TEXT, title TEXT)
      messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
               role TEXT, content TEXT, ts TEXT)
    """

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions(
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                title TEXT
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """)
            conn.commit()

    def create_session(self, session_id: str, title: Optional[str] = None):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(id, created_at, title) VALUES(?,?,?)",
                (session_id, datetime.now(timezone.utc).isoformat(), title or None)
            )
            conn.commit()

    def list_sessions(self) -> List[Dict]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("""
                SELECT id, created_at, COALESCE(title, '') as title
                FROM sessions ORDER BY created_at DESC
            """).fetchall()
        return [{"id": r[0], "created_at": r[1], "title": r[2]} for r in rows]

    def append(self, session_id: str, role: str, content: str):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, ts) VALUES(?,?,?,?)",
                (session_id, role, content, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

    def history(self, session_id: str) -> List[Dict]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("""
                SELECT role, content, ts FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
            """, (session_id,)).fetchall()
        return [{"role": r[0], "content": r[1], "ts": r[2]} for r in rows]

    def export_markdown(self, session_id: str, out_path: str):
        msgs = self.history(session_id)
        lines = [f"# Session {session_id}", ""]
        for m in msgs:
            t = m["ts"]
            role = m["role"].capitalize()
            lines.append(f"**{role} ({t})**\n\n{m['content']}\n")
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")


# ----------------------------
# Gemini setup helpers
# ----------------------------

def build_model(api_key: str) -> genai.GenerativeModel:
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        # Optional:
        # generation_config=genai.types.GenerationConfig(
        #     temperature=0.6,
        #     max_output_tokens=512,
        # ),
    )


def to_chat_history_for_gemini(history_rows: List[Dict]) -> List[Dict]:
    """
    Convert stored rows into Gemini chat 'history' format.
    """
    hist = []
    for r in history_rows:
        role = r["role"]
        content = r["content"]
        if role not in ("user", "model"):
            continue
        hist.append({"role": role, "parts": [{"text": content}]})
    return hist

# ----------------------------
# UX helper: typewriter effect
# ----------------------------

def type_out(s: str, cps: int = 40):  
    """
    Print text like it's being typed in real-time.
    cps = characters per second (0 = instant).
    Adds small pauses around punctuation for a natural feel.
    """
    if not s:
        return
    if cps <= 0:
        print(s, end="", flush=True)
        return

    base = 1.0 / float(cps)
    for ch in s:
        print(ch, end="", flush=True)
        if ch in ".!?":
            time.sleep(base * 8)
        elif ch in ",;:":
            time.sleep(base * 4)
        elif ch == "\n":
            time.sleep(base * 6)
        else:
            time.sleep(base)


# ----------------------------
# The main chat loop
# ----------------------------

def run_chat(session_id: str, title: Optional[str], api_key: str, cps: int = 40):  # [CHANGED] added cps
    # 1) Persistence
    store = ChatLog(DB_PATH)
    store.create_session(session_id, title=title)

    # 2) Prior history
    prior = store.history(session_id)

    # 3) Model + stateful chat
    model = build_model(api_key)
    chat = model.start_chat(history=to_chat_history_for_gemini(prior))

    # Info
    print(f"Therapy-style AI Chatbot  |  session: {session_id}")
    print("Press Ctrl+C to exit.")
    if title:
        print(f"Title: {title}")
    print()

    # Greeting for new sessions
    if not prior:
        system_greeting = "Hello. What’s on your mind today?"
        print("Bot: ", end="", flush=True)                     # [CHANGED]
        type_out(system_greeting, cps=cps)                     # [ADDED]
        print()                                                # [ADDED]
        store.append(session_id, "model", system_greeting)

    # 4) REPL
    while True:
        try:
            user_msg = input("\nYou: ").strip()
            if not user_msg:
                continue

            # Log user first
            store.append(session_id, "user", user_msg)

            # Stream response & buffer for logging
            print("Bot: ", end="", flush=True)
            full_text: List[str] = []                          # [ADDED] (annotation only)
            stream = chat.send_message(user_msg, stream=True)
            for chunk in stream:
                part = getattr(chunk, "text", None)
                if part:
                    full_text.append(part)
                    type_out(part, cps=cps)                    # [CHANGED] was print(part,...)

            print()  # newline after stream finishes

            reply_text = "".join(full_text).strip()
            if reply_text:
                store.append(session_id, "model", reply_text)

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description="Therapy-style Gemini chatbot with persistent history.")
    parser.add_argument("--session", "-s", help="Session ID (any string). Defaults to today's date.", default=None)
    parser.add_argument("--title", "-t", help="Optional title for the session.", default=None)
    parser.add_argument("--list", "-l", action="store_true", help="List existing sessions and exit.")
    parser.add_argument("--export", "-e", metavar="SESSION_ID", help="Export a session to Markdown and exit.")
    parser.add_argument("--out", "-o", metavar="FILE", help="Output path for --export (default: session_{id}.md)")
    parser.add_argument("--api-key", help="Gemini API key (overrides env vars and files).", default=None)
    parser.add_argument("--cps", type=int, default=40, help="Typing speed (chars/sec). 0 = instant.")  # [ADDED]

    args = parser.parse_args()

    # Utilities
    store = ChatLog(DB_PATH)

    if args.list:
        sessions = store.list_sessions()
        if not sessions:
            print("No sessions found.")
            return
        print("Existing sessions:")
        for s in sessions:
            print(f"- {s['id']}  (created {s['created_at']})  {('— ' + s['title']) if s['title'] else ''}")
        return

    if args.export:
        out = args.out or f"session_{args.export}.md"
        store.export_markdown(args.export, out)
        print(f"Exported to {out}")
        return

    # Load key (from CLI/env/.env/file)
    api_key = load_api_key(args.api_key)

    # Default session id: today's date
    session_id = args.session or datetime.now().strftime("%Y-%m-%d")
    run_chat(session_id=session_id, title=args.title, api_key=api_key, cps=args.cps)  # [CHANGED] pass cps


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()

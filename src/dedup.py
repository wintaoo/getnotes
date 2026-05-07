import hashlib
import os
import sqlite3
import threading

from .config import NOTES_DIR

DB_PATH = os.path.join(NOTES_DIR, ".cache.db")
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    os.makedirs(NOTES_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processed ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  url_hash TEXT UNIQUE NOT NULL,"
        "  url TEXT NOT NULL,"
        "  title TEXT,"
        "  filename TEXT,"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    conn.commit()
    return conn


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def is_processed(url: str) -> str | None:
    """Return filename if URL has been processed, None otherwise."""
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT filename FROM processed WHERE url_hash = ?",
            (_hash_url(url),),
        ).fetchone()
        conn.close()
    return row[0] if row else None


def mark_processed(url: str, title: str, filename: str):
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO processed (url_hash, url, title, filename) VALUES (?, ?, ?, ?)",
            (_hash_url(url), url, title, filename),
        )
        conn.commit()
        conn.close()


def get_url_by_filename(filename: str) -> str | None:
    """Retrieve the original URL for a given filename."""
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT url FROM processed WHERE filename = ?",
            (filename,),
        ).fetchone()
        conn.close()
    return row[0] if row else None

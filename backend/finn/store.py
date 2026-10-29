"""One SQLite file holds every cache: HTTP bodies, PDF text, LLM answers, filings and job results.

Caching is the main cost lever: a transcript is downloaded, parsed and summarised once,
then every later request for that company is free.
"""
import json
import sqlite3
import threading
import time

from .config import DATA_DIR

_DB = DATA_DIR / "finn.db"
_lock = threading.RLock()
_conn = sqlite3.connect(_DB, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.executescript("""
CREATE TABLE IF NOT EXISTS kv (ns TEXT, k TEXT, v TEXT, ts REAL, PRIMARY KEY (ns, k));
CREATE TABLE IF NOT EXISTS blobs (url TEXT PRIMARY KEY, body BLOB, ctype TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS filings (
    id TEXT PRIMARY KEY, symbol TEXT, company TEXT, ts REAL, title TEXT, subject TEXT,
    summary TEXT, url TEXT, source TEXT, extra TEXT);
CREATE INDEX IF NOT EXISTS filings_ts ON filings(ts);
""")


def kv_get(ns, k, max_age=None):
    with _lock:
        row = _conn.execute("SELECT v, ts FROM kv WHERE ns=? AND k=?", (ns, k)).fetchone()
    if not row or (max_age is not None and time.time() - row[1] > max_age):
        return None
    return json.loads(row[0])


def kv_age(ns, k):
    with _lock:
        row = _conn.execute("SELECT ts FROM kv WHERE ns=? AND k=?", (ns, k)).fetchone()
    return None if not row else time.time() - row[0]


def kv_set(ns, k, v, ts=None):
    with _lock:
        _conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?,?)",
                      (ns, k, json.dumps(v, default=str), ts or time.time()))
        _conn.commit()


def kv_all(ns):
    with _lock:
        rows = _conn.execute("SELECT k, v FROM kv WHERE ns=?", (ns,)).fetchall()
    return {k: json.loads(v) for k, v in rows}


def blob_get(url, max_age=None):
    with _lock:
        row = _conn.execute("SELECT body, ctype, ts FROM blobs WHERE url=?", (url,)).fetchone()
    if not row or (max_age is not None and time.time() - row[2] > max_age):
        return None
    return row[0], row[1]


def blob_set(url, body, ctype):
    with _lock:
        _conn.execute("INSERT OR REPLACE INTO blobs VALUES (?,?,?,?)", (url, body, ctype, time.time()))
        _conn.commit()


def blob_del(url):
    with _lock:
        _conn.execute("DELETE FROM blobs WHERE url=?", (url,))
        _conn.commit()


FILING_COLS =["id", "symbol", "company", "ts", "title", "subject", "summary", "url", "source", "extra"]


def upsert_filings(rows):
    """Insert filings; a richer duplicate (longer summary) wins over a thinner one."""
    with _lock:
        for r in rows:
            old = _conn.execute("SELECT summary FROM filings WHERE id=?", (r["id"],)).fetchone()
            if old and len(old[0] or "") >= len(r.get("summary") or ""):
                continue
            _conn.execute(f"INSERT OR REPLACE INTO filings VALUES ({','.join('?' * len(FILING_COLS))})",
                          [json.dumps(r.get(c) or {}) if c == "extra" else r.get(c) for c in FILING_COLS])
        _conn.commit()


def filings_since(ts, symbols=None):
    with _lock:
        rows = _conn.execute("SELECT * FROM filings WHERE ts>=? ORDER BY ts DESC", (ts,)).fetchall()
    out = [dict(zip(FILING_COLS, r)) for r in rows]
    for r in out:
        r["extra"] = json.loads(r["extra"] or "{}")
    if symbols is not None:
        out = [r for r in out if r["symbol"] in symbols]
    return out

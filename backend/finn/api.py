"""FINN HTTP API + static frontend.  uvicorn finn.api:app"""
import json
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ingest, llm, memo, snapshot, store
from .config import PORTFOLIO, RESEARCH_DEMO, WEB_DIST
from .net import FetchError
from .pull import ask as ask_mod
from .pull import research
from .push import alerts, digest, webpush
from .sources import screener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
app = FastAPI(title="FINN")
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.on_event("startup")
def _startup():
    if snapshot.load(only_if_empty=True):
        logging.info("seeded from snapshot")
    if os.environ.get("FINN_BACKGROUND", "1") == "1":
        ingest.start_background()


def _rules(raw):
    try:
        return alerts.merge_rules(json.loads(raw)) if raw else alerts.merge_rules()
    except (ValueError, TypeError):
        return alerts.merge_rules()


@app.get("/api/meta")
def meta():
    return {"portfolio": PORTFOLIO, "research_demo": RESEARCH_DEMO, "llm": llm.status(),
            "last_refresh": store.kv_get("meta", "last_refresh"), "feed": store.kv_get("nse", "feed_stats"),
            "default_rules": alerts.merge_rules()}


def digest_cached(hours=24, since=None, rules=None, muted=()):
    r = alerts.merge_rules(rules)
    since = int(since // 60 * 60) if since else None  # "since your last visit" rounded to the minute
    key = ("digest", hours, since, json.dumps(r, sort_keys=True), ",".join(sorted(muted)))

    def build():
        with llm.cached_only():
            return digest.build(hours=hours, since=since, rules=r, muted=list(muted))
    return memo.get(key, build)


def holdings_cached():
    return memo.get(("holdings",), digest.holdings)


def backtest_default():
    return memo.get(("backtest", json.dumps(alerts.merge_rules(), sort_keys=True), 90),
                    lambda: alerts.backtest(alerts.merge_rules(), sessions=90))


@app.get("/api/digest")
def get_digest(hours: float = 24, since: float | None = None, rules: str | None = None, muted: str = ""):
    return digest_cached(hours, since, _rules(rules), tuple(m for m in muted.split(",") if m))


@app.get("/api/brief")
def get_brief(hours: float = 24, since: float | None = None, rules: str | None = None, muted: str = ""):
    d = digest_cached(hours, since, _rules(rules), tuple(m for m in muted.split(",") if m))
    return {"script": digest.brief_script(d)}


@app.get("/api/holdings")
def get_holdings():
    return holdings_cached()


@app.get("/api/stats")
def stats():
    """What FINN has read and what it cost, for the 'How FINN works' page."""
    counts_part = memo.get(("stats",), _stats_counts, ttl=1800)
    return {**counts_part, "llm": llm.status(), "feed": store.kv_get("nse", "feed_stats"),
            "last_refresh": store.kv_get("meta", "last_refresh")}


def _stats_counts():
    with store._lock:
        counts = dict(store._conn.execute("SELECT ns, COUNT(*) FROM kv GROUP BY ns").fetchall())
        filings = store._conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
        pdf_pages = store._conn.execute("SELECT COALESCE(SUM(json_array_length(v)), 0) FROM kv WHERE ns='pdftext'").fetchone()[0]
    return {"filings_stored": filings, "pdfs_read": counts.get("pdftext", 0), "pdf_pages": pdf_pages,
            "dossiers": counts.get("research", 0), "transcripts": counts.get("guidance", 0),
            "annual_reports": counts.get("governance", 0), "llm_cached_answers": counts.get("llm", 0)}


class RulesIn(BaseModel):
    rules: dict = {}
    sessions: int = 90


@app.post("/api/alerts/backtest")
def backtest(body: RulesIn):
    r, n = alerts.merge_rules(body.rules), min(max(body.sessions, 20), 240)
    return memo.get(("backtest", json.dumps(r, sort_keys=True), n), lambda: alerts.backtest(r, sessions=n))


@app.get("/api/search")
def search(q: str):
    return screener.search(q)


@app.post("/api/research/{symbol}")
def research_start(symbol: str, force: bool = False):
    try:
        screener.company(symbol)  # fail fast on an unknown ticker
    except FetchError:
        raise HTTPException(404, f"No data for {symbol}")
    return research.start(symbol, force=force)


@app.get("/api/research/{symbol}")
def research_get(symbol: str):
    doc = research.get(symbol)
    if not doc:
        raise HTTPException(404, "not started")
    return doc


class AskIn(BaseModel):
    symbol: str
    q: str


@app.post("/api/ask")
def ask(body: AskIn):
    try:
        co = screener.company(body.symbol)
    except FetchError:
        raise HTTPException(404, f"No data for {body.symbol}")
    return ask_mod.answer(body.symbol.upper(), co["name"], body.q[:300])


class SubIn(BaseModel):
    subscription: dict
    rules: dict = {}
    muted: list = []


@app.get("/api/push/key")
def push_key():
    return {"publicKey": webpush.public_key()}


@app.post("/api/push/subscribe")
def push_subscribe(body: SubIn):
    return {"ok": webpush.subscribe(body.subscription, body.rules, body.muted)}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: SubIn):
    webpush.unsubscribe(body.subscription)
    return {"ok": True}


_last_tick = {"t": 0.0, "report": None}


@app.get("/api/tick")
def tick():
    """Called every 10 minutes by a scheduled GitHub Action: keeps the server awake,
    refreshes data, and sends background alerts. Cheap to call more often (rate-limited)."""
    if time.time() - _last_tick["t"] < 120:
        return {"skipped": True, "last": _last_tick["report"]}
    _last_tick["t"] = time.time()
    try:
        ingest.refresh_all()
    except Exception as e:
        logging.warning("tick refresh failed: %s", e)
    report = webpush.tick()
    _last_tick["report"] = {**report, "at": time.time()}
    return _last_tick["report"]


_last_manual = {"t": 0.0}


@app.post("/api/refresh")
def refresh():
    if time.time() - _last_manual["t"] < 120:
        return {"ok": False, "reason": "refreshed under 2 minutes ago"}
    _last_manual["t"] = time.time()
    ingest.refresh_all(force=True)
    return {"ok": True, "last_refresh": store.kv_get("meta", "last_refresh")}


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")

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

from . import ingest, llm, snapshot, store
from .config import PORTFOLIO, RESEARCH_DEMO, WEB_DIST
from .net import FetchError
from .pull import ask as ask_mod
from .pull import research
from .push import alerts, digest
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


@app.get("/api/digest")
def get_digest(hours: float = 24, since: float | None = None, rules: str | None = None, muted: str = ""):
    return digest.build(hours=hours, since=since, rules=_rules(rules), muted=[m for m in muted.split(",") if m])


@app.get("/api/brief")
def get_brief(hours: float = 24, since: float | None = None, rules: str | None = None, muted: str = ""):
    d = digest.build(hours=hours, since=since, rules=_rules(rules), muted=[m for m in muted.split(",") if m])
    return {"script": digest.brief_script(d)}


@app.get("/api/holdings")
def get_holdings():
    return digest.holdings()


class RulesIn(BaseModel):
    rules: dict = {}
    sessions: int = 90


@app.post("/api/alerts/backtest")
def backtest(body: RulesIn):
    return alerts.backtest(alerts.merge_rules(body.rules), sessions=min(max(body.sessions, 20), 240))


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

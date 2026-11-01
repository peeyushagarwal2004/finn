"""Refresh loop: EOD prices, screener pages (announcements + fundamentals), NSE RSS."""
import hashlib
import logging
import threading
import time

from . import memo, store
from .config import PORTFOLIO_SYMBOLS
from .net import FetchError
from .sources import nse, prices, screener

log = logging.getLogger("finn.ingest")


def company_filings(symbol, co=None):
    co = co or screener.company(symbol)
    rows = []
    for a in co["documents"]["announcements"]:
        if not a.get("ts") or not a.get("url"):
            continue
        rows.append({"id": hashlib.sha1(a["url"].encode()).hexdigest()[:16], "symbol": symbol, "company": co["name"],
                     "ts": a["ts"], "title": a["title"], "subject": "", "summary": a.get("summary", ""),
                     "url": a["url"], "source": "BSE"})
    store.upsert_filings(rows)
    return rows


def names():
    out = {}
    for s in PORTFOLIO_SYMBOLS:
        co = store.kv_get("company", s)
        out[s] = co["name"] if co else s
    return out


def refresh_companies(symbols=PORTFOLIO_SYMBOLS, ttl=6 * 3600):
    for s in symbols:
        try:
            company_filings(s, screener.company(s, ttl=ttl))
        except FetchError as e:
            log.warning("screener %s: %s", s, e)


def _fingerprint():
    with store._lock:
        f = store._conn.execute("SELECT COUNT(*), MAX(ts), SUM(LENGTH(summary)) FROM filings").fetchone()
    eod = store.kv_get("eod", PORTFOLIO_SYMBOLS[0]) or [[None]]
    return (f, eod[-1][0])


def refresh_all(force=False):
    t0 = time.time()
    before = _fingerprint()
    try:
        if force or (store.kv_age("eod", PORTFOLIO_SYMBOLS[0]) or 1e9) > 3 * 3600:
            prices.refresh(PORTFOLIO_SYMBOLS)
    except Exception as e:  # yfinance is the flakiest dependency; never let it stop the rest
        log.warning("prices: %s", e)
    refresh_companies(ttl=1800 if force else 6 * 3600)
    nse.poll(set(PORTFOLIO_SYMBOLS), names())
    store.kv_set("meta", "last_refresh", {"ts": time.time(), "secs": round(time.time() - t0, 1)})
    if _fingerprint() != before:  # only new filings or prices invalidate the cached pages
        memo.bump()


def prewarm():
    """Compute the default pages ahead of time so the first visitor gets a cached response."""
    from .api import backtest_default, digest_cached, holdings_cached
    for h in (24, 72, 168):
        digest_cached(h)
    holdings_cached()
    backtest_default()


def start_background(interval=300):
    """Poll NSE every 5 minutes (its RSS TTL); full refresh is internally rate-limited."""
    def loop():
        while True:
            try:
                refresh_all()
                from .push import digest
                digest.build(hours=24 * 7)  # warm results cards and people (model calls happen here, not in requests)
                prewarm()
            except Exception as e:
                log.warning("refresh failed: %s", e)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="finn-refresh").start()

"""End-of-day price & volume from Yahoo Finance, plus per-session signals.

A fixed ±X% threshold treats a 3% day on a sleepy bank like a 3% day on a small-cap
manufacturer. So every session also gets a sigma score: the move divided by that
stock's own 60-session volatility. The user picks which lens they trust.
"""
import math
import warnings
from datetime import datetime, time as dtime

from .. import store
from ..config import DATA_DIR
from .nse import IST

warnings.filterwarnings("ignore")


def _session_closed_today():
    now = datetime.now(IST)
    return now.weekday() >= 5 or now.time() >= dtime(16, 0)


def refresh(symbols, period="1y"):
    import yfinance as yf
    try:
        yf.set_tz_cache_location(str(DATA_DIR / "yf-cache"))
    except Exception:
        pass
    df = yf.download([s + ".NS" for s in symbols], period=period, interval="1d", group_by="ticker",
                     progress=False, auto_adjust=False, threads=False)
    today = datetime.now(IST).date()
    out = {}
    for s in symbols:
        try:
            sub = df[s + ".NS"].dropna(subset=["Close"])
        except KeyError:
            continue
        rows = [[d.strftime("%Y-%m-%d"), round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2),
                 round(float(r.Close), 2), int(r.Volume or 0)] for d, r in sub.iterrows()]
        # an unfinished session has partial volume and would fake a "volume collapse"
        if rows and rows[-1][0] == today.isoformat() and not _session_closed_today():
            rows = rows[:-1]
        if len(rows) > 30:
            out[s] = rows
            store.kv_set("eod", s, rows)
    return out


def series(symbol):
    return store.kv_get("eod", symbol) or []


def signals(rows):
    """Annotate each session with ret %, volume multiple vs prior 20 sessions, and sigma."""
    out = []
    for i in range(1, len(rows)):
        d, o, h, lo, c, v = rows[i]
        pc = rows[i - 1][4]
        ret = 100 * (c / pc - 1) if pc else 0.0
        past_v = [r[5] for r in rows[max(0, i - 20):i] if r[5]]
        vm = v / (sum(past_v) / len(past_v)) if past_v and v else None
        rets = [100 * (rows[j][4] / rows[j - 1][4] - 1) for j in range(max(1, i - 60), i) if rows[j - 1][4]]
        sd = None
        if len(rets) >= 20:
            mu = sum(rets) / len(rets)
            sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1))
        out.append({"date": d, "close": c, "ret": round(ret, 2), "vol": v,
                    "vol_mult": round(vm, 2) if vm else None,
                    "sigma": round(ret / sd, 2) if sd else None})
    return out


def summary(symbol):
    rows = series(symbol)
    if len(rows) < 25:
        return None
    sig = signals(rows)
    last = sig[-1]
    closes = [r[4] for r in rows]
    yr = closes[-250:]
    return {
        "date": last["date"], "close": last["close"], "ret": last["ret"], "vol_mult": last["vol_mult"],
        "sigma": last["sigma"],
        "ret_1m": round(100 * (closes[-1] / closes[-22] - 1), 1) if len(closes) > 22 else None,
        "hi52": max(yr), "lo52": min(yr),
        "from_hi": round(100 * (closes[-1] / max(yr) - 1), 1),
        "spark": closes[-60:],
    }

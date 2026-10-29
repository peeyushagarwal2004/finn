"""Triggered alerts on EOD data, and a backtest that prices a threshold in attention.

Before you save "ping me above 2× volume", FINN replays the last 90 sessions and tells
you that rule would have fired 41 times (~3 a week). Thresholds become a conscious
trade between coverage and interruptions instead of a guess.
"""
from collections import Counter

from ..config import DEFAULT_RULES, PORTFOLIO_SYMBOLS
from ..sources import prices


def merge_rules(r=None):
    out = dict(DEFAULT_RULES)
    for k, v in (r or {}).items():
        if k in out and v is not None:
            out[k] = v
    return out


def move_triggers(sig, rules):
    """Which rules this session tripped, with the human reason."""
    why = []
    if abs(sig["ret"]) >= rules["price_pct"]:
        why.append(("price", f"{sig['ret']:+.1f}% on the day"))
    if sig["vol_mult"] and sig["vol_mult"] >= rules["vol_mult"]:
        why.append(("volume", f"{sig['vol_mult']:.1f}× usual volume"))
    if rules.get("use_sigma") and sig["sigma"] is not None and abs(sig["sigma"]) >= rules["sigma"]:
        why.append(("sigma", f"{abs(sig['sigma']):.1f}σ move for this stock"))
    return why


def moves(rules, sessions=1, symbols=PORTFOLIO_SYMBOLS):
    """Alerts for the last `sessions` EOD sessions."""
    out = []
    for s in symbols:
        rows = prices.series(s)
        if len(rows) < 30:
            continue
        sig = prices.signals(rows)
        for i in range(max(0, len(sig) - sessions), len(sig)):
            hit = move_triggers(sig[i], rules)
            if hit:
                window = [r[4] for r in rows[max(0, i - 18):i + 2]]
                vols = [r[5] for r in rows[max(0, i - 18):i + 2]]
                out.append({"symbol": s, "date": sig[i]["date"], "ret": sig[i]["ret"], "vol_mult": sig[i]["vol_mult"],
                            "sigma": sig[i]["sigma"], "close": sig[i]["close"], "kinds": [k for k, _ in hit],
                            "why": [w for _, w in hit], "spark": window, "vols": vols})
    return sorted(out, key=lambda x: (x["date"], abs(x["ret"])), reverse=True)


def backtest(rules, sessions=90):
    ev = moves(rules, sessions=sessions)
    dates = sorted({r[0] for s in PORTFOLIO_SYMBOLS for r in prices.series(s)[-sessions:]})
    by_day = Counter(e["date"] for e in ev)
    weeks = max(1, len(dates) / 5)
    return {
        "sessions": len(dates), "total": len(ev), "per_week": round(len(ev) / weeks, 1),
        "by_kind": Counter(k for e in ev for k in e["kinds"]),
        "by_symbol": Counter(e["symbol"] for e in ev).most_common(6),
        "timeline": [{"date": d, "n": by_day.get(d, 0)} for d in dates],
        "recent": ev[:12],
    }

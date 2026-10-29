"""The windowed digest: every filing in the window, ranked, enriched only where it earns it.

Tiers:  needs_you (>=65)  -> full card (results table, people, move chart)
        worth_knowing     -> one line
        routine (<25)     -> collapsed into a count per category
Price/volume alerts join the same list, cross-referenced with filings: a big move with
no filing behind it is flagged as unexplained, the one an investor most needs to see.
"""
import re
import time
from datetime import datetime

from .. import store
from ..config import LENDERS, PORTFOLIO, PORTFOLIO_SYMBOLS
from ..sources import nse, prices
from . import alerts, classify, people, results

SECTOR = {p["symbol"]: p["sector"] for p in PORTFOLIO}
clean_title = classify.clean_title


def _tokens(s):
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower())} - {"limited", "company", "regulation", "informed", "exchange", "about", "regarding", "disclosure", "announcement", "under", "lodr", "sebi"}


def _same_event(a, b):
    """NSE and BSE both carry most filings, under different titles; so do companies that file
    the result, the deck and the letter separately. Merge what is one event to the investor."""
    if a["symbol"] != b["symbol"] or abs(a["ts"] - b["ts"]) > 3 * 86400:
        return False
    if a["category"] == b["category"] == "results" and {a["sub"], b["sub"]} <= {"results", "deck"}:
        return True
    if a["category"] != b["category"]:
        return False
    if a.get("amount_cr") and b.get("amount_cr") and abs(a["amount_cr"] - b["amount_cr"]) <= 0.02 * a["amount_cr"]:
        return True
    ta, tb = a["_tok"], b["_tok"]
    return bool(ta and tb and len(ta & tb) / len(ta | tb) >= 0.3)


def _dedupe(items):
    kept = []
    # the most important version of an event survives; richer summaries break ties
    for it in sorted(items, key=lambda x: (-x["score"], -len(x.get("summary") or ""))):
        it["_tok"] = _tokens(it["title"] + " " + (it.get("summary") or ""))
        dup = next((k for k in kept if _same_event(k, it)), None)
        if dup:
            dup.setdefault("also", []).append({"source": it["source"], "url": it["url"], "title": it["title"]})
        else:
            kept.append(it)
    for k in kept:
        k.pop("_tok", None)
    return kept


def _scale(symbol):
    co = store.kv_get("company", symbol) or {}
    pl = (co.get("tables") or {}).get("profit-loss") or {}
    rev = None
    for key in ("Sales", "Revenue"):
        if key in pl.get("rows", {}):
            rev = next((v for v in reversed(pl["rows"][key]) if v), None)
            break
    return rev, (co.get("ratios") or {}).get("Market Cap"), co.get("name", symbol)


def _oneliner(f, cat, sub):
    s = (f.get("summary") or "").strip()
    if f["source"] == "NSE":  # NSE bodies are boilerplate wrapped around the real headline
        s = ""
    if len(s) > 220:
        s = s[:217].rsplit(" ", 1)[0] + "…"
    return s


def _enrich(item, symbol, name):
    cat = item["category"]
    if cat == "results" and item["sub"] == "results":
        key = f"{symbol}:{int(item['ts'] // 86400)}"
        card = store.kv_get("results_card", key)
        if card is None:
            try:
                card = results.headline(symbol, lender=symbol in LENDERS)
            except Exception:
                card = None
            store.kv_set("results_card", key, card or {})
        if card and card.get("period_end"):
            # the screener table may not have this quarter yet; never attach last quarter's numbers
            lag = (item["ts"] - datetime.fromisoformat(card["period_end"]).timestamp()) / 86400
            if not 0 <= lag <= 100:
                card = None
        if card:
            item["results"] = card
            if card.get("headline"):
                item["oneliner"] = f"{card['period']}: {card['headline']}"
    elif cat == "management_change" and item["score"] >= 60:
        ppl = store.kv_get("people", item["id"])
        if ppl is None:
            try:
                ppl = people.enrich(item, name)
            except Exception:
                ppl = []
            store.kv_set("people", item["id"], ppl)
        if ppl:
            item["people"] = ppl
            ins = [p for p in ppl if p["direction"] == "in"]
            outs = [p for p in ppl if p["direction"] == "out"]
            bits = []
            if ins:
                bits.append("In: " + ", ".join(f"{p['name']}" + (f" ({p['role']})" if p["role"] else "") for p in ins))
            if outs:
                bits.append("Out: " + ", ".join(p["name"] for p in outs))
            if bits:
                item["oneliner"] = " · ".join(bits)


def build(hours=24, since=None, rules=None, muted=(), symbols=PORTFOLIO_SYMBOLS):
    rules = alerts.merge_rules(rules)
    now = time.time()
    start = since or (now - hours * 3600)
    raw = store.filings_since(start, set(symbols))
    muted = set(muted)
    items = []
    for f in raw:
        rev, mcap, name = _scale(f["symbol"])
        sc = classify.score(f, revenue_cr=rev, mcap_cr=mcap)
        it = {
            "id": f["id"], "kind": "filing", "symbol": f["symbol"], "company": name, "sector": SECTOR.get(f["symbol"]),
            "ts": f["ts"], "title": clean_title(f["title"]), "summary": f.get("summary"), "url": f["url"],
            "source": f["source"], "category": sc["category"], "category_label": classify.CATEGORY_LABEL[sc["category"]],
            "sub": sc["sub"], "score": sc["score"], "reasons": sc["reasons"], "amount_cr": sc["amount_cr"],
        }
        it["oneliner"] = _oneliner(f, sc["category"], sc["sub"])
        if f"{f['symbol']}:{sc['category']}" in muted:
            it["score"] = min(it["score"], 20)
            it["muted"] = True
        items.append(it)
    items = _dedupe(items)
    for it in items:
        it["tier"] = classify.tier(it["score"])
        it["alert"] = it["category"] in rules["categories"] and it["score"] >= rules["min_score"]
        if it["tier"] != "routine":
            _enrich(it, it["symbol"], it["company"])

    # price / volume moves inside the window
    start_day = datetime.fromtimestamp(start, nse.IST).date().isoformat()
    n_sessions = max(1, min(30, int(hours / 24) + 1)) if not since else 5
    for mv in alerts.moves(rules, sessions=n_sessions, symbols=symbols):
        if mv["date"] < start_day and hours <= 24 and not since:
            # a 24h window over a weekend/holiday still shows the last session's moves
            pass
        elif mv["date"] < start_day:
            continue
        day_ts = datetime.fromisoformat(mv["date"]).replace(hour=15, minute=30, tzinfo=nse.IST).timestamp()
        related = [i for i in items if i["symbol"] == mv["symbol"] and abs(i["ts"] - day_ts) < 1.6 * 86400 and i["score"] >= 25]
        _, _, name = _scale(mv["symbol"])
        price_strength = max(abs(mv["ret"]) / max(rules["price_pct"], 0.1), abs(mv["sigma"] or 0) / max(rules["sigma"], 0.1))
        vol_strength = (mv["vol_mult"] or 0) / max(rules["vol_mult"], 0.1)
        # heavy volume on a flat day is worth knowing; a real price move is what needs you
        score = int(58 + 10 * price_strength + 3 * min(vol_strength, 3)) if price_strength >= 1 else int(40 + 6 * min(vol_strength, 3))
        it = {
            "id": f"move-{mv['symbol']}-{mv['date']}", "kind": "move", "symbol": mv["symbol"], "company": name,
            "sector": SECTOR.get(mv["symbol"]), "ts": day_ts, "category": "move", "category_label": "Unusual move",
            "score": min(95, score), "move": mv, "alert": True,
            "explained_by": [{"id": r["id"], "title": r["title"], "category_label": r["category_label"]} for r in related],
            "title": f"{mv['ret']:+.1f}% · " + " · ".join(w for w in mv["why"] if not w.endswith("on the day")),
        }
        it["title"] = it["title"].rstrip(" ·")
        it["unexplained"] = not related
        if it["unexplained"] and price_strength >= 1:
            it["score"] = min(97, it["score"] + 8)
            it["reasons"] = ["No filing explains this move"]
        elif it["unexplained"]:
            it["reasons"] = ["Heavy volume, no filing"]
        else:
            it["reasons"] = [f"Likely driver: {related[0]['category_label'].lower()}"]
        it["tier"] = classify.tier(it["score"])
        items.append(it)

    items.sort(key=lambda x: (-x["score"], -x["ts"]))
    tiers = {t: [i for i in items if i["tier"] == t] for t in ("needs_you", "worth_knowing", "routine")}
    routine_groups = {}
    for i in tiers["routine"]:
        routine_groups.setdefault(i["category_label"], []).append(i)
    feed = store.kv_get("nse", "day_counts") or {}
    return {
        "window": {"start": start, "end": now, "hours": hours},
        "counts": {"filings": sum(1 for i in items if i["kind"] == "filing"), "moves": sum(1 for i in items if i["kind"] == "move"),
                   "needs_you": len(tiers["needs_you"]), "worth_knowing": len(tiers["worth_knowing"]),
                   "routine": len(tiers["routine"]), "alerts": sum(1 for i in items if i.get("alert")),
                   "market_today": feed.get(datetime.now(nse.IST).date().isoformat())},
        "needs_you": tiers["needs_you"], "worth_knowing": tiers["worth_knowing"],
        "routine": [{"label": k, "count": len(v), "items": v} for k, v in sorted(routine_groups.items(), key=lambda kv: -len(kv[1]))],
        "rules": rules,
    }


def holdings():
    out = []
    for p in PORTFOLIO:
        s = p["symbol"]
        sm = prices.summary(s)
        _, mcap, name = _scale(s)
        last = store.filings_since(time.time() - 30 * 86400, {s})
        lf = None
        if last:
            sc = classify.score(last[0])
            lf = {"title": clean_title(last[0]["title"]), "ts": last[0]["ts"], "category_label": classify.CATEGORY_LABEL[sc["category"]]}
        out.append({"symbol": s, "name": name, "sector": p["sector"], "size": p["size"], "mcap": mcap, "eod": sm, "last_filing": lf})
    return out


def brief_script(d):
    """A ~60-second spoken brief, built from the digest (no model needed)."""
    n = d["counts"]
    lines = [f"Here's your brief. {n['filings']} filings across your portfolio; {n['needs_you']} need you."]
    for it in d["needs_you"][:5]:
        co = it["company"].replace(" Ltd", "").replace(" Limited", "")
        if it["kind"] == "move":
            mv = it["move"]
            tail = " No filing explains it." if it.get("unexplained") else ""
            lines.append(f"{co} moved {abs(mv['ret']):.1f} percent {'up' if mv['ret'] > 0 else 'down'}, {mv['why'][-1]}.{tail}")
        elif it.get("results"):
            lines.append(f"{co} reported {it['results']['period']}: {it['results']['headline']}.")
        elif it.get("people"):
            lines.append(f"{co}: {it['oneliner'].replace(' · ', '. ')}.")
        else:
            lines.append(f"{co}: {it['title']}.")
    if n["routine"]:
        lines.append(f"{n['routine']} routine filings were set aside.")
    return " ".join(lines)

"""Promise ledger: what management said, checked against what the statements later showed.

For each promise on a checkable metric (revenue growth, operating margin, profit growth)
the period it refers to is mapped onto reported quarters, the same quarters a year earlier
are used as the base, and a verdict is given. Promises whose period hasn't been reported
yet are 'tracking' on the quarters that have.
"""
import re

from ..push.results import fy_label
from ..sources import screener
from .guidance import CHECKABLE, METRIC_LABEL


def _quarters(co):
    q = co["tables"].get("quarters") or {"headers": [], "rows": {}}
    r = q["rows"]
    sales = r.get("Sales") or r.get("Revenue") or []
    op = r.get("Operating Profit") or r.get("Financing Profit") or []
    pat = r.get("Net Profit") or []
    out = {}
    for i, h in enumerate(q["headers"]):
        m = re.match(r"Q(\d) FY(\d\d)", fy_label(h))
        if m:
            out[(int(m.group(1)), 2000 + int(m.group(2)))] = {
                "label": fy_label(h), "sales": sales[i] if i < len(sales) else None,
                "op": op[i] if i < len(op) else None, "pat": pat[i] if i < len(pat) else None}
    return out


def _period_quarters(period):
    if not period:
        return None
    m = re.match(r"(?:(Q)([1-4])|(H)([12]))?\s*FY(\d\d)", period.replace(" ", " "))
    if not m:
        return None
    fy = 2000 + int(m.group(5))
    if m.group(1):
        return [(int(m.group(2)), fy)]
    if m.group(3):
        return [(1, fy), (2, fy)] if m.group(4) == "1" else [(3, fy), (4, fy)]
    return [(1, fy), (2, fy), (3, fy), (4, fy)]


def actual(qd, metric, quarters):
    """Metric over the reported subset of `quarters`; returns (value, n_reported)."""
    have = [k for k in quarters if k in qd and qd[k]["sales"] is not None]
    if not have:
        return None, 0
    if metric == "ebitda_margin":
        s = sum(qd[k]["sales"] or 0 for k in have)
        o = sum(qd[k]["op"] or 0 for k in have)
        return (round(100 * o / s, 1) if s else None), len(have)
    field = "sales" if metric == "revenue_growth" else "pat"
    base = [(q, fy - 1) for q, fy in have]
    if not all(b in qd and qd[b][field] for b in base):
        return None, len(have)
    cur = sum(qd[k][field] or 0 for k in have)
    prev = sum(qd[b][field] for b in base)
    return (round(100 * (cur / prev - 1), 1) if prev > 0 else None), len(have)


def _verdict(p, val, n, total):
    lo, hi = p.get("low"), p.get("high")
    if val is None:
        return "pending", None
    complete = n >= total
    tol = 0.2 if p["metric"] == "ebitda_margin" else 0.5
    if lo is not None and val + tol < lo:
        gap = lo - val
        close = gap <= (1.0 if p["metric"] == "ebitda_margin" else 2.5)
        if complete:
            return ("near_miss" if close else "missed"), round(-gap, 1)
        return ("slightly_behind" if close else "behind"), round(-gap, 1)
    if hi is not None and p["metric"] != "ebitda_margin" and val > hi + 5:
        return ("beat" if complete else "ahead"), round(val - hi, 1)
    return ("delivered" if complete else "on_track"), round(val - (lo if lo is not None else val), 1)


VERDICT_LABEL = {"delivered": "Delivered", "beat": "Beat", "on_track": "On track", "ahead": "Ahead",
                 "near_miss": "Near miss", "slightly_behind": "Slightly behind", "behind": "Behind", "missed": "Missed", "pending": "Pending",
                 "unverifiable": "Not checkable", "long_term": "Long-dated"}


def build(symbol, transcripts):
    co = screener.company(symbol)
    qd = _quarters(co)
    rows = []
    for t in transcripts:
        call_key = (t["q"], t["fy"])
        for p in t["promises"]:
            pq = _period_quarters(p.get("period"))
            row = {"said_in": t["label"], "url": t["url"], "page": p["page"], "speaker": p["speaker"],
                   "quote": p["text"], "summary": p.get("summary"), "metric": p["metric"],
                   "metric_label": METRIC_LABEL.get(p["metric"], p["metric"]), "period": p.get("period"),
                   "low": p.get("low"), "high": p.get("high"), "unit": p.get("unit"), "explicit": p.get("explicit")}
            if pq:
                end = max(pq, key=lambda k: (k[1], k[0]))
                if (end[1], end[0]) <= (call_key[1], call_key[0]):
                    continue  # the period had already been reported when it was said: a recap, not a promise
            if p["metric"] in ("other", "unit_economics") and not p.get("summary"):
                continue
            if p.get("period") == "Long-term":
                row["verdict"] = "long_term"
            elif p["metric"] not in CHECKABLE or p.get("unit") not in ("%", None) or not pq:
                row["verdict"] = "unverifiable"
            else:
                val, n = actual(qd, p["metric"], pq)
                row["actual"], row["reported"], row["of"] = val, n, len(pq)
                row["verdict"], row["gap"] = _verdict(p, val, n, len(pq))
                if p["metric"] == "ebitda_margin" and val is not None and p.get("low") is not None and abs(val - p["low"]) > 8 \
                        and (p.get("high") is None or abs(val - p["high"]) > 8):
                    # a "margin" band nowhere near the company's margin level is a mislabelled number
                    row.update(verdict="unverifiable", actual=None, gap=None)
                row["actual_basis"] = ("reported ₹ revenue YoY" if p["metric"] == "revenue_growth" else
                                       "reported operating (EBITDA) margin" if p["metric"] == "ebitda_margin" else "reported PAT YoY")
            row["verdict_label"] = VERDICT_LABEL[row["verdict"]]
            rows.append(row)
    good = sum(r["verdict"] in ("delivered", "beat", "on_track", "ahead") for r in rows)
    bad = sum(r["verdict"] in ("missed", "behind") for r in rows)
    near = sum(r["verdict"] in ("near_miss", "slightly_behind") for r in rows)
    scored = good + bad + near
    timeline = []
    for t in sorted(transcripts, key=lambda t: (t["fy"], t["q"])):
        k = (t["q"], t["fy"])
        a = qd.get(k, {})
        prev = qd.get((t["q"], t["fy"] - 1), {})
        timeline.append({
            "label": t["label"], "tone": (t.get("tone") or {}).get("score"), "url": t["url"],
            "said": [p.get("summary") or p["text"] for p in t["promises"][:2]],
            "sales_yoy": round(100 * (a["sales"] / prev["sales"] - 1), 1) if a.get("sales") and prev.get("sales") else None,
            "opm": round(100 * a["op"] / a["sales"], 1) if a.get("sales") and a.get("op") is not None else None,
            "pat_yoy": round(100 * (a["pat"] / prev["pat"] - 1), 1) if a.get("pat") and prev.get("pat") and prev["pat"] > 0 else None,
        })
    return {
        "rows": rows, "timeline": timeline,
        "score": {"kept": good, "near": near, "missed": bad, "scored": scored,
                  "credibility": round(100 * (good + 0.5 * near) / scored) if scored else None},
        "narrative": narrative(rows, timeline),
    }


def _fmt_target(r):
    lo, hi = r.get("low"), r.get("high")
    if lo is None:
        return "direction only"
    if lo == 0 and hi is None and r["metric"] == "revenue_growth":
        return "a return to growth"
    if hi is None:
        return f"{lo:g}%+"
    return f"{lo:g}%" if lo == hi else f"{lo:g}–{hi:g}%"


def narrative(rows, timeline):
    """Deterministic 'said vs did' statements; the strong model can rewrite these if configured."""
    out = []
    for r in rows:
        if r["verdict"] in ("unverifiable", "long_term", "pending") or r.get("actual") is None:
            continue
        stance = "agree" if r["verdict"] in ("delivered", "beat", "on_track", "ahead") else "diverge"
        part = "so far " if r.get("reported", 0) < r.get("of", 0) else ""
        out.append({"stance": stance,
                    "text": f"{r['said_in']}: guided {r['metric_label'].lower()} of {_fmt_target(r)} for {r['period']}; "
                            f"{part}{r['actual']:g}% ({r['reported']}/{r['of']} quarters) → {r['verdict_label'].lower()}.",
                    "evidence": f"{r['said_in']} transcript p.{r['page']}"})
    # tone vs. trend: management mood rising while growth falls (or vice versa) is the classic tell
    pts = [t for t in timeline if t["tone"] is not None and t["sales_yoy"] is not None]
    if len(pts) >= 3:
        dt = pts[-1]["tone"] - pts[0]["tone"]
        dg = pts[-1]["sales_yoy"] - pts[0]["sales_yoy"]
        if dt > 0.1 and dg < -3:
            out.append({"stance": "diverge", "text": f"Tone brightened ({pts[0]['tone']:+.2f} → {pts[-1]['tone']:+.2f}) while revenue growth slowed "
                        f"({pts[0]['sales_yoy']:.0f}% → {pts[-1]['sales_yoy']:.0f}% YoY) between {pts[0]['label']} and {pts[-1]['label']}.",
                        "evidence": "Tone index across calls vs reported quarters"})
        elif dt < -0.1 and dg > 3:
            out.append({"stance": "diverge", "text": f"Management sounded more cautious ({pts[0]['tone']:+.2f} → {pts[-1]['tone']:+.2f}) even as growth "
                        f"improved ({pts[0]['sales_yoy']:.0f}% → {pts[-1]['sales_yoy']:.0f}% YoY) — under-promising?",
                        "evidence": "Tone index across calls vs reported quarters"})
        else:
            out.append({"stance": "agree", "text": f"Management's tone moved in step with the numbers from {pts[0]['label']} to {pts[-1]['label']}.",
                        "evidence": "Tone index across calls vs reported quarters"})
    return out

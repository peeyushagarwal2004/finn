"""Quarterly results -> headline numbers, read from the exchange filing itself.

Indian results follow SEBI's format: every line item carries this quarter, the previous
quarter and the same quarter last year as its first three columns. So QoQ and YoY come
straight out of one document with a regex pass and no model call. The parse is then
cross-checked against screener's standardised table; if the two disagree we show the
standardised numbers and say so.
"""
import re
from datetime import datetime

from ..sources import pdf, screener

ROW_PATTERNS = {
    "revenue": r"(?:total\s+)?revenue\s+from\s+operations(?:\s*\(net\))?|income\s+from\s+operations|net\s+sales",
    "other_income": r"other\s+income",
    "finance": r"finance\s+costs?|interest\s+(?:and\s+finance\s+)?(?:costs?|expenses?)",
    "dep": r"depreciation(?:,)?\s+(?:and|&)\s+amorti[sz]ation(?:\s+expenses?)?|depreciation",
    "pbt_pre": r"profit\s*/?\s*(?:\(loss\))?\s*before\s+exceptional\s+items\s+and\s+tax",
    "pbt": r"(?:total\s+)?profit\s*/?\s*(?:\(loss\))?\s*before\s+(?:income\s+)?tax(?:es)?(?!\s+and\s+exceptional)",
    "pat": r"(?:net\s+)?profit\s*/?\s*(?:\(loss\))?\s*(?:for\s+the\s+(?:period|quarter|year)|after\s+tax)",
}
NUM = re.compile(r"\(?-?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?\)?(?![\d,])|(?<!\S)-(?!\S)")


def _nums(s):
    out = []
    for tok in NUM.findall(s):
        if tok == "-":
            out.append(0.0)
            continue
        neg = tok.startswith("(") or tok.startswith("-")
        try:
            v = float(tok.strip("()-").replace(",", ""))
        except ValueError:
            continue
        out.append(-v if neg else v)
    return out


def _unit(text):
    t = text.lower()
    if re.search(r"(in|rs\.?|₹|inr)\s*(\w+\s+)?lakhs?|lacs", t):
        return 0.01
    if re.search(r"(in|rs\.?|₹|inr)\s*(\w+\s+)?millions?|\bmn\b", t):
        return 0.1
    if re.search(r"(in|rs\.?|₹|inr)\s*(\w+\s+)?billions?", t):
        return 100.0
    return 1.0


def _parse_page(text):
    lines = text.split("\n")
    found = {}
    for key, pat in ROW_PATTERNS.items():
        # row prefixes seen in the wild: "5) ", "3 |", ") ", "(a) ", "IV. ", "A "
        rx = re.compile(r"^\s*(?:[(\[]?(?:\d{1,2}|[a-z]|[ivx]{1,4})[)\].:|]?\s*)?[)|]?\s*(?:" + pat + r")\b(.*)$", re.I)
        for ln in lines:
            m = rx.match(ln)
            if not m:
                continue
            rest = re.sub(r"\(\s*(?:refer\s+)?note\s*\d+\s*\)", "", m.group(1), flags=re.I)
            # formula references such as (3+4), (1-2), (5.6) are row arithmetic, not figures
            rest = re.sub(r"\(\s*[0-9A-Za-z]{1,4}(?:\s*[-+.x±]\s*[0-9A-Za-z]{1,4})+\s*\)", " ", rest)
            rest = re.sub(r"\((?:net of tax|i+|[a-z])\)", " ", rest, flags=re.I)
            vals = [v for v in _nums(rest)]
            # skip short note numbers that precede the figures ("Revenue from operations 4 73,188 ...")
            if len(vals) >= 4 and abs(vals[0]) < 50 and abs(vals[1]) > 500:
                vals = vals[1:]
            if len(vals) >= 3:
                found[key] = vals[:3]
                break
    return found


LLM_PROMPT = """Below is one page of an Indian company's quarterly results filing.
Extract the {basis} statement's first three numeric columns: [this quarter, previous quarter, same quarter last year].
Return JSON: {{"unit": "crore|lakh|million", "revenue": [..3], "other_income": [..3], "finance": [..3],
"dep": [..3], "pbt": [..3], "pat": [..3]}} — revenue = revenue from operations, pbt = profit before tax,
pat = profit for the period. Numbers only (negative for losses), null if a row is absent. Digits may be
split by OCR spaces ("10,5 10.51" = 10510.51).

PAGE:
{page}"""


def _llm_parse(pages, basis):
    """Cheap-model fallback: send only the single best statement page, not the whole filing."""
    from .. import llm
    best = None
    for text in pages:
        head = text[:1500].lower()
        if re.search(r"revenue|income from operations", text, re.I) and re.search(r"before\s+tax", text, re.I):
            rank = (basis in head) * 2 + ("statement" in head)
            if best is None or rank > best[0]:
                best = (rank, text)
    if not best:
        return None
    js = llm.ask_json(LLM_PROMPT.format(basis=basis, page=best[1][:7000]), tier="cheap", max_tokens=600)
    if not isinstance(js, dict) or not js.get("revenue"):
        return None
    k = {"lakh": 0.01, "million": 0.1}.get(str(js.get("unit", "crore")).lower(), 1.0)
    rows = {}
    for key in ("revenue", "other_income", "finance", "dep", "pbt", "pat"):
        v = js.get(key)
        if isinstance(v, list) and len(v) >= 3 and all(isinstance(x, (int, float)) for x in v[:3]):
            rows[key] = [round(x * k, 2) for x in v[:3]]
    return rows if {"revenue", "pat", "pbt"} <= rows.keys() else None


def parse_filing(url, basis="consolidated"):
    """Return {'consolidated': {...}, 'standalone': {...}} of parsed headline rows (₹ cr).
    Regex first (free); the cheap model only sees the page when regex finds nothing usable."""
    out = _regex_parse(url)
    if basis not in out:
        rows = _llm_parse(pdf.pages(url, max_pages=40), basis)
        if rows:
            out[basis] = rows
            out["_llm"] = True
    return out


def _regex_parse(url):
    out = {}
    for text in pdf.pages(url, max_pages=40):
        if not re.search(r"revenue|income from operations", text, re.I):
            continue
        head = text[:1500].lower()
        basis = "consolidated" if "consolidated" in head and "standalone" not in head[:head.find("consolidated")] else "standalone"
        rows = _parse_page(text)
        if {"revenue", "pat"} <= rows.keys() and ("pbt" in rows or "pbt_pre" in rows) and basis not in out:
            k = _unit(text[:2500])
            out[basis] = {r: [round(v * k, 2) for v in vals] for r, vals in rows.items()}
    return out


def _ebitda(rows, i):
    pbt = rows.get("pbt_pre", rows.get("pbt"))
    if not pbt or "finance" not in rows or "dep" not in rows:
        return None
    return pbt[i] + rows["finance"][i] + rows["dep"][i] - rows.get("other_income", [0, 0, 0])[i]


def fy_label(header):
    """'Sep 2026' -> 'Q2 FY27'."""
    mon, yr = header.split()
    q = {"Jun": 1, "Sep": 2, "Dec": 3, "Mar": 4}.get(mon)
    fy = int(yr) + (0 if mon == "Mar" else 1)
    return f"Q{q} FY{str(fy)[-2:]}" if q else header


def _close(a, b, tol=0.03):
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(abs(b), 1)


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round(100 * (a - b) / abs(b), 1)


def _from_table(q, lender):
    """Headline rows from screener's quarterly table (fallback + cross-check)."""
    r, h = q["rows"], q["headers"]
    idx = [len(h) - 1, len(h) - 2, len(h) - 5]
    def pick(*names):
        for n in names:
            if n in r:
                return [r[n][i] if -len(r[n]) <= i < len(r[n]) else None for i in idx]
        return [None] * 3
    rev, intr = pick("Sales", "Revenue"), pick("Interest")
    return {
        "revenue": rev,
        "ebitda": [None] * 3 if lender else pick("Operating Profit"),
        "pbt": pick("Profit before tax"),
        "pat": pick("Net Profit"),
        "nii": [a - b if a is not None and b is not None else None for a, b in zip(rev, intr)] if lender else None,
    }, [h[i] for i in idx]


def headline(symbol, lender=False):
    """First-cut results card for the latest reported quarter."""
    co = screener.company(symbol)
    q = co["tables"].get("quarters")
    if not q or len(q["headers"]) < 5:
        return None
    std, cols = _from_table(q, lender)
    period = fy_label(cols[0])
    src = screener.results_source_url(co["company_id"], cols[0]) if co.get("company_id") else None
    parsed, method, note = None, "standardised", None
    if src and not lender:
        try:
            filing = parse_filing(src, co.get("basis", "consolidated"))
        except Exception:
            filing = {}
        cand = filing.get(co.get("basis", "consolidated")) or filing.get("consolidated") or filing.get("standalone")
        if cand and _close(cand["revenue"][0], std["revenue"][0]):
            parsed = {"revenue": cand["revenue"], "ebitda": [_ebitda(cand, i) for i in range(3)],
                      "pbt": cand.get("pbt", cand.get("pbt_pre")), "pat": cand["pat"]}
            patched = []
            for k in ("ebitda", "pbt", "pat"):
                if not parsed[k] or not all(_close(a, b, 0.06) for a, b in zip(parsed[k], std[k]) if b is not None):
                    parsed[k] = std[k]
                    patched.append(k.upper())
            method = "filing" if not patched else "filing+standardised"
            if filing.get("_llm"):
                method += " (model-read)"
            if patched:
                note = f"{', '.join(patched)} taken from the standardised table (filing row didn't reconcile)."
        elif cand:
            note = "Filing layout didn't reconcile with reported totals; showing standardised figures."
    rows = parsed or {k: v for k, v in std.items() if k != "nii"}
    lines = []
    for key, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pbt", "PBT"), ("pat", "PAT")]:
        v = rows.get(key) or [None] * 3
        if key == "ebitda" and lender:
            op = std.get("nii") or [None] * 3
            lines.append({"key": "nii", "label": "NII", "note": "EBITDA isn't meaningful for a lender; net interest income shown instead",
                          "cur": op[0], "prev": op[1], "yoy": op[2], "qoq_pct": _pct(op[0], op[1]), "yoy_pct": _pct(op[0], op[2])})
            continue
        lines.append({"key": key, "label": label, "cur": v[0], "prev": v[1], "yoy": v[2],
                      "qoq_pct": _pct(v[0], v[1]), "yoy_pct": _pct(v[0], v[2])})
    rev = rows["revenue"]
    margins = {}
    if rows.get("ebitda") and rows["ebitda"][0] is not None and rev[0]:
        margins = {"ebitda_margin": round(100 * rows["ebitda"][0] / rev[0], 1),
                   "ebitda_margin_yoy": round(100 * rows["ebitda"][2] / rev[2], 1) if rows["ebitda"][2] and rev[2] else None}
    if rows.get("pat") and rows["pat"][0] is not None and rev[0]:
        margins["pat_margin"] = round(100 * rows["pat"][0] / rev[0], 1)
    trend_key = "Sales" if "Sales" in q["rows"] else "Revenue"
    import calendar
    from datetime import date
    mon, yr = cols[0].split()
    mnum = datetime.strptime(mon, "%b").month
    period_end = date(int(yr), mnum, calendar.monthrange(int(yr), mnum)[1]).isoformat()
    return {
        "period": period, "period_end": period_end, "columns": [period, fy_label(cols[1]), fy_label(cols[2])],
        "lines": lines, "margins": margins, "method": method, "note": note,
        "verified": method.startswith("filing"),"source_url": src, "basis": co.get("basis"),
        "trend": {"labels": [fy_label(x) for x in q["headers"][-8:]],
                  "revenue": q["rows"].get(trend_key, [])[-8:],
                  "pat": q["rows"].get("Net Profit", [])[-8:]},
        "headline": _headline_text(lines, margins),
    }


def _headline_text(lines, margins):
    d = {l["key"]: l for l in lines}
    bits = []
    rv = d.get("revenue")
    if rv and rv["yoy_pct"] is not None:
        bits.append(f"Revenue {rv['yoy_pct']:+.0f}% YoY")
    pt = d.get("pat")
    if pt and pt["yoy_pct"] is not None:
        bits.append(f"PAT {pt['yoy_pct']:+.0f}% YoY")
    if margins.get("ebitda_margin") is not None and margins.get("ebitda_margin_yoy") is not None:
        bps = round(100 * (margins["ebitda_margin"] - margins["ebitda_margin_yoy"]))
        bits.append(f"margin {'+' if bps >= 0 else ''}{bps} bps")
    return ", ".join(bits)

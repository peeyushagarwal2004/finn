"""Concall transcripts -> what management promised, as structured, quotable claims.

Pipeline (cheapest first):
  1. Split the transcript into speaker turns; drop the moderator and analysts.
  2. Keep management sentences that look forward ("expect", "FY27", "guide") AND carry a
     quantity or a headline metric. A 50-page call shrinks to ~25 sentences.
  3. Parse those sentences deterministically (metric, range, period). Phrases like
     "high single digit" or "mid-teens" map to numeric bands.
  4. If a model is configured, the cheap tier re-labels the same numbered sentences.
     It can only point at sentence ids, so every quote shown is verbatim from the source.
"""
import re
from collections import Counter

from .. import llm, store
from ..sources import pdf, screener

FWD = re.compile(r"\b(?:expect\w*|anticipat\w*|guid\w*|target\w*|aim(?:s|ing)?\b|aspir\w*|outlook|going forward|"
                 r"should (?:be|see|grow|reach|come)|will (?:be|grow|see|reach|deliver|achieve|continue|remain|come)|"
                 r"we see|confiden\w*|plan(?:s|ned|ning)? to|looking at|endeavou?r|trajectory|"
                 r"for (?:the )?(?:full )?year|next (?:year|quarter|fiscal|few)|this (?:year|fiscal)|"
                 r"fy\s*'?\d{2}\b|h[12]\b|second half|first half|medium[- ]term|by 20\d\d|"
                 r"maintain\w*|sustain\w*|band\b|range\b|on track)", re.I)
PAST = re.compile(r"\b(grew|was|were|delivered|reported|recorded|achieved|posted|declined|came in at)\b", re.I)
QTY = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|per cent|bps|basis points|crores?|cr\b|billion|million|x\b)|"
                 r"(?:double|single)[- ]digit|(?:low|mid|high)[- ](?:single|double|teens|twenties)|teens|twenties", re.I)
METRIC = [
    # cost ratios and macro talk carry percentages but are not company headline guidance
    ("other_", r"a ?& ?sp\b|a ?& ?p\b|advertis\w*|ad spend|employee cost|staff cost|tax rate|\betr\b|effective tax|as a percentage of|"
               r"attrition|utili[sz]ation|headcount|international share|share of|"
               r"% of (?:sales|revenue)|\bgdp\b|economy|inflation|industry (?:growth|is growing|will grow)|market (?:growth|is growing|will grow)"),
    # checked before margins/revenue: a yield or per-unit target is not a P&L headline
    ("unit_economics_",r"\b(?:p?rask|cask|yields?|per unit|unit (?:passenger )?revenue|arpu|realis\w*|realiz\w*|gross margin|contribution margin)\b"),
    ("ebitda_margin", r"\b(ebitda|ebit|operating) margins?|\bmargins?\b|\bopm\b"),
    ("nim", r"net interest margin|\bnim\b"),
    ("credit_cost", r"credit cost"),
    ("aum_growth", r"\baum\b|loan book|advances|disburse"),
    ("profit_growth", r"\bpat\b|net profit|bottom[- ]line|profit growth|earnings growth"),
    ("unit_economics", r"\b(?:p?rask|cask|yields?|per unit|unit (?:passenger )?revenue|arpu|realis\w*|realiz\w*|asp|pricing|gross margin|contribution margin)\b"),
    ("capex", r"capex|capital expenditure|invest(?:ment)? of"),
    ("orders", r"order (?:book|inflow|intake|pipeline)|deal wins|tcv"),
    ("volume_growth", r"capacity|\basks?\b|volumes?\b|passengers|tonnage|units\b|footfall|store additions|new stores"),
    ("revenue_growth", r"revenue|top[- ]?line|\bsales\b|growth|grow\b|growing"),
]
CHECKABLE = {"revenue_growth", "ebitda_margin", "profit_growth"}
METRIC_LABEL = {"revenue_growth": "Revenue growth", "ebitda_margin": "Operating margin", "profit_growth": "Profit growth",
                "capex": "Capex", "orders": "Orders", "aum_growth": "Loan/AUM growth", "nim": "NIM",
                "volume_growth": "Volume / capacity", "unit_economics": "Unit economics",
                "credit_cost": "Credit cost", "other": "Other"}
WORDS = [(r"low[- ]single[- ]digit", 1, 4), (r"mid[- ]single[- ]digit", 4, 6), (r"high[- ]single[- ]digit", 7, 9),
         (r"low[- ]double[- ]digit|low[- ]teens", 10, 13), (r"mid[- ]teens", 14, 16), (r"high[- ]teens", 17, 19),
         (r"double[- ]digit", 10, None), (r"(?:low|early)[- ]twenties", 20, 23), (r"mid[- ]twenties", 24, 26),
         (r"high[- ]twenties", 27, 29), (r"single[- ]digit", 1, 9)]
JUNK_SPEAKERS = {"cin", "encl", "subject", "kind attn", "scrip code", "scrip id", "series", "symbol", "management",
                 "note", "disclaimer", "page", "date", "dear sir", "ref", "website", "email", "sub"}


def _fy_of_call(month, year):
    """Concall in Jul-Sep discusses Q1, Oct-Dec Q2, Jan-Mar Q3, Apr-Jun Q4."""
    m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(month) + 1
    if m in (7, 8, 9):
        return 1, year + 1
    if m in (10, 11, 12):
        return 2, year + 1
    if m in (1, 2, 3):
        return 3, year
    return 4, year


def quarter_label(text, month, year):
    hits = Counter()
    for m in re.finditer(r"\bQ([1-4])\s*[-' ]?\s*(?:FY|F\.Y\.)\s*'?(?:20)?(\d{2})\b", text[:12000], re.I):
        hits[(int(m.group(1)), 2000 + int(m.group(2)))] += 1
    if hits:
        return hits.most_common(1)[0][0]
    return _fy_of_call(month, year)


def turns(pages):
    """[(speaker, text, page)] for every speaker turn."""
    out, cur, buf, page0 = [], None, [], 0
    rx = re.compile(r"^\s*([A-Z][A-Za-z.' \-]{2,42}?)\s*:\s+(.*)$")
    for pno, page in enumerate(pages):
        for ln in page.split("\n"):
            if re.match(r"^\s*(Page \d+ of \d+|.*Limited\s*$|[A-Z][a-z]+ \d{1,2}, 20\d\d\s*$)", ln):
                continue
            m = rx.match(ln)
            if m and m.group(1).strip().lower() not in JUNK_SPEAKERS and len(m.group(1).split()) <= 5:
                if cur:
                    out.append((cur, " ".join(buf), page0))
                cur, buf, page0 = m.group(1).strip(), [m.group(2)], pno + 1
            elif cur:
                buf.append(ln.strip())
    if cur:
        out.append((cur, " ".join(buf), page0))
    return out


def _intro_names(full_text, speakers):
    """Speakers named in the cover page / opening ('On the call today we have Mr. X, CFO')."""
    head = full_text[:6000].lower()
    head = head[:head.find("question-and-answer")] if "question-and-answer" in head else head
    named = set()
    for sp in speakers:
        parts = [p for p in re.split(r"[\s.]+", sp.lower()) if len(p) > 2]
        if len(parts) >= 2 and parts[0] in head and parts[-1] in head:
            named.add(sp)
    return named


def management(trns, full_text):
    speakers = {sp for sp, _, _ in trns}
    host = re.search(r"hand (?:the conference |it )?over to (?:Mr\.?|Ms\.?|Mrs\.?)?\s*([A-Z][a-z]+)", full_text[:5000])
    intro = _intro_names(full_text, speakers)
    if host:
        intro = {s for s in intro if not s.lower().startswith(host.group(1).lower())}
    analysts = set()
    for m in re.finditer(r"(?:line of|question (?:is )?from|over to)\s+(?:Mr\.?|Ms\.?|Mrs\.?)?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\s+(?:from|with|of)\b", full_text):
        analysts.add(m.group(1).split()[0].lower())
    stats = {}
    for sp, txt, _ in trns:
        s = stats.setdefault(sp, [0, 0, 0])
        s[0] += 1
        s[1] += txt.count("?") > 0
        s[2] += len(txt)
    mgmt = set()
    for sp, (n, q, ln) in stats.items():
        low = sp.lower()
        if "moderator" in low or "operator" in low or low.split()[0] in analysts or len(sp.split()) < 2:
            continue
        if not re.match(r"^[A-Z][a-z]", sp) or re.search(r"\b(office|no|terms|of|the|in)\b", low):
            continue
        if n >= 2 and q / n > 0.6:  # mostly asks questions -> analyst
            continue
        mgmt.add(sp)
    # trust the intro list when it names at least one speaker; it is the cleanest signal
    named = {s for s in intro if (s in mgmt or s.split()[0].lower() not in analysts)
             and not re.search(r"\b(office|no|terms)\b", s.lower()) and "moderator" not in s.lower()}
    return named if named else mgmt


POS = re.compile(r"\b(strong\w*|robust|healthy|confiden\w*|record|momentum|accelerat\w*|improv\w*|opportunit\w*|"
                 r"encourag\w*|optimis\w*|resilien\w*|buoyant|upbeat|outperform\w*|tailwind\w*|excit\w*)\b", re.I)
NEG = re.compile(r"\b(challeng\w*|headwind\w*|weak\w*|uncertain\w*|slowdown|pressure\w*|declin\w*|delay\w*|soft\w*|"
                 r"cautious|difficult\w*|muted|subdued|volatil\w*|disrupt\w*|deferr\w*|sluggish|concern\w*)\b", re.I)


def tone(text):
    """(pos - neg) / (pos + neg) over management's own words; -1 gloomy .. +1 euphoric."""
    p, n = len(POS.findall(text)), len(NEG.findall(text))
    return {"score": round((p - n) / (p + n), 2) if p + n else 0.0, "pos": p, "neg": n}


def _sentences(text):
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text) if 40 <= len(s.strip()) <= 420]


def _metric(s):
    for name, rx in METRIC:
        if re.search(rx, s, re.I):
            return name.rstrip("_")
    return "other"


def _ctx_metric(text, everything=False):
    best, pos = None, -1
    for name, rx in METRIC:
        name = name.rstrip("_")
        if name not in CHECKABLE and not (everything and name not in ("other", "unit_economics")):
            continue
        if everything and name == "revenue_growth":
            rx = r"revenue|sales|top[- ]?line|turnover"  # only an explicit revenue mention counts here
        for m in re.finditer(rx, text, re.I):
            if m.start() > pos:
                best, pos = name, m.start()
    return best


def _band(s):
    for rx, lo, hi in WORDS:
        if re.search(rx, s, re.I):
            return lo, hi, "%"
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*(?:-|–|to|,|or)\s*(\d+(?:\.\d+)?)\s*(%|percent|per cent)", s, re.I)
    if m:
        return float(m.group(1)), float(m.group(2)), "%"
    m = re.search(r"(?:(at least|over|more than|upwards of|in excess of|north of|above)\s+|(?:~|about|around|approximately|close to|roughly)\s*)?(\d+(?:\.\d+)?)\s*(%|percent|per cent)", s, re.I)
    if m:
        v = float(m.group(2))
        return (v, None, "%") if m.group(1) else (v, v, "%")
    m = re.search(r"(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b)", s, re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        return v, v, "cr"
    return None, None, None


def _period(s, q, fy):
    m = re.search(r"\bH([12])\s*(?:FY\s*'?(?:20)?(\d{2}))?", s, re.I)
    if m:
        return f"H{m.group(1)} FY{m.group(2) or str(fy)[-2:]}"
    if re.search(r"second half", s, re.I):
        return f"H2 FY{str(fy)[-2:]}"
    m = re.search(r"\bFY\s*'?(?:20)?(\d{2})\b|\b(?:fiscal|financial year)\s*(?:20)?(\d{2})\b", s, re.I)
    if m:
        return f"FY{m.group(1) or m.group(2)}"
    if re.search(r"next (?:year|fiscal|financial year)", s, re.I):
        return f"FY{str(fy + 1)[-2:]}"
    if re.search(r"this (?:year|fiscal|financial year)|current (?:year|fiscal)|full[- ]year|for the year", s, re.I):
        return f"FY{str(fy)[-2:]}"
    if re.search(r"next quarter|coming quarter|q[1-4] onwards", s, re.I):
        nq, nfy = (q + 1, fy) if q < 4 else (1, fy + 1)
        return f"Q{nq} FY{str(nfy)[-2:]}"
    if re.search(r"medium[- ]term|long[- ]term|\d\s*(?:-|to)\s*\d\s*years|next few years|by 20\d\d", s, re.I):
        return "Long-term"
    return f"FY{str(fy)[-2:]}" if q <= 2 else None


RETRO = re.compile(r"came in at|grew by|we (?:delivered|reported|posted|recorded)|exiting|was (?:up|down) |"
                   r"in line with (?:our )?(?:the )?(?:revised )?guidance|stood at|registering|registered a|would have been|"
                   r"take you through|for the quarter gone by|during the quarter", re.I)
DIRECTIONAL = re.compile(r"return to growth|will (?:improve|recover|be better|pick up|accelerate|expand|normali[sz]e)|"
                         r"better than h1|margins? (?:will|should) (?:improve|expand|recover)|guidance|outlook", re.I)


def candidates(trns, mgmt):
    out = []
    prev_q = ""
    for sp, txt, page in trns:
        if sp not in mgmt:
            prev_q = txt[-600:]  # the analyst's question gives the metric context for the answer
            continue
        sents = _sentences(txt)
        for i, s in enumerate(sents):
            fwd, qty = FWD.search(s), QTY.search(s)
            directional = bool(DIRECTIONAL.search(s))
            if not fwd or not (qty or directional or re.search(r"target|band", s, re.I)):
                continue
            if RETRO.search(s) and not re.search(r"\b(expect\w*|will|going forward|should)\b", s, re.I):
                continue
            if PAST.search(s) and not re.search(r"expect|guid|target|will|going forward|outlook|should", s, re.I):
                continue
            metric = _metric(s)
            ctx = prev_q + " " + " ".join(sents[max(0, i - 2):i])
            if metric == "other" and not re.search(METRIC[0][1], s, re.I):
                # the sentence names no metric ("26-28% is our guiding beacon"): borrow the headline
                # metric mentioned most recently before it — in this answer or the analyst's question
                metric = _ctx_metric(ctx) or metric
            elif metric == "revenue_growth" and not re.search(r"revenue|sales|top[- ]?line|turnover", s, re.I):
                # a bare "growth" means whatever was just being discussed (capacity? volumes? revenue?)
                alt = _ctx_metric(ctx, everything=True)
                if alt in ("volume_growth", "aum_growth", "profit_growth", "orders"):  # growth of *what*, never a margin
                    metric = alt
            score = 2 * bool(re.search(r"guid|target|outlook|band|range", s, re.I)) + bool(qty) + \
                bool(re.search(r"FY\s*'?\d{2}|this year|next year|H[12]\b", s, re.I)) + (metric in CHECKABLE)
            out.append({"speaker": sp, "text": s, "page": page, "score": score, "metric_hint": metric})
    out.sort(key=lambda c: -c["score"])
    return out[:28]


LLM_PROMPT = """These numbered sentences are from {company}'s {label} earnings call, spoken by management.
Identify the ones that are forward-looking GUIDANCE on headline numbers (growth, margins, profit, capex,
orders, loan growth, NIM, credit cost). Ignore past results and vague aspirations without a direction.
Return JSON {{"items": [{{"id": <sentence id>, "metric": one of {metrics}, "low": number|null, "high": number|null,
"unit": "%"|"cr"|"x"|null, "period": "FY27"|"H2 FY27"|"Q3 FY27"|"Long-term"|null, "explicit": true|false,
"summary": "<= 12 words, plain English"}}]}}
"explicit" = a number or a clear numeric band was stated. Growth figures are YoY unless stated.

{sents}"""


def extract(symbol, max_calls=4):
    """Promises from the last few concalls, newest first. Cached per transcript."""
    co = screener.company(symbol)
    calls = []
    seen = set()
    for c in co["documents"]["concalls"]:
        if not c.get("transcript") or (c["month"], c["year"]) in seen:
            continue
        seen.add((c["month"], c["year"]))
        calls.append(c)
        if len(calls) >= max_calls:
            break
    out = []
    for c in calls:
        key = f"{symbol}:{c['transcript']}"
        cached = store.kv_get("guidance", key)
        if cached is None:
            cached = _extract_one(co, c)
            if cached.get("pages"):
                store.kv_set("guidance", key, cached)
        out.append(cached)
    # newest first, and only one transcript per fiscal quarter
    by_q = {}
    for t in out:
        if t.get("q") and (t["fy"], t["q"]) not in by_q:
            by_q[(t["fy"], t["q"])] = t
    return sorted(by_q.values(), key=lambda t: (t["fy"], t["q"]), reverse=True)


def _extract_one(co, c):
    pages = pdf.pages(c["transcript"], max_pages=45)
    text = "\n".join(pages)
    q, fy = quarter_label(text, c["month"], c["year"])
    base = {"label": f"Q{q} FY{str(fy)[-2:]}", "q": q, "fy": fy, "url": c["transcript"],
            "call": f"{c['month']} {c['year']}", "pages": len(pages), "promises": []}
    if not text.strip():
        return base
    trns = turns(pages)
    mgmt = management(trns, text)
    cands = candidates(trns, mgmt)
    base["speakers"] = sorted(mgmt)[:8]
    base["candidates"] = len(cands)
    base["tone"] = tone(" ".join(t for sp, t, _ in trns if sp in mgmt))
    js = None
    if cands:
        numbered = "\n".join(f"[{i}] ({c_['speaker']}) {c_['text']}" for i, c_ in enumerate(cands))
        js = llm.ask_json(LLM_PROMPT.format(company=co["name"], label=base["label"], sents=numbered,
                                            metrics="|".join(METRIC_LABEL)), tier="cheap", max_tokens=1800)
    promises = []
    if isinstance(js, dict) and isinstance(js.get("items"), list):
        base["method"] = "model-labelled"
        for it in js["items"]:
            try:
                cand = cands[int(it["id"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            metric = it.get("metric") if it.get("metric") in METRIC_LABEL else cand["metric_hint"]
            promises.append({**cand, "metric": metric, "low": it.get("low"), "high": it.get("high"), "unit": it.get("unit"),
                             "period": it.get("period") or _period(cand["text"], q, fy), "explicit": bool(it.get("explicit")),
                             "summary": it.get("summary")})
    else:
        base["method"] = "rules"
        for cand in cands:
            if cand["score"] < 3:
                continue
            lo, hi, unit = _band(cand["text"])
            metric = cand["metric_hint"]
            if lo is None and re.search(r"return to (?:revenue )?growth|back to growth|grow again", cand["text"], re.I) and metric == "revenue_growth":
                lo, unit = 0.0, "%"  # "we will return to growth" is checkable: YoY > 0
            if lo is None:  # rules can't safely interpret an unquantified sentence; the model path can
                continue
            period = _period(cand["text"], q, fy)
            if metric in ("other", "unit_economics") or period is None:
                continue  # a wrong verdict is worse than none: rules keep only what they can place
            promises.append({**cand, "metric": metric, "low": lo, "high": hi, "unit": unit,
                             "period": period, "explicit": lo is not None, "summary": None})
    # one promise per (metric, period): keep the most explicit/highest-scoring statement
    best = {}
    for p in promises:
        k = (p["metric"], p["period"])
        if k not in best or (p["explicit"], p["score"]) > (best[k]["explicit"], best[k]["score"]):
            best[k] = p
    base["promises"] = sorted(best.values(), key=lambda p: (not p["explicit"], -p["score"]))[:8]
    return base

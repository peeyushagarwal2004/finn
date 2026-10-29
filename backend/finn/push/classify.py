"""Filing -> (category, materiality 0-100, reasons).

Deterministic on purpose: exchange subjects and BSE titles are formulaic, so ordered
regex rules classify ~all filings for free and explain themselves. The score starts
from a category base and is moved by what the filing actually says — who left, how big
the order is relative to the company, whether a rating went up or down.
"""
import re

# (category, sub-type, base score, pattern) — first match wins, so specific rules come first.
RULES = [
    ("unclassified", "trading_window", 3, r"trading window|reg(ulation)?\.? ?74 ?\(5\)|certificate under reg|compliance certificate|loss of share certificate|duplicate share|newspaper (publication|advertisement)(?!.*result)|monitoring agency|iepf|investor education and protection|unclaimed"),
    ("litigation", "auditor_exit", 85, r"resignation of (the )?(statutory |secretarial )?auditor"),
    # an intimation that results WILL be considered is a calendar entry, not results
    ("results", "board_meeting_notice", 30, r"board meeting intimation|intimation of (the )?board meeting|prior intimation|will be held on|to consider and approve"),
    ("results", "results", 90, r"financial results?|un-?audited results|audited results|integrated filing.*financial|results? for the (quarter|period|year)|reported q[1-4]|q[1-4] ?fy\d\d (revenue|results|pat|profit)"),
    ("results", "deck", 40, r"investor presentation|shareholders?'? letter|results presentation|earnings (presentation|release)|press release.*results"),
    ("earnings_call", "transcript", 35, r"transcript"),
    ("earnings_call", "recording", 10, r"(audio|video) recording|recording of"),
    ("management_change", "change", 60, r"change in (directorate|management|key managerial|senior management)|appointment|resignation|cessation|re-?appointment|retire|steps? down|(managing director|chief executive|ceo|cfo|chief financial)"),
    ("M&A", "deal", 75, r"acquisition|acquire|amalgamation|merger|demerger|scheme of arrangement|joint venture|\bjv\b|stake (sale|purchase)|divest|slump sale|incorporation of (a )?(wholly|subsidiary)|investment in (wholly|subsidiary)"),
    ("fund_raise", "buyback", 75, r"buy-?back"),
    ("fund_raise", "equity", 70, r"\bqip\b|qualified institutional|rights issue|preferential (issue|allotment)|fund ?rais|issue of (equity|warrants)"),
    ("fund_raise", "debt", 25, r"commercial paper|non-convertible|\bncds?\b|debentures?|bonds?"),
    ("pledging", "pledge", 70, r"pledge|encumbrance"),
    ("insider_trading", "insider", 30, r"insider trading|reg(ulation)? 7\(2\)|regulation 29|regulation 31|\bsast\b|substantial acquisition|disclosure.*(acquisition|disposal) of shares"),
    ("credit_rating", "rating", 35, r"credit rating|rating(s)? (assigned|reaffirmed|upgrade|downgrade|revised)|\b(crisil|icra|care ?edge|india ratings|fitch|moody)"),
    ("litigation", "legal", 60, r"litigation|dispute|penalty|show cause|order (passed|received) .*(tax|gst|authority)|demand notice|tax demand|\bsebi order|\bnclt\b|insolvency|fine imposed|search (and|&) seizure|regulatory action|warning letter|import alert|form 483|\busfda\b.*(observation|warning)"),
    ("bonus_split", "bonus_split", 55, r"\bbonus\b|sub-?division|stock split|split of"),
    ("dividend", "dividend", 30, r"dividend"),
    ("capex", "capex", 55, r"capex|capital expenditure|capacity expansion|new (plant|facility|unit)|greenfield|brownfield|commission(ing|ed) of"),
    ("investor_meetings", "meet", 8, r"analyst|investor (meet|conference|presentation)|institutional investor|non-deal roadshow|conference call|con\. call|earnings call"),
    ("postal_ballot", "ballot", 12, r"postal ballot|e-?voting"),
    ("agm_egm", "meeting", 12, r"\bagm\b|\begm\b|annual general meeting|extra-?ordinary general|shareholders meeting|book closure|record date"),
    ("press_release", "order", 40, r"order|contract|bagging|letter of award|\bloa\b|work order"),
    ("press_release", "press", 25, r"press release|launch|partnership|collaborat|clarification|media release|update"),
    ("unclassified", "routine", 5, r"esop|esos|employee stock|allotment of (equity )?shares under|amendment to (aoa|moa)|change in (registrar|address)|investor complaints|corporate governance|\besg\b|sustainability|brsr|record of|loss of"),
]
_COMPILED = [(c, s, b, re.compile(p, re.I)) for c, s, b, p in RULES]

CATEGORY_LABEL = {
    "results": "Results", "M&A": "M&A", "fund_raise": "Fund raise", "management_change": "Management",
    "litigation": "Litigation", "insider_trading": "Insider trade", "earnings_call": "Earnings call",
    "investor_meetings": "Investor meet", "credit_rating": "Credit rating", "dividend": "Dividend",
    "bonus_split": "Bonus / split", "capex": "Capex", "press_release": "Press release",
    "postal_ballot": "Postal ballot", "agm_egm": "AGM / EGM", "pledging": "Pledging", "unclassified": "Routine",
}

TOP_ROLE = re.compile(r"\b(managing director|\bmd\b|chief executive|\bceo\b|chief financial|\bcfo\b|chair(man|person)|whole[- ]time director|chief operating|\bcoo\b|executive director)", re.I)
LOW_ROLE = re.compile(r"independent director|company secretary|compliance officer|nominee director|senior management|\bsmp\b|statutory auditor|secretarial auditor|cost auditor|internal auditor|scrutini[sz]er", re.I)
AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|million|mn|billion|bn)?"
                    r"|([\d,]+(?:\.\d+)?)\s*(crores?|cr\b)", re.I)
USD = re.compile(r"(?:us\$|usd|\$)\s*([\d,]+(?:\.\d+)?)\s*(million|mn|billion|bn)", re.I)


def amount_cr(text):
    """Largest rupee amount mentioned, in ₹ crore (None if none). USD converted at ~₹88."""
    best = None
    for m in AMOUNT.finditer(text):
        val, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            v = float(val.replace(",", ""))
        except ValueError:
            continue
        unit = (unit or "").lower()
        if unit.startswith(("lakh", "lac")):
            v /= 100
        elif unit.startswith(("million", "mn")):
            v /= 10
        elif unit.startswith(("billion", "bn")):
            v *= 100
        elif not unit.startswith("cr"):
            if v < 1e5:  # a bare small rupee figure (e.g. a dividend per share) is not a deal size
                continue
            v /= 1e7
        best = max(best or 0, v)
    for m in USD.finditer(text):
        v = float(m.group(1).replace(",", "")) * 88 / 10  # USD mn -> ₹ cr
        if m.group(2).lower().startswith("b"):
            v *= 1000
        best = max(best or 0, v)
    return best


GENERIC = re.compile(r"^\s*(meeting updates?|general updates?|updates?|allotment|press release.*|media release|"
                     r"board meeting outcome.*|outcome of board meeting.*|disclosure under regulation 30.*|"
                     r"announcement under regulation 30.*|intimation|clarification|.*\(lodr\)[- ]*)\s*$", re.I)


BOILER = re.compile(r"^(?:announcement|disclosure|intimation)s?\s+under\s+(?:regulation|reg\.?)\s*\d+.*?(?:\(lodr\)|2015|regulations)\s*[-–:]+\s*", re.I)


def clean_title(t):
    t = BOILER.sub("", t or "").strip(" -–:")
    t = re.sub(r"\s+", " ", t)
    return t[:1].upper() + t[1:] if t else t


def classify(title, subject="", summary=""):
    title = clean_title(title) or title
    text = f"{subject} || {title}"
    if summary and GENERIC.match(title.strip()):
        # the title says nothing ("Meeting Updates"); the summary says it was a QIP
        text = f"{summary} || {title}"
        if re.search(r"board meeting outcome|outcome of (the )?board meeting", title, re.I) and \
                re.search(r"\b(results?|revenue|pat|profit|q[1-4])\b", summary, re.I):
            return "results", "results", 90
    for cat, sub, base, rx in _COMPILED:
        if rx.search(text):
            return cat, sub, base
    # fall back to the summary only when the title says nothing useful
    for cat, sub, base, rx in _COMPILED:
        if rx.search(summary or ""):
            return cat, sub, base
    return "unclassified", "other", 10


def score(filing, revenue_cr=None, mcap_cr=None):
    """Return dict(category, sub, score, reasons, amount_cr)."""
    title, subject, summary = filing.get("title", ""), filing.get("subject", ""), filing.get("summary", "")
    cat, sub, s = classify(title, subject, summary)
    text = f"{title} {summary}"
    reasons = []
    amt = amount_cr(text) if cat in {"press_release", "M&A", "capex", "litigation", "fund_raise"} else None

    if cat == "results" and sub == "results":
        if re.search(r"newspaper|advertisement|publication", text, re.I):
            cat, sub, s = "results", "results_ad", 8
        else:
            reasons.append("Quarterly numbers are out")
    elif cat == "results" and sub == "board_meeting_notice":
        reasons.append("Results date set")
    elif cat == "management_change":
        if TOP_ROLE.search(text) and not LOW_ROLE.search(title):
            s = 88
            reasons.append("Top-management change")
        elif LOW_ROLE.search(text):
            s = 22
        if re.search(r"resign|cessation|steps? down", text, re.I) and s >= 60:
            s += 4
            reasons.append("Departure")
    elif cat == "credit_rating":
        if re.search(r"upgrad", text, re.I):
            s, sub = 65, "upgrade"
            reasons.append("Rating upgraded")
        elif re.search(r"downgrad|negative|watch with negative", text, re.I):
            s, sub = 80, "downgrade"
            reasons.append("Rating downgraded")
        else:
            s = 15
    elif cat == "pledging" and re.search(r"release|revoc", text, re.I):
        s = 40
        reasons.append("Pledge released")
    elif cat == "insider_trading" and re.search(r"promoter", text, re.I):
        s = 50
        reasons.append("Promoter dealing")
    elif cat == "dividend" and re.search(r"special|interim", text, re.I):
        s = 38

    if amt and (revenue_cr or mcap_cr):
        # equity raises dilute holders, so size them against market cap; everything else against revenue
        use_mcap = (cat == "fund_raise" and sub in {"equity", "buyback"} and mcap_cr) or not revenue_cr
        base = mcap_cr if use_mcap else revenue_cr
        share = 100 * amt / base
        what = "market cap" if use_mcap else "annual revenue"
        amt_txt = f"₹{amt:,.0f} cr" if amt >= 1 else f"₹{amt * 100:,.0f} lakh"
        if share >= 0.5:
            reasons.append(f"{amt_txt} ≈ {share:.1f}% of {what}")
        if cat in {"press_release", "capex", "M&A"}:
            s = max(s, min(92, s + int(12 * min(share, 5))))  # 5% of revenue moves an order to "needs you"
        elif cat == "litigation":
            if share < 0.1:
                s = 30
                reasons.append(f"Immaterial size ({amt_txt})")
            else:
                s = max(s, min(90, 45 + int(10 * min(share, 4))))
    return {"category": cat, "sub": sub, "score": max(0, min(100, s)), "reasons": reasons, "amount_cr": amt}


def tier(s):
    return "needs_you" if s >= 65 else "worth_knowing" if s >= 25 else "routine"

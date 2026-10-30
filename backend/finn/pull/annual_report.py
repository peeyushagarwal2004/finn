"""Governance checks from the latest annual report: the parts of a 300-400 page document
an investor actually looks for. Everything here is quoted or located, never paraphrased,
and each finding carries the page it came from.

  - auditor's opinion: clean, qualified, adverse or disclaimer; emphasis of matter; going concern
  - who the auditor is, and how many key audit matters they raised
  - the board's statement on related-party transactions
  - the contingent liabilities note (quoted, since layouts vary too much to parse safely)
"""
import re

from .. import store
from ..sources import pdf, screener

REPORT_START = re.compile(r"independent\s+auditor'?s?['’]?\s*report|report\s+on\s+the\s+audit\s+of\s+the\s+(?:standalone|consolidated)\s+financial\s+statements", re.I)
OPINION_BAD = [("disclaimer", re.compile(r"disclaimer of opinion", re.I)),
               ("adverse", re.compile(r"adverse opinion", re.I)),
               ("qualified", re.compile(r"basis for qualified opinion|qualified opinion", re.I))]
EOM = re.compile(r"emphasis of matter", re.I)
GOING = re.compile(r"material uncertainty related to going concern", re.I)
AUDITOR = re.compile(r"For\s+([A-Z][A-Za-z&.,' ]{2,60}?(?:LLP|& Co\.?|& Associates|& Company|Associates))\s*\n?\s*Chartered Accountants", re.S)
RPT = re.compile(r"[^.]{0,200}(?:materially significant|material(?:ly)?)\s+related[- ]party transactions?[^.]{0,260}\.", re.I | re.S)
CONTINGENT = re.compile(r"contingent liabilit(?:y|ies)", re.I)


def _clean(s):
    return re.sub(r"\s+", " ", s).strip()


def scan(symbol):
    co = screener.company(symbol)
    ars = co["documents"].get("annual_reports") or []
    if not ars:
        return None
    ar = ars[0]
    key = f"{symbol}:{ar['url']}"
    cached = store.kv_get("governance", key)
    if cached is not None:
        return cached
    pages = pdf.pages(ar["url"], max_pages=600)
    out = {"year": ar["year"], "url": ar["url"], "pages": len(pages)}
    if not pages or sum(map(len, pages)) < 5000:
        out["error"] = "The annual report PDF has no extractable text (probably scanned)."
        store.kv_set("governance", key, out)
        return out

    # auditor's report: prefer the consolidated one, which covers the whole group
    starts = [i for i, p in enumerate(pages) if REPORT_START.search(p[:1500]) and "opinion" in p.lower()]
    cons = [i for i in starts if "consolidated" in pages[i][:2500].lower()]
    s = (cons or starts or [None])[0]
    aud = {"found": s is not None}
    if s is not None:
        block = "\n".join(pages[s:s + 12])
        aud["page"] = s + 1
        aud["basis"] = "consolidated" if cons else "standalone"
        aud["opinion"] = next((name for name, rx in OPINION_BAD if rx.search(block)), "unmodified")
        aud["emphasis_of_matter"] = bool(EOM.search(block))
        aud["going_concern"] = bool(GOING.search(block))
        aud["key_audit_matters"] = len(set(i for i in range(s, min(s + 12, len(pages))) if re.search(r"key audit matter", pages[i], re.I)))
        m = AUDITOR.search(block)
        aud["firm"] = _clean(m.group(1)) if m else None
    out["auditor"] = aud

    # the board's declaration mentions conflict of interest; prefer it over AGM-notice boilerplate
    rpt = None
    for want_conflict in (True, False):
        for i, p in enumerate(pages):
            for m in RPT.finditer(p):
                if not want_conflict or "conflict" in m.group(0).lower():
                    rpt = {"page": i + 1, "text": _clean(m.group(0))[:420]}
                    break
            if rpt:
                break
        if rpt:
            break
    out["related_party"] = rpt

    # skip the accounting-policy paragraph; the note itself has figures right after the heading
    cont, fallback = None, None
    for i, p in enumerate(pages):
        for m in CONTINGENT.finditer(p):
            ctx = p[m.start():m.start() + 700]
            if re.search(r"possible obligation|is made where|are not recogni[sz]ed|disclosed when|integral part|notes to (?:the )?accounts\s+\d", ctx[:400], re.I):
                continue
            if not re.search(r"\d{1,3}(?:,\d{2,3})+|\d{3,}", ctx[:500]):
                continue
            hit = {"page": i + 1, "text": _clean(ctx)}
            if re.search(r"not acknowledged as debts?|claims against", ctx, re.I):
                cont = hit
                break
            fallback = fallback or hit
        if cont:
            break
    cont = cont or fallback
    out["contingent"] = cont
    store.kv_set("governance", key, out)
    return out


def flags(g):
    """Turn the scan into the same flag shape the rest of the dossier uses."""
    if not g or g.get("error") or not g.get("auditor", {}).get("found"):
        return []
    a, F = g["auditor"], []
    src = f"Annual report {g['year']}, p.{a['page']}"
    if a["opinion"] != "unmodified":
        F.append({"id": "audit_opinion", "tone": "neg", "section": "governance",
                  "title": f"Auditor gave a {a['opinion']} opinion", "detail": f"{a.get('firm') or 'The auditor'} did not sign off cleanly. {src}."})
    if a["going_concern"]:
        F.append({"id": "going_concern", "tone": "neg", "section": "governance",
                  "title": "Going-concern doubt raised by the auditor", "detail": f"{src}."})
    if a["emphasis_of_matter"]:
        F.append({"id": "emphasis", "tone": "watch", "section": "governance",
                  "title": "Auditor added an emphasis of matter", "detail": f"Not a qualification, but the auditor wanted something read closely. {src}."})
    if a["opinion"] == "unmodified" and not a["emphasis_of_matter"] and not a["going_concern"]:
        F.append({"id": "audit_clean", "tone": "pos", "section": "governance",
                  "title": "Clean audit opinion", "detail": f"{a.get('firm') or 'The auditor'} signed off without qualification on the {a['basis']} accounts. {src}."})
    r = g.get("related_party")
    if r and re.search(r"(?:\bno\b|not have|do not|does not|did not|not entered)[^.]{0,90}(?:conflict|materially significant)", r["text"], re.I):
        F.append({"id": "rpt_none", "tone": "pos", "section": "governance",
                  "title": "Board reports no related-party deals that conflict with shareholders", "detail": f"Annual report {g['year']}, p.{r['page']}."})
    elif r and re.search(r"\bno\s+material", r["text"], re.I):
        F.append({"id": "rpt_none", "tone": "pos", "section": "governance",
                  "title": "Board reports no material related-party transactions", "detail": f"Annual report {g['year']}, p.{r['page']}."})
    elif r:
        F.append({"id": "rpt_some", "tone": "watch", "section": "governance",
                  "title": "Related-party transactions disclosed", "detail": f"Worth reading the note. Annual report {g['year']}, p.{r['page']}."})
    return F

"""Ask a question of a company's own transcripts.

BM25 retrieval over speaker-turn chunks picks ~6 passages (a few thousand tokens) out of
four calls (~200k characters), so the model sees a fraction of the text. Without a model,
the answer is the passages themselves, with the sentences that match highlighted.
"""
import math
import re
import time
from collections import Counter

from .. import llm
from ..sources import pdf
from .guidance import extract, turns

STOP = set("the a an and or of to in on for is are was were be been it this that with as at by from we our you your "
           "they their has have had will would can could should what how why when which who do does did about there "
           "than then so if not no any all its into over also more most such".split())


def _tok(s):
    return [w for w in re.findall(r"[a-z0-9%]+", s.lower()) if w not in STOP and len(w) > 1]


def _chunks(symbol):
    out = []
    for t in extract(symbol):
        pages = pdf.pages(t["url"], max_pages=45)
        for sp, txt, page in turns(pages):
            if len(txt) < 120 or "moderator" in sp.lower():
                continue
            for i in range(0, len(txt), 900):
                out.append({"label": t["label"], "speaker": sp, "page": page, "url": t["url"], "text": txt[i:i + 1100]})
    # the latest annual report, if the research job has already read it (it's cached by then)
    from ..sources import screener
    ars = screener.company(symbol)["documents"].get("annual_reports") or []
    if ars:
        from .. import store
        pages = store.kv_get("pdftext", f"{ars[0]['url']}#600") or []
        for n, txt in enumerate(pages):
            txt = " ".join(txt.split())
            for i in range(0, len(txt), 1000):
                if len(txt) > 200:
                    out.append({"label": f"Annual report {ars[0]['year']}", "speaker": "Annual report", "page": n + 1,
                                "url": ars[0]["url"], "text": txt[i:i + 1100]})
    return out


_INDEX: dict = {}


def _index(symbol):
    """Tokenise a company's calls and annual report once, then reuse for every question."""
    ix = _INDEX.get(symbol)
    if ix is None or time.time() - ix["ts"] > 6 * 3600:
        chunks = _chunks(symbol)
        docs = [Counter(_tok(c["text"])) for c in chunks]
        lens = [sum(d.values()) for d in docs]
        ix = {"ts": time.time(), "chunks": chunks, "docs": docs, "lens": lens,
              "avg": (sum(lens) / len(lens)) if lens else 1, "df": Counter(w for d in docs for w in d)}
        _INDEX[symbol] = ix
    return ix


def search(ix, q, k=6):
    N = len(ix["chunks"])
    if not N:
        return []
    df, avg = ix["df"], ix["avg"]
    scored = []
    for c, tf, ln in zip(ix["chunks"], ix["docs"], ix["lens"]):
        s = sum(math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * ln / avg))
                for w in set(_tok(q)) if w in tf)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    # the calls are where management talks; the annual report is mostly tables. Let the report lead
    # only for questions that are about its kind of content.
    ar_q = re.search(r"auditor|audit|contingent|related.party|segment|subsidiar|tax|litigation|liabilit|remuneration|pledge|provision", q, re.I)
    calls = [c for _, c in scored if c["speaker"] != "Annual report"]
    report = [c for _, c in scored if c["speaker"] == "Annual report"]
    if ar_q:
        return (report[:4] + calls[:2])[:k]
    return (calls[:k - 2] + report[:2])[:k] if calls else report[:k]


PROMPT = """Answer the investor's question about {name} using ONLY these excerpts from the company's own earnings
calls and annual report. Cite every claim with the excerpt number like [2]. If the excerpts don't answer it, say so plainly.
Keep it under 120 words; lead with the direct answer. Return JSON {{"answer": "...", "used": [numbers]}}.

QUESTION: {q}

{ctx}"""


def answer(symbol, name, q):
    hits = search(_index(symbol), q)
    sources = [{"n": i + 1, "label": h["label"], "speaker": h["speaker"], "page": h["page"], "url": h["url"],
                "text": h["text"]} for i, h in enumerate(hits)]
    if not hits:
        return {"answer": "Nothing in the last four earnings calls or the annual report addresses that.", "sources": [], "mode": "none"}
    ctx = "\n\n".join(f"[{s['n']}] {s['label']} — {s['speaker']} (p.{s['page']}): {s['text']}" for s in sources)
    js = llm.ask_json(PROMPT.format(name=name, q=q, ctx=ctx), tier="cheap", max_tokens=500,
                     attempts=2, timeout=25)  # someone is waiting: short budget, then quote instead
    if isinstance(js, dict) and js.get("answer"):
        return {"answer": js["answer"], "sources": sources, "mode": "model"}
    # extractive fallback: the best sentences from the top passages, verbatim
    qt = set(_tok(q))
    ranked = []
    for s in sources:
        for sent in re.split(r"(?<=[.!?])\s+", s["text"]):
            sent = sent.strip()
            hit = len(qt & set(_tok(sent)))
            digits = sum(ch.isdigit() for ch in sent) / max(len(sent), 1)
            if sent.endswith("?") or digits > 0.15:  # an analyst's question or a table row isn't an answer
                continue
            if 60 <= len(sent) <= 400 and hit >= 1:
                ranked.append((hit + 0.1 * bool(re.search(r"\d", sent)) - 0.02 * s["n"], sent, s["n"]))
    ranked.sort(key=lambda x: -x[0])
    if ranked and ranked[0][0] >= 2:
        ranked = [r for r in ranked if r[0] >= 1.5]  # if some sentences match well, drop the weak ones
    picks = [f"“{t}” [{n}]" for _, t, n in ranked[:3]]
    if not picks:
        return {"answer": "The calls touch on this only in passing — see the passages below.", "sources": sources, "mode": "extractive"}
    return {"answer": " ".join(picks), "sources": sources, "mode": "extractive"}

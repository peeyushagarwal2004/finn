"""Ask a question of a company's own transcripts.

BM25 retrieval over speaker-turn chunks picks ~6 passages (a few thousand tokens) out of
four calls (~200k characters), so the model sees a fraction of the text. Without a model,
the answer is the passages themselves, with the sentences that match highlighted.
"""
import math
import re
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
    return out


def search(chunks, q, k=6):
    docs = [_tok(c["text"]) for c in chunks]
    if not docs:
        return []
    N, avg = len(docs), sum(map(len, docs)) / len(docs)
    df = Counter(w for d in docs for w in set(d))
    qt = _tok(q)
    scored = []
    for c, d in zip(chunks, docs):
        tf = Counter(d)
        s = sum(math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / avg))
                for w in qt if w in tf)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


PROMPT = """Answer the investor's question about {name} using ONLY these excerpts from the company's own earnings
calls. Cite every claim with the excerpt number like [2]. If the excerpts don't answer it, say so plainly.
Keep it under 120 words; lead with the direct answer. Return JSON {{"answer": "...", "used": [numbers]}}.

QUESTION: {q}

{ctx}"""


def answer(symbol, name, q):
    hits = search(_chunks(symbol), q)
    sources = [{"n": i + 1, "label": h["label"], "speaker": h["speaker"], "page": h["page"], "url": h["url"],
                "text": h["text"]} for i, h in enumerate(hits)]
    if not hits:
        return {"answer": "Nothing in the last four earnings calls addresses that.", "sources": [], "mode": "none"}
    ctx = "\n\n".join(f"[{s['n']}] {s['label']} — {s['speaker']} (p.{s['page']}): {s['text']}" for s in sources)
    js = llm.ask_json(PROMPT.format(name=name, q=q, ctx=ctx), tier="cheap", max_tokens=500)
    if isinstance(js, dict) and js.get("answer"):
        return {"answer": js["answer"], "sources": sources, "mode": "model"}
    # extractive fallback: the best sentences from the top passages, verbatim
    qt = set(_tok(q))
    ranked = []
    for s in sources:
        for sent in re.split(r"(?<=[.!?])\s+", s["text"]):
            sent = sent.strip()
            hit = len(qt & set(_tok(sent)))
            if len(sent) >= 60 and hit >= min(2, len(qt)):
                ranked.append((hit + 0.1 * bool(re.search(r"\d", sent)) - 0.02 * s["n"], sent, s["n"]))
    ranked.sort(key=lambda x: -x[0])
    picks = [f"“{t}” [{n}]" for _, t, n in ranked[:3]]
    if not picks:
        return {"answer": "The calls touch on this only in passing — see the passages below.", "sources": sources, "mode": "extractive"}
    return {"answer": " ".join(picks), "sources": sources, "mode": "extractive"}

"""Research job: progressive and cached, so the screen fills in as each stage lands.

  1. numbers   - statements, ratios, flags            (~1 s, no model)
  2. promises  - last 4 transcripts -> ledger         (~20 s first time, cached after)
  3. synthesis - narrative vs numbers, bull / bear    (one strong-model call, or rules)
"""
import json
import threading
import time

from .. import llm, store
from . import fundamentals, guidance, ledger

_jobs: dict[str, threading.Thread] = {}
_lock = threading.Lock()
VERSION = 3  # bump to invalidate cached dossiers when the analysis changes


def get(symbol):
    return store.kv_get("research", symbol.upper())


def _save(symbol, doc):
    doc["updated"] = time.time()
    store.kv_set("research", symbol, doc)


def start(symbol, force=False):
    symbol = symbol.upper().strip()
    doc = get(symbol)
    fresh = doc and doc.get("version") == VERSION and doc.get("status") == "done" and time.time() - doc.get("updated", 0) < 12 * 3600
    if fresh and not force:
        return doc
    with _lock:
        if symbol in _jobs and _jobs[symbol].is_alive():
            return get(symbol)
        t = threading.Thread(target=_run, args=(symbol,), daemon=True)
        _jobs[symbol] = t
        _save(symbol, {"symbol": symbol, "version": VERSION, "status": "running", "stage": "numbers",
                       "stages": {"numbers": "running", "promises": "waiting", "synthesis": "waiting"}})
        t.start()
    return get(symbol)


def _run(symbol):
    doc = get(symbol)
    try:
        a = fundamentals.analyse(symbol)
        doc.update(a)
        doc["stages"]["numbers"] = "done"
        doc["stages"]["promises"] = "running"
        doc["stage"] = "promises"
        _save(symbol, doc)

        ts = guidance.extract(symbol)
        doc["transcripts"] = [{k: t.get(k) for k in ("label", "call", "url", "pages", "candidates", "method", "tone", "speakers")} for t in ts]
        doc["ledger"] = ledger.build(symbol, ts)
        doc["stages"]["promises"] = "done"
        doc["stages"]["synthesis"] = "running"
        doc["stage"] = "synthesis"
        _save(symbol, doc)

        doc["synthesis"] = synthesise(doc)
        doc["stages"]["synthesis"] = "done"
        doc["status"] = "done"
        doc["stage"] = None
        doc["llm"] = llm.status()
    except Exception as e:  # surface the failure in the UI rather than spinning forever
        doc["status"] = "error"
        doc["error"] = f"{type(e).__name__}: {e}"
    _save(symbol, doc)


SYNTH = """You are analysing {name} for a professional investor. Use ONLY the facts below (computed from the
company's filed statements and its own earnings-call transcripts). No outside knowledge.
Write:
- "narrative": 3-4 points on where management's story and the numbers agree or diverge. Each
  {{"stance": "agree"|"diverge", "text": "<= 30 words, specific numbers", "evidence": [fact ids]}}
- "bull": 3 points, "bear": 3 points, each {{"text": "<= 22 words", "evidence": [fact ids]}}
- "verdict": one sentence, <= 25 words, the single thing to watch next quarter.
Return JSON with keys narrative, bull, bear, verdict.

FACTS:
{facts}"""


def _facts(doc):
    facts = []
    for f in doc.get("flags", []):
        facts.append({"id": f["id"], "fact": f"{f['title']}. {f['detail']}"})
    for i, r in enumerate((doc.get("ledger") or {}).get("rows", [])):
        if r["verdict"] in ("unverifiable",):
            continue
        tgt = r.get("summary") or r["quote"][:160]
        res = f" Result: {r.get('actual')}% over {r.get('reported')}/{r.get('of')} quarters ({r['verdict_label']})." if r.get("actual") is not None else f" ({r['verdict_label']})"
        facts.append({"id": f"P{i}", "fact": f"{r['said_in']} call, {r['metric_label']} for {r['period']}: \"{tgt}\".{res}"})
    for t in (doc.get("ledger") or {}).get("timeline", []):
        facts.append({"id": f"T-{t['label']}", "fact": f"{t['label']}: revenue YoY {t['sales_yoy']}%, operating margin {t['opm']}%, PAT YoY {t['pat_yoy']}%, management tone {t['tone']}"})
    c = doc.get("trajectory", {}).get("cagr", {})
    facts.append({"id": "CAGR", "fact": f"Revenue CAGR 3y {c.get('sales_3y')}%, 5y {c.get('sales_5y')}%; PAT CAGR 3y {c.get('pat_3y')}%"})
    return facts


def synthesise(doc):
    facts = _facts(doc)
    ids = {f["id"] for f in facts}
    js = llm.ask_json(SYNTH.format(name=doc["snapshot"]["name"], facts=json.dumps(facts, ensure_ascii=False)),
                      tier="strong", max_tokens=1200)
    if isinstance(js, dict) and js.get("bull") and js.get("bear"):
        for k in ("narrative", "bull", "bear"):  # keep only points that cite real facts
            js[k] = [p for p in js.get(k) or [] if isinstance(p, dict) and set(p.get("evidence") or []) & ids]
        js["mode"] = "model"
        if not js.get("narrative"):
            js["narrative"] = doc["ledger"]["narrative"]
        return js
    # rules fallback: the flags already carry tone; the ledger already says said-vs-did
    pos = [f for f in doc.get("flags", []) if f["tone"] == "pos"]
    neg = [f for f in doc.get("flags", []) if f["tone"] in ("neg", "watch")]
    L = doc.get("ledger") or {}
    kept = [r for r in L.get("rows", []) if r["verdict"] in ("delivered", "beat", "on_track", "ahead")]
    missed = [r for r in L.get("rows", []) if r["verdict"] in ("missed", "behind", "near_miss", "slightly_behind")]
    bull = [{"text": f"{f['title']}: {f['detail']}", "evidence": [f["id"]]} for f in pos[:3]]
    bear = [{"text": f"{f['title']}: {f['detail']}", "evidence": [f["id"]]} for f in neg[:3]]
    if kept and len(bull) < 3:
        r = kept[0]
        bull.append({"text": f"Kept its word on {r['metric_label'].lower()} ({r['period']}): {r['actual']}% vs guidance.", "evidence": ["ledger"]})
    if missed and len(bear) < 3:
        r = missed[0]
        bear.append({"text": f"Fell short on {r['metric_label'].lower()} ({r['period']}): {r['actual']}% vs guidance.", "evidence": ["ledger"]})
    watch = missed[0] if missed else (neg[0] if neg else None)
    verdict = (f"Watch {watch['metric_label'].lower()} against the {watch['period']} guide." if watch and "metric_label" in watch
               else f"Watch: {watch['title'].lower()}." if watch else "Nothing flagged; watch whether growth holds its trend.")
    return {"narrative": L.get("narrative", []), "bull": bull, "bear": bear, "verdict": verdict, "mode": "rules"}

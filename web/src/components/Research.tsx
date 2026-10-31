import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { BarLine, Delta, fmt, Icon, Section } from "./ui";

/* ---------- voice input (browser speech recognition; free, on-device where supported) ---------- */
const SR: any = typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;
function useVoice(onText: (t: string) => void) {
  const [live, setLive] = useState(false);
  const rec = useRef<any>(null);
  const start = () => {
    if (!SR) return alert("Voice input isn't supported in this browser. Try Chrome or Safari.");
    const r = new SR();
    r.lang = "en-IN";
    r.interimResults = false;
    r.onresult = (e: any) => onText(e.results[0][0].transcript);
    r.onend = () => setLive(false);
    r.onerror = () => setLive(false);
    rec.current = r;
    setLive(true);
    r.start();
  };
  return { live, start, stop: () => rec.current?.stop(), supported: !!SR };
}

const VERDICT_TONE: Record<string, string> = {
  delivered: "up", beat: "up", on_track: "up", ahead: "up", near_miss: "accent", slightly_behind: "accent",
  behind: "down", missed: "down", pending: "", unverifiable: "", long_term: "",
};

function Gauge({ r }: { r: any }) {
  if (r.actual == null || r.low == null) return null;
  const hi = r.high ?? Math.max(r.low * 1.4, r.low + 4);
  let lo = Math.min(r.low, r.actual), up = Math.max(hi, r.actual);
  const pad = (up - lo) * 0.25 || 2;
  lo -= pad; up += pad;
  const X = (v: number) => `${((v - lo) / (up - lo)) * 100}%`;
  const col = `var(--${VERDICT_TONE[r.verdict] === "up" ? "up" : VERDICT_TONE[r.verdict] === "down" ? "down" : "accent"})`;
  return (
    <div className="gauge">
      <div className="gauge-track">
        <div className="gauge-band" style={{ left: X(r.low), width: `max(4px, calc(${X(hi)} - ${X(r.low)}))`, opacity: r.high == null ? 0.55 : 1 }} />
        <div className="gauge-dot" style={{ left: X(r.actual), background: col }} />
      </div>
      <div className="gauge-l num">
        <span>Guided {r.low === 0 && r.high == null ? "> 0%" : r.high == null ? `${r.low}%+` : r.low === r.high ? `${r.low}%` : `${r.low}–${r.high}%`}</span>
        <span style={{ color: col }}>Actual {r.actual}% · {r.reported}/{r.of} qtrs</span>
      </div>
    </div>
  );
}

function Promises({ L }: { L: any }) {
  const [all, setAll] = useState(false);
  const rows = L.rows.filter((r: any) => all || r.verdict !== "unverifiable");
  const hidden = L.rows.length - rows.length;
  const s = L.score;
  return (
    <>
      <div className="scoreline">
        <span className="big">{s.scored ? `${s.kept}/${s.scored}` : "–"}</span>
        <span className="muted" style={{ fontSize: 13.5 }}>
          {s.scored ? <>guidance targets met{s.near ? `, ${s.near} close` : ""}, {s.missed} missed, across the last {L.timeline.length} calls</> : "Management gave direction on the calls but few numbers that can be checked against results."}
        </span>
      </div>
      {rows.length > 0 && (
        <div>
          {rows.map((r: any, i: number) => (
            <div className="promise" key={i}>
              <div className="ptop">
                <span>{r.metric_label}{r.period ? `, ${r.period}` : ""}</span>
                <span className={`vd ${VERDICT_TONE[r.verdict] === "up" ? "good" : VERDICT_TONE[r.verdict] === "down" ? "bad" : VERDICT_TONE[r.verdict] === "accent" ? "mid" : "none"}`}>{r.verdict_label}</span>
              </div>
              {r.summary && <div style={{ fontWeight: 500, fontSize: 14, marginTop: 4 }}>{r.summary}</div>}
              <div className="quote">{r.quote.length > 260 ? r.quote.slice(0, 257) + "…" : r.quote}</div>
              <Gauge r={r} />
              <div className="pmeta">
                <span>{r.speaker}</span>
                <a href={`${r.url}#page=${r.page}`} target="_blank" rel="noreferrer">{r.said_in} call, p.{r.page}</a>
                {r.actual_basis && <span>checked against {r.actual_basis}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      {hidden > 0 && <button className="act primary" onClick={() => setAll(true)} style={{ marginTop: 10, whiteSpace: "normal", textAlign: "left" }}>Show {hidden} more that can't be checked against the financials</button>}
    </>
  );
}

function SayDo({ L }: { L: any }) {
  const tl = L.timeline;
  if (!tl.length) return null;
  return (
    <div>
      <div className="tl num">
        <div className="h">Call</div><div className="h">Tone</div><div className="h" style={{ textAlign: "right" }}>Rev YoY</div><div className="h" style={{ textAlign: "right" }}>PAT YoY</div>
        {tl.map((t: any) => (
          <FragmentRow key={t.label} t={t} />
        ))}
      </div>
      <div className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>Tone counts upbeat against cautious words in management's remarks, from −1 to +1. Growth figures are that quarter's reported results.</div>
    </div>
  );
}
function FragmentRow({ t }: { t: any }) {
  const w = t.tone == null ? 0 : Math.abs(t.tone) * 44;
  return (
    <>
      <div><a href={t.url} target="_blank" rel="noreferrer">{t.label}</a></div>
      <div className="tonebar">
        <i style={{ width: w, background: t.tone >= 0 ? "var(--up)" : "var(--down)" }} />
        <span className="muted">{t.tone == null ? "—" : (t.tone > 0 ? "+" : "") + t.tone.toFixed(2)}</span>
      </div>
      <div style={{ textAlign: "right" }}><Delta v={t.sales_yoy} /></div>
      <div style={{ textAlign: "right" }}><Delta v={t.pat_yoy} /></div>
    </>
  );
}

function Narrative({ items }: { items: any[] }) {
  if (!items?.length) return <div className="muted" style={{ fontSize: 13, paddingTop: 8 }}>Not enough checkable guidance to compare what was said with what was reported.</div>;
  return (
    <div>
      {items.map((n, i) => (
        <div className="narr" key={i}>
          <span className={`dot ${n.stance === "agree" ? "up" : "down"}`}>{n.stance === "agree" ? "+" : "−"}</span>
          <div>
            <div>{n.text}</div>
            {n.evidence && <div className="ev">{Array.isArray(n.evidence) ? n.evidence.join(" · ") : n.evidence}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

function Flags({ flags, section }: { flags: any[]; section?: string }) {
  const f = section ? flags.filter((x) => x.section === section) : flags;
  if (!f.length) return null;
  return (
    <div style={{ marginTop: 10 }}>
      {f.map((x) => (
        <div className="flag" key={x.id}>
          <span className={`mk ${x.tone === "pos" ? "up" : x.tone === "neg" ? "down" : "accent"}`}>{x.tone === "pos" ? "+" : x.tone === "neg" ? "−" : "?"}</span>
          <div><b>{x.title}</b><p>{x.detail}</p></div>
        </div>
      ))}
    </div>
  );
}

function Ask({ symbol, name }: { symbol: string; name: string }) {
  const [q, setQ] = useState("");
  const [a, setA] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const voice = useVoice((t) => { setQ(t); go(t); });
  const go = (text = q) => {
    if (!text.trim()) return;
    setBusy(true);
    api.ask(symbol, text).then(setA).catch((e) => setA({ answer: String(e.message), sources: [] })).finally(() => setBusy(false));
  };
  const ideas = ["What is the margin outlook?", "What are the biggest risks management sees?", "What did they say about demand?"];
  return (
    <div>
      <div className="ask-box">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} placeholder="What did they say about margins?" />
        {voice.supported && <button className={`btn ghost ${voice.live ? "down" : ""}`} onClick={voice.live ? voice.stop : voice.start} aria-label="Ask by voice"><Icon.mic /></button>}
        <button className="btn" onClick={() => go()} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
      {!a && (
        <div className="suggestions">{ideas.map((i) => <button key={i} onClick={() => { setQ(i); go(i); }}>{i}</button>)}</div>
      )}
      {a && (
        <>
          <div className="answer" dangerouslySetInnerHTML={{ __html: a.answer.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\[(\d+)\]/g, "<sup>[$1]</sup>") }} />
          {a.mode === "extractive" && <div className="faint" style={{ fontSize: 11.5, marginTop: 6 }}>Quoted directly from the transcripts, since no language model is configured.</div>}
          <details style={{ marginTop: 10 }}>
            <summary className="muted" style={{ fontSize: 12.5 }}>{a.sources.length} source passages</summary>
            {a.sources.map((s: any) => (
              <div className="src" key={s.n}>
                <b>[{s.n}] {s.label} · {s.speaker}</b> · <a href={`${s.url}#page=${s.page}`} target="_blank" rel="noreferrer">p.{s.page}</a>
                <div style={{ marginTop: 4 }}>{s.text.slice(0, 420)}…</div>
              </div>
            ))}
          </details>
        </>
      )}
    </div>
  );
}

const NAV = [["verdict", "Summary"], ["promises", "Guidance"], ["saydo", "By quarter"], ["numbers", "Business"], ["trajectory", "Growth"], ["balance", "Balance sheet"], ["cash", "Cash"], ["capital", "Capital allocation"], ["governance", "Annual report"], ["bullbear", "Bull and bear"], ["ask", "Ask"]];

function Dossier({ d }: { d: any }) {
  const s = d.snapshot;
  const L = d.ledger;
  const syn = d.synthesis;
  const tr = d.trajectory, bal = d.balance, cash = d.cash;
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const keyPoints = (s?.key_points || "").split("\n").filter((x: string) => x.trim() && !/^\[\d+\]$/.test(x.trim()));
  return (
    <>
      {s && (
        <div className="dossier-h">
          <div className="nm">{s.name}</div>
          <div className="meta">{d.symbol} · {s.sector?.slice(-2).join(" · ")} · {s.basis}</div>
          <div className="kpis num">
            <div className="kpi"><span>Price</span><b>₹{fmt.n(s.price)}</b></div>
            <div className="kpi"><span>Mkt cap</span><b>{fmt.cr(s.mcap)}</b></div>
            <div className="kpi"><span>P/E</span><b>{fmt.n(s.pe, 1)}</b></div>
            <div className="kpi"><span>TTM revenue</span><b>{fmt.cr(s.ttm_sales)}</b></div>
            <div className="kpi"><span>TTM PAT</span><b>{fmt.cr(s.ttm_pat)}</b></div>
            <div className="kpi"><span>{s.lender ? "ROE" : "ROCE"}</span><b>{fmt.n(s.lender ? s.roe : s.roce, 1)}%</b></div>
          </div>
        </div>
      )}
      <div className="stages">
        {(["numbers", "promises", "annual_report", "synthesis"] as const).map((k) => (
          <div key={k} className={`stage ${d.stages?.[k] || "done"}`}><i />{k === "numbers" ? "Statements" : k === "promises" ? `Calls${d.transcripts ? ` (${d.transcripts.length})` : ""}` : k === "annual_report" ? "Annual report" : "Summary"}</div>
        ))}
      </div>
      {d.status === "error" && <div className="err" style={{ marginTop: 12 }}>Research hit a snag: {d.error}</div>}

      <div className="secnav"><div className="chips">{NAV.map(([id, l]) => <button key={id} className="chip sm" onClick={() => go(id)}>{l}</button>)}</div></div>

      <Section title="What to watch" id="verdict">
        {syn ? (
          <div className="verdict">
            <div className="q">{syn.verdict}</div>
            <Flags flags={d.flags.slice(0, 3)} />
          </div>
        ) : <div className="skeleton" style={{ height: 120 }} />}
      </Section>

      <Section title="Guidance against results" id="promises" aside="last four calls">
        {L ? <Promises L={L} /> : <div className="skeleton" style={{ height: 160 }} />}
      </Section>

      <Section title="Calls and results by quarter" id="saydo">
        {L ? <SayDo L={L} /> : <div className="skeleton" style={{ height: 120 }} />}
        <div style={{ marginTop: 10 }}>{syn ? <Narrative items={syn.narrative} /> : L ? <Narrative items={L.narrative} /> : null}</div>
      </Section>

      {s && (
        <Section title="Business" id="numbers">
          <div>
            <div className="about">{s.about.replace(/\s*\[\d+\]/g, "")}</div>
            {keyPoints.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 13, color: "var(--text-2)" }}>
                {keyPoints.slice(0, 10).map((k: string, i: number) => <div key={i} style={{ padding: "2px 0" }}>{k.replace(/^-\s*/, "· ").replace(/\s*\[\d+\]/g, "")}</div>)}
              </div>
            )}
            <div className="faint" style={{ fontSize: 11.5, marginTop: 10 }}>As described by the company in its filings and investor material.</div>
          </div>
        </Section>
      )}

      {tr && (
        <Section title="Growth" id="trajectory" aside={`revenue CAGR 3y ${fmt.pct(tr.cagr.sales_3y, 0, false)} · 5y ${fmt.pct(tr.cagr.sales_5y, 0, false)}`}>
          <div className="panel">
            <BarLine labels={tr.years} bars={tr.sales} line={s?.lender ? undefined : tr.opm} fmtBar={(v) => fmt.cr(v).replace(" cr", "")} fmtLine={(v) => `${v}%`} />
            <div className="legend"><span><i style={{ background: "var(--line-2)" }} />Revenue (₹ cr)</span>{!s?.lender && <span><i style={{ background: "var(--accent)" }} />Operating margin</span>}</div>
            <div style={{ marginTop: 14 }} className="muted">Last 8 quarters · revenue YoY</div>
            <BarLine labels={tr.quarters.labels} bars={tr.quarters.sales_yoy} h={110} barColor="var(--info)" fmtBar={(v) => `${v.toFixed(0)}%`} />
            <div className="kv num" style={{ marginTop: 6 }}><span className="muted">PAT CAGR 3y / 5y</span><b>{fmt.pct(tr.cagr.pat_3y, 0, false)} / {fmt.pct(tr.cagr.pat_5y, 0, false)}</b></div>
            <div className="kv num"><span className="muted">EPS CAGR 3y</span><b>{fmt.pct(tr.cagr.eps_3y, 0, false)}</b></div>
            <Flags flags={d.flags} section="trajectory" />
          </div>
        </Section>
      )}

      {bal && !s?.lender && (
        <Section title="Balance sheet" id="balance">
          <div className="panel">
            <BarLine labels={bal.years} bars={bal.borrowings} line={bal.de} h={120} barColor="var(--down)" fmtBar={(v) => fmt.cr(v).replace(" cr", "")} fmtLine={(v) => `${v}× D/E`} />
            <div className="legend"><span><i style={{ background: "var(--down)" }} />Borrowings</span><span><i style={{ background: "var(--accent)" }} />Debt / equity</span></div>
            <div className="tl num" style={{ gridTemplateColumns: "1fr repeat(3, 64px)", marginTop: 12 }}>
              <div className="h">Days</div>
              {bal.wc_years.slice(-3).map((y: string) => <div key={y} className="h" style={{ textAlign: "right" }}>{y.replace("Mar ", "FY")}</div>)}
              {[["Debtor", bal.debtor_days], ["Inventory", bal.inventory_days], ["Payable", bal.payable_days], ["Cash cycle", bal.ccc]]
                .filter(([, v]: any) => v.slice(-3).some((x: any) => x != null))
                .map(([l, v]: any) => <Row3 key={l} label={l} vals={v.slice(-3)} />)}
            </div>
            <Flags flags={d.flags} section="balance" />
          </div>
        </Section>
      )}

      {cash && !s?.lender && (
        <Section title="Cash quality" id="cash" aside={cash.cfo_pat_5y != null ? `5y CFO/PAT ${cash.cfo_pat_5y}×` : ""}>
          <div className="panel">
            <BarLine labels={cash.years} bars={cash.cfo} line={cash.pat} h={130} barColor="var(--up)" lineColor="var(--text-2)" fmtBar={(v) => fmt.cr(v).replace(" cr", "")} />
            <div className="legend"><span><i style={{ background: "var(--up)" }} />Operating cash flow</span><span><i style={{ background: "var(--text-2)" }} />Reported profit</span></div>
            {cash.fcf?.some((x: any) => x != null) && <div className="kv num" style={{ marginTop: 8 }}><span className="muted">Free cash flow, last 3 yrs</span><b>{cash.fcf.slice(-3).map((v: number) => fmt.cr(v)).join(" · ")}</b></div>}
            <Flags flags={d.flags} section="cash" />
          </div>
        </Section>
      )}

      {d.capital && (
        <Section title="Capital allocation" id="capital" aside={d.capital.years}>
          <div className="panel">
            {d.capital.uses?.length ? (
              <>
                <p className="lede" style={{ marginTop: 10 }}>Of {fmt.cr(d.capital.generated)} of operating cash generated, this is where it went.</p>
                <div className="alloc">
                  {d.capital.uses.map((u: any) => (
                    <div className="alloc-row" key={u.label}>
                      <span>{u.label === "Net debt repaid" && u.amount < 0 ? "Net new borrowing (added)" : u.label}</span>
                      <span className="alloc-bar"><i style={{ width: `${Math.min(100, Math.abs(u.pct))}%`, background: u.amount < 0 ? "var(--flag)" : undefined }} /></span>
                      <span className="num" style={{ textAlign: "right" }}>{Math.abs(u.pct)}%</span>
                    </div>
                  ))}
                </div>
                <div className="faint" style={{ fontSize: 11.5, marginTop: 6 }}>Shares of five years' operating cash flow, from the filed cash-flow statements. The remainder went to cash, investments and other items.</div>
              </>
            ) : <p className="lede" style={{ marginTop: 10 }}>{d.capital.note}</p>}
            <Flags flags={d.flags} section="capital" />
          </div>
        </Section>
      )}

      {(d.governance || d.stages?.annual_report === "running") && (
        <Section title="From the annual report" id="governance" aside={d.governance?.year ? `${d.governance.year}, ${d.governance.pages} pages read` : "reading…"}>
          {!d.governance ? <div className="skeleton" style={{ height: 100 }} /> : d.governance.error ? <p className="lede" style={{ marginTop: 10 }}>{d.governance.error}</p> : (
            <div>
              {d.governance.auditor?.found && (
                <div className="kv" style={{ marginTop: 8 }}>
                  <span className="muted">Auditor</span>
                  <span>{d.governance.auditor.firm || "Named in the report"}, {d.governance.auditor.key_audit_matters} key audit matters · <a className="link" href={`${d.governance.url}#page=${d.governance.auditor.page}`} target="_blank" rel="noreferrer">p.{d.governance.auditor.page}</a></span>
                </div>
              )}
              <Flags flags={d.flags} section="governance" />
              {d.governance.related_party && (
                <div style={{ paddingTop: 10 }}>
                  <div className="muted" style={{ fontSize: 12 }}>Related-party transactions, as stated in the report (<a className="link" href={`${d.governance.url}#page=${d.governance.related_party.page}`} target="_blank" rel="noreferrer">p.{d.governance.related_party.page}</a>)</div>
                  <div className="excerpt">{d.governance.related_party.text}</div>
                </div>
              )}
              {d.governance.contingent && (
                <div style={{ paddingTop: 10 }}>
                  <div className="muted" style={{ fontSize: 12 }}>Contingent liabilities note (<a className="link" href={`${d.governance.url}#page=${d.governance.contingent.page}`} target="_blank" rel="noreferrer">p.{d.governance.contingent.page}</a>)</div>
                  <div className="excerpt">{d.governance.contingent.text.slice(0, 420)}…</div>
                </div>
              )}
            </div>
          )}
        </Section>
      )}

      <Section title="Bull and bear case" id="bullbear" aside={syn?.mode === "rules" ? "from the flags above" : syn ? "written from the figures above" : ""}>
        {syn ? (
          <div className="bb">
            <div><h4 className="up">Bull</h4><ul>{syn.bull.map((b: any, i: number) => <li key={i}>{b.text}</li>)}</ul></div>
            <div><h4 className="down">Bear</h4><ul>{syn.bear.length ? syn.bear.map((b: any, i: number) => <li key={i}>{b.text}</li>) : <li className="muted">Nothing negative in the statements or the calls.</li>}</ul></div>
          </div>
        ) : <div className="skeleton" style={{ height: 140 }} />}
      </Section>

      <Section title="Ask about the calls" id="ask">
        <Ask symbol={d.symbol} name={s?.name || d.symbol} />
      </Section>

      <div className="foot">
        Sources: filed statements and {d.transcripts?.length || 0} earnings-call transcripts
        {d.transcripts?.length ? <> ({d.transcripts.map((t: any, i: number) => <span key={t.url}>{i ? ", " : ""}<a href={t.url} target="_blank" rel="noreferrer">{t.label}</a></span>)})</> : null}
        {s?.documents?.annual_reports?.[0] && <> · <a href={s.documents.annual_reports[0].url} target="_blank" rel="noreferrer">Annual report {s.documents.annual_reports[0].year}</a></>}.
        <br />No news or broker reports are used. {d.llm?.provider ? `Models: ${d.llm.cheap} for extraction, ${d.llm.strong} for the summary.` : "No language model is configured, so extraction is rule-based."}
      </div>
    </>
  );
}
function Row3({ label, vals }: { label: string; vals: (number | null)[] }) {
  return (<><div className="muted">{label}</div>{vals.map((v, i) => <div key={i} style={{ textAlign: "right" }}>{v == null ? "—" : Math.round(v)}</div>)}</>);
}

export default function Research({ symbol, setSymbol, demo, book }: { symbol: string | null; setSymbol: (s: string | null) => void; demo: string[]; book: any[] }) {
  const [q, setQ] = useState("");
  const [sug, setSug] = useState<any[]>([]);
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const voice = useVoice((t) => { setQ(t); api.search(t).then((r) => r[0] && setSymbol(r[0].symbol)); });
  const poll = useRef<number>();

  useEffect(() => {
    if (q.trim().length < 2) return setSug([]);
    const t = setTimeout(() => api.search(q).then(setSug).catch(() => setSug([])), 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    window.clearInterval(poll.current);
    setD(null); setErr(null);
    if (!symbol) return;
    window.scrollTo({ top: 0 });
    api.research(symbol).then((doc) => {
      setD(doc);
      if (doc.status === "running") {
        poll.current = window.setInterval(() => {
          api.researchGet(symbol).then((x) => { setD(x); if (x.status !== "running") window.clearInterval(poll.current); }).catch(() => {});
        }, 1500);
      }
    }).catch((e) => setErr(/404/.test(String(e)) || /No data/.test(String(e)) ? `No primary data found for ${symbol}.` : String(e.message || e)));
    return () => window.clearInterval(poll.current);
  }, [symbol]);

  return (
    <div className="page">
      <div className="search">
        <span className="ico"><Icon.search /></span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Any NSE company or ticker…" onKeyDown={(e) => { if (e.key === "Enter" && sug[0]) { setSymbol(sug[0].symbol); setQ(""); setSug([]); } }} />
        {voice.supported && <button className={`mic ${voice.live ? "live" : ""}`} onClick={voice.live ? voice.stop : voice.start}><Icon.mic /> {voice.live ? "Listening" : "Speak"}</button>}
        {sug.length > 0 && (
          <div className="suggest">
            {sug.map((s) => (
              <button key={s.symbol} onClick={() => { setSymbol(s.symbol); setQ(""); setSug([]); }}>
                <span className="sym">{s.symbol}</span><span>{s.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {!symbol && (
        <>
          <h1 className="page-title">Research</h1>
          <p className="lede">Search any NSE-listed company. FINN reads its last four earnings calls, picks out the guidance management gave, and checks it against the results filed afterwards. It uses only the company's own filings and transcripts.</p>
          <Section title="Outside the portfolio">
            <div className="tags" style={{ paddingTop: 12 }}>{demo.map((s) => <button key={s} className="tag" onClick={() => setSymbol(s)}>{s}</button>)}</div>
          </Section>
          <Section title="In the portfolio">
            <div className="tags" style={{ paddingTop: 12 }}>{book.map((p) => <button key={p.symbol} className="tag" onClick={() => setSymbol(p.symbol)}>{p.symbol}</button>)}</div>
          </Section>
        </>
      )}

      {symbol && err && (
        <div style={{ marginTop: 16 }}>
          <div className="err">{err}</div>
          <button className="act primary" onClick={() => setSymbol(null)} style={{ marginTop: 8 }}>Back to research</button>
        </div>
      )}
      {symbol && !err && !d && (<><div className="skeleton" style={{ height: 160, marginTop: 10 }} /><div className="skeleton" style={{ height: 220, marginTop: 12 }} /></>)}
      {symbol && d && <Dossier d={d} />}
    </div>
  );
}

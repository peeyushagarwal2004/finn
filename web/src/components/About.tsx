import { useEffect, useState } from "react";
import { api } from "../api";
import { fmt, Section } from "./ui";

export default function About() {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api.stats().then(setS).catch(() => setS({})); }, []);
  const llm = s?.llm || {};
  const n = (v: any) => (v == null ? "–" : Number(v).toLocaleString("en-IN"));

  return (
    <div className="page howto">
      <h1 className="page-title">How FINN works</h1>
      <p className="lede">What it reads, how it decides what matters, and what it costs to run.</p>

      <Section title="What it has read" aside={s?.last_refresh ? `refreshed ${fmt.ago(s.last_refresh.ts)} ago` : ""}>
        <div className="kpis" style={{ borderTop: 0 }}>
          <div className="kpi"><span>Filings stored</span><b>{n(s?.filings_stored)}</b></div>
          <div className="kpi"><span>PDFs read</span><b>{n(s?.pdfs_read)}</b></div>
          <div className="kpi"><span>PDF pages</span><b>{n(s?.pdf_pages)}</b></div>
          <div className="kpi"><span>Earnings calls</span><b>{n(s?.transcripts)}</b></div>
          <div className="kpi"><span>Annual reports</span><b>{n(s?.annual_reports)}</b></div>
          <div className="kpi"><span>Companies researched</span><b>{n(s?.dossiers)}</b></div>
        </div>
      </Section>

      <Section title="Sources">
        <ol>
          <li><b>NSE announcements feed</b>, checked every 5 minutes. It only holds the latest few hundred items, most of them mutual-fund notices, so FINN keeps its own history.</li>
          <li><b>Exchange filings on BSE</b>: results PDFs, earnings call transcripts and annual reports, read directly.</li>
          <li><b>screener.in</b> for standardised statements and links to those documents.</li>
          <li><b>Yahoo Finance</b> for end-of-day prices and volumes.</li>
        </ol>
        <p className="lede">Research uses only the company's own filings and transcripts. No news, broker reports or model background knowledge.</p>
      </Section>

      <Section title="How decisions are made">
        <ol>
          <li><b>Ranking filings</b> is done by rules, so every score can be explained. Size counts: an order is compared with revenue, a share issue with market cap, a penalty with the size of the company.</li>
          <li><b>Results numbers</b> are read from the filed PDF and checked against reported totals before they're shown.</li>
          <li><b>Guidance</b>: rules cut each call down to about 25 forward-looking sentences from management. A small model labels them; it can only point at sentences, so quotes are always verbatim.</li>
          <li><b>The written summary</b> comes from one call to a larger model per company, using a numbered list of facts. Points that don't cite a fact are dropped.</li>
          <li><b>When unsure, FINN leaves it out.</b> Unreconciled numbers, implausible targets and uncited claims are not shown.</li>
        </ol>
      </Section>

      <Section title="Cost">
        <div className="kv"><span className="muted">Language model</span><span>{llm.provider ? `${llm.provider}: ${llm.cheap} / ${llm.strong}` : "None configured. Everything above runs on rules."}</span></div>
        <div className="kv"><span className="muted">Model calls this session</span><b>{n(llm.calls)} ({n(llm.by_tier?.cheap)} small, {n(llm.by_tier?.strong)} large)</b></div>
        <div className="kv"><span className="muted">Answered from cache</span><b>{n(llm.cache_hits || 0)}</b></div>
        <div className="kv"><span className="muted">Saved answers on disk</span><b>{n(s?.llm_cached_answers)}</b></div>
        <div className="kv"><span className="muted">Tokens in / out</span><b>{n(llm.tokens_in)} / {n(llm.tokens_out)}</b></div>
        <div className="kv"><span className="muted">Spend at list prices</span><b>${(llm.usd || 0).toFixed(4)}{llm.free ? " (free tier: $0)" : ""}</b></div>
        <p className="lede" style={{ marginTop: 10 }}>A company costs about six model calls the first time it's researched and nothing after that, because filings never change and every answer is cached.</p>
      </Section>
    </div>
  );
}

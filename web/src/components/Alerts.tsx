import { useEffect, useRef, useState } from "react";
import { api, Rules, syncPush } from "../api";
import { fmt, Section } from "./ui";
import { headlineFor } from "./Cards";

const CATS: [string, string][] = [
  ["results", "Results"], ["management_change", "Management"], ["M&A", "M&A"], ["fund_raise", "Fund raise"],
  ["litigation", "Litigation"], ["credit_rating", "Ratings"], ["pledging", "Pledging"], ["capex", "Capex"],
  ["bonus_split", "Bonus / split"], ["insider_trading", "Insider trades"], ["dividend", "Dividends"], ["press_release", "Orders / PR"],
];

export default function Alerts({ rules, setRules, onDig, muted, pushState, setPushState }: {
  rules: Rules; setRules: (r: Rules) => void; onDig: (s: string) => void; muted: string[]; pushState: string; setPushState: (s: string) => void;
}) {
  const [draft, setDraft] = useState<Rules>(rules);
  const [bt, setBt] = useState<any>(null);
  const [live, setLive] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const t = useRef<number>();

  useEffect(() => setDraft(rules), [rules]);
  useEffect(() => {
    window.clearTimeout(t.current);
    t.current = window.setTimeout(() => api.backtest(draft).then(setBt).catch(() => setBt(null)), 250);
  }, [JSON.stringify(draft)]);
  useEffect(() => {
    api.digest({ hours: 168, rules }).then((d) => setLive([...d.needs_you, ...d.worth_knowing].filter((i: any) => i.alert).slice(0, 12))).catch(() => setLive([]));
  }, [JSON.stringify(rules)]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(rules);
  const set = (k: keyof Rules, v: any) => setDraft({ ...draft, [k]: v });
  const maxN = Math.max(1, ...(bt?.timeline || []).map((x: any) => x.n));

  return (
    <div className="page">
      <h1 className="page-title">Alert rules</h1>
      <p className="lede">Set what counts as unusual. The count further down shows how often these rules would have fired over the last 90 trading days, so you can tune them before saving.</p>

      <Section title="Price and volume">
        <div className="panel">
          <div className="rule">
            <div className="rule-h"><b>Daily move beyond</b><span className="v num">±{draft.price_pct}%</span></div>
            <input type="range" min={1} max={10} step={0.5} value={draft.price_pct} onChange={(e) => set("price_pct", +e.target.value)} aria-label="Price move threshold" />
          </div>
          <div className="rule">
            <div className="rule-h"><b>Volume above</b><span className="v num">{draft.vol_mult.toFixed(1)}×</span></div>
            <p>Compared with the stock's own 20-day average.</p>
            <input type="range" min={1.2} max={5} step={0.1} value={draft.vol_mult} onChange={(e) => set("vol_mult", +e.target.value)} aria-label="Volume multiple threshold" />
          </div>
          <div className="rule">
            <div className="rule-h">
              <b>Adjust for each stock's volatility</b>
              <button className={`toggle ${draft.use_sigma ? "on" : ""}`} onClick={() => set("use_sigma", !draft.use_sigma)} aria-label="Toggle volatility-adjusted alerts" />
            </div>
            <p>A 3% day is normal for a small-cap and rare for a large bank. This measures the move against the stock's own 60-day volatility.</p>
            {draft.use_sigma && (
              <>
                <div className="rule-h" style={{ marginTop: 4 }}><span className="muted" style={{ fontSize: 13 }}>Move larger than</span><span className="v num">{draft.sigma.toFixed(1)}σ</span></div>
                <input type="range" min={1.5} max={4} step={0.1} value={draft.sigma} onChange={(e) => set("sigma", +e.target.value)} aria-label="Sigma threshold" />
              </>
            )}
          </div>
        </div>
      </Section>

      <Section title="Filings that trigger an alert">
        <div className="tags" style={{ paddingTop: 12 }}>
          {CATS.map(([k, l]) => {
            const on = draft.categories.includes(k);
            return (
              <button key={k} className={`tag ${on ? "on" : ""}`} onClick={() => set("categories", on ? draft.categories.filter((c) => c !== k) : [...draft.categories, k])}>{l}</button>
            );
          })}
        </div>
        <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>Only filings FINN rates as material. A CFO leaving triggers one; a company secretary changing doesn't.</div>
      </Section>

      <Section title="How often this would have fired" aside="last 90 sessions">
        <div className="panel bt">
          {!bt ? <div className="skeleton" style={{ height: 120 }} /> : (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span className="bt-big num">{bt.per_week}</span>
                <span className="muted">price and volume alerts a week<br /><span className="faint">{bt.total} over {bt.sessions} trading days</span></span>
              </div>
              <div className="bt-bars" aria-label="Alerts per session">
                {bt.timeline.map((x: any) => <i key={x.date} className={x.n ? "" : "zero"} style={{ height: `${x.n ? Math.max(8, (100 * x.n) / maxN) : 4}%` }} title={`${x.date}: ${x.n}`} />)}
              </div>
              <div className="faint" style={{ fontSize: 11, display: "flex", justifyContent: "space-between" }}>
                <span>{bt.timeline[0]?.date}</span><span>{bt.timeline[bt.timeline.length - 1]?.date}</span>
              </div>
              <div style={{ marginTop: 12 }}>
                {Object.entries(bt.by_kind).map(([k, v]: any) => (
                  <div className="kv" key={k}><span className="muted">{k === "sigma" ? "Volatility-adjusted move" : k === "price" ? "Daily move" : "Volume spike"}</span><b className="num">{v}</b></div>
                ))}
                {bt.by_symbol?.length > 0 && (
                  <div className="kv"><span className="muted">Most alerts</span><span className="num">{bt.by_symbol.slice(0, 3).map((x: any) => `${x[0]} ${x[1]}`).join(" · ")}</span></div>
                )}
              </div>
            </>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button className="btn" disabled={!dirty} onClick={() => setRules(draft)} style={{ flex: 1 }}>{dirty ? "Save rules" : "Saved"}</button>
            {dirty && <button className="btn ghost" onClick={() => setDraft(rules)}>Undo</button>}
          </div>
        </div>
      </Section>

      <Section title="On this device">
        <div className="panel" style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 12 }}>
          <div style={{ flex: 1, fontSize: 13.5 }}>
            <b>Notifications</b>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {pushState === "on" ? "On for this device. FINN checks every 10 minutes and notifies you even when the app is closed."
                : pushState === "denied" ? "Blocked in this browser's settings. Allow notifications for this site to turn them on."
                : pushState === "unsupported" ? "This browser can't receive background notifications. On iPhone, add FINN to your home screen first (Share, then Add to Home Screen)."
                : pushState === "not-configured" ? "Background notifications aren't set up on this server, so FINN will only notify you while it's open."
                : "Get notified when a rule is triggered, even when the app is closed."}
            </div>
          </div>
          {pushState !== "on" && pushState !== "unsupported" && (
            <button className="btn" disabled={busy} onClick={() => { setBusy(true); syncPush(rules, muted, true).then(setPushState).catch(() => setPushState("off")).finally(() => setBusy(false)); }}>{busy ? "…" : "Turn on"}</button>
          )}
        </div>
      </Section>

      <Section title="Triggered in the last 7 days" aside={live ? `${live.length}` : ""}>
        {!live ? <div className="skeleton" style={{ height: 80 }} /> : live.length === 0 ? <div className="zero">Nothing crossed your thresholds.</div> : (
          <div className="rows">
            {live.map((it) => (
              <button key={it.id} className="row" onClick={() => onDig(it.symbol)}>
                <span className="sym">{it.symbol}</span>
                <span className="body">
                  <span className="t">{headlineFor(it)}</span>
                  <span className="m"><span>{it.category_label}</span><span>{fmt.ago(it.ts)}</span>{it.unexplained && it.score >= 65 && <span className="down">no filing</span>}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

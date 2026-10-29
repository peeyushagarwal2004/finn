import { useEffect, useRef, useState } from "react";
import { api, Rules } from "../api";
import { fmt, Section } from "./ui";

const CATS: [string, string][] = [
  ["results", "Results"], ["management_change", "Management"], ["M&A", "M&A"], ["fund_raise", "Fund raise"],
  ["litigation", "Litigation"], ["credit_rating", "Ratings"], ["pledging", "Pledging"], ["capex", "Capex"],
  ["bonus_split", "Bonus / split"], ["insider_trading", "Insider trades"], ["dividend", "Dividends"], ["press_release", "Orders / PR"],
];

export default function Alerts({ rules, setRules, onDig }: { rules: Rules; setRules: (r: Rules) => void; onDig: (s: string) => void }) {
  const [draft, setDraft] = useState<Rules>(rules);
  const [bt, setBt] = useState<any>(null);
  const [live, setLive] = useState<any[] | null>(null);
  const [perm, setPerm] = useState<string>(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
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
      <h1 className="headline" style={{ marginTop: 12 }}>You decide what <em>unusual</em> means.</h1>
      <div className="muted" style={{ fontSize: 14, margin: "-6px 2px 4px" }}>
        Every threshold is a trade between coverage and interruptions. FINN replays the last 90 sessions so you can see the price before you pay it.
      </div>

      <Section title="Price & volume">
        <div className="panel">
          <div className="rule">
            <div className="rule-h"><b>Daily move beyond</b><span className="v num">±{draft.price_pct}%</span></div>
            <input type="range" min={1} max={10} step={0.5} value={draft.price_pct} onChange={(e) => set("price_pct", +e.target.value)} aria-label="Price move threshold" />
          </div>
          <div className="rule">
            <div className="rule-h"><b>Volume above</b><span className="v num">{draft.vol_mult.toFixed(1)}×</span></div>
            <p>…its own 20-session average.</p>
            <input type="range" min={1.2} max={5} step={0.1} value={draft.vol_mult} onChange={(e) => set("vol_mult", +e.target.value)} aria-label="Volume multiple threshold" />
          </div>
          <div className="rule">
            <div className="rule-h">
              <b>Unusual for this stock</b>
              <button className={`toggle ${draft.use_sigma ? "on" : ""}`} onClick={() => set("use_sigma", !draft.use_sigma)} aria-label="Toggle volatility-adjusted alerts" />
            </div>
            <p>A 3% day is noise for a small-cap and news for a bank. This lens scales the move by the stock's own 60-day volatility.</p>
            {draft.use_sigma && (
              <>
                <div className="rule-h" style={{ marginTop: 4 }}><span className="muted" style={{ fontSize: 13 }}>Move larger than</span><span className="v num">{draft.sigma.toFixed(1)}σ</span></div>
                <input type="range" min={1.5} max={4} step={0.1} value={draft.sigma} onChange={(e) => set("sigma", +e.target.value)} aria-label="Sigma threshold" />
              </>
            )}
          </div>
        </div>
      </Section>

      <Section title="Filings that ping you">
        <div className="routine">
          {CATS.map(([k, l]) => {
            const on = draft.categories.includes(k);
            return (
              <button key={k} className={`chip ${on ? "on" : ""}`} onClick={() => set("categories", on ? draft.categories.filter((c) => c !== k) : [...draft.categories, k])}>{l}</button>
            );
          })}
        </div>
        <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>Only when FINN rates the filing material (a CFO exit pings; a company-secretary change doesn't).</div>
      </Section>

      <Section title="What that would have cost you" aside="last 90 sessions">
        <div className="panel bt">
          {!bt ? <div className="skeleton" style={{ height: 120 }} /> : (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span className="bt-big num">{bt.per_week}</span>
                <span className="muted">price/volume pings a week<br /><span className="faint">{bt.total} across {bt.sessions} sessions</span></span>
              </div>
              <div className="bt-bars" aria-label="Alerts per session">
                {bt.timeline.map((x: any) => <i key={x.date} className={x.n ? "" : "zero"} style={{ height: `${x.n ? Math.max(8, (100 * x.n) / maxN) : 4}%` }} title={`${x.date}: ${x.n}`} />)}
              </div>
              <div className="faint" style={{ fontSize: 11, display: "flex", justifyContent: "space-between" }}>
                <span>{bt.timeline[0]?.date}</span><span>{bt.timeline[bt.timeline.length - 1]?.date}</span>
              </div>
              <div style={{ marginTop: 12 }}>
                {Object.entries(bt.by_kind).map(([k, v]: any) => (
                  <div className="kv" key={k}><span className="muted">{k === "sigma" ? "Volatility-adjusted" : k === "price" ? "Price move" : "Volume spike"}</span><b className="num">{v}</b></div>
                ))}
                {bt.by_symbol?.length > 0 && (
                  <div className="kv"><span className="muted">Noisiest</span><span className="num">{bt.by_symbol.slice(0, 3).map((x: any) => `${x[0]} ${x[1]}`).join(" · ")}</span></div>
                )}
              </div>
            </>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button className="btn" disabled={!dirty} onClick={() => setRules(draft)} style={{ flex: 1 }}>{dirty ? "Save these rules" : "Rules saved"}</button>
            {dirty && <button className="btn ghost" onClick={() => setDraft(rules)}>Undo</button>}
          </div>
        </div>
      </Section>

      <Section title="On this device">
        <div className="panel" style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1, fontSize: 13.5 }}>
            <b>Notifications</b>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {perm === "granted" ? "On. FINN checks every 5 minutes while open and pings you for new alerts." : perm === "denied" ? "Blocked in browser settings." : perm === "unsupported" ? "Not supported in this browser — add FINN to your home screen." : "Get a ping the moment a rule trips."}
            </div>
          </div>
          {perm === "default" && (
            <button className="btn" onClick={() => Notification.requestPermission().then(setPerm)}>Enable</button>
          )}
        </div>
      </Section>

      <Section title="Triggered this week" aside={live ? `${live.length}` : ""}>
        {!live ? <div className="skeleton" style={{ height: 80 }} /> : live.length === 0 ? <div className="zero muted">Nothing crossed your thresholds.</div> : (
          <div className="rows">
            {live.map((it) => (
              <button key={it.id} className="row" onClick={() => onDig(it.symbol)}>
                <span className="tick">{it.symbol}</span>
                <span className="body">
                  <span className="t">{it.kind === "move" ? it.title : it.oneliner && it.oneliner.length > 20 ? it.oneliner : it.title}</span>
                  <span className="m"><span>{it.category_label}</span><span>·</span><span>{fmt.ago(it.ts)}</span>{it.unexplained && it.score >= 65 && <><span>·</span><span className="down">no filing</span></>}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

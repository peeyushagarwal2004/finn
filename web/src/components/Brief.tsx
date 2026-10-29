import { useEffect, useMemo, useRef, useState } from "react";
import { api, prefs, Rules } from "../api";
import { PushCard, WorthRow } from "./Cards";
import { fmt, Icon, Section } from "./ui";

export type Win = { key: string; label: string; hours?: number; since?: number };

export function windows(lastVisit: number | null): Win[] {
  const w: Win[] = [];
  if (lastVisit && Date.now() / 1000 - lastVisit > 15 * 60) w.push({ key: "last", label: `Since ${fmt.ago(lastVisit)} ago`, since: lastVisit });
  return w.concat([
    { key: "24", label: "24 hours", hours: 24 },
    { key: "72", label: "3 days", hours: 72 },
    { key: "168", label: "7 days", hours: 168 },
    { key: "720", label: "30 days", hours: 720 },
  ]);
}

const greet = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

export default function Brief({ win, setWin, wins, rules, muted, setMuted, onDig, onCount, flash }: {
  win: Win; setWin: (w: Win) => void; wins: Win[]; rules: Rules; muted: string[]; setMuted: (m: string[]) => void;
  onDig: (sym: string) => void; onCount: (n: number) => void; flash: (msg: string, undo?: () => void) => void;
}) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, number>>(() => prefs.read("done", {}));
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [showRoutine, setShowRoutine] = useState<string | null>(null);

  const widened = useRef(false);
  useEffect(() => {
    setErr(null);
    setD(null);
    api.digest({ hours: win.hours, since: win.since, rules, muted }).then((x) => {
      // a quiet day shouldn't greet you with an empty screen: widen once to the first window with news
      const empty = x.counts.filings + x.counts.moves === 0;
      if (empty && !widened.current) {
        const i = wins.findIndex((w) => w.key === win.key);
        if (i >= 0 && i < wins.length - 1) {
          widened.current = true;
          flash(`Quiet ${win.label.toLowerCase()} — showing ${wins[i + 1].label.toLowerCase()}`);
          return setWin(wins[i + 1]);
        }
      }
      widened.current = true;
      setD(x);
    }).catch((e) => setErr(String(e.message || e)));
  }, [win.key, JSON.stringify(rules), muted.join(",")]);

  useEffect(() => prefs.write("done", done), [done]);

  const needs = useMemo(() => (d?.needs_you || []).filter((i: any) => !done[i.id]), [d, done]);
  const worth = useMemo(() => (d?.worth_knowing || []).filter((i: any) => !done[i.id]), [d, done]);
  const cleared = (d?.needs_you || []).length - needs.length;
  useEffect(() => onCount(needs.length), [needs.length]);

  const markDone = (it: any) => {
    setDone((x) => ({ ...x, [it.id]: Date.now() / 1000 }));
    flash(`Cleared ${it.symbol}`, () => setDone((x) => { const y = { ...x }; delete y[it.id]; return y; }));
  };
  const mute = (it: any) => {
    const key = `${it.symbol}:${it.category}`;
    setMuted(Array.from(new Set([...muted, key])));
    flash(`Muted ${it.category_label.toLowerCase()} for ${it.symbol}`, () => setMuted(muted.filter((m) => m !== key)));
  };

  const c = d?.counts;
  const total = c ? c.needs_you + c.worth_knowing + c.routine : 0;

  return (
    <div className="page">
      <div className="hello">{greet()} · {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
      <h1 className="headline">
        {!c ? "Reading the tape…" : needs.length === 0 ? <>You're <em>caught up.</em></> : <><em>{needs.length}</em> thing{needs.length === 1 ? "" : "s"} need{needs.length === 1 ? "s" : ""} you.</>}
      </h1>
      <div className="chips" role="tablist">
        {wins.map((w) => (
          <button key={w.key} className={`chip ${w.key === win.key ? "on" : ""}`} onClick={() => setWin(w)}>{w.label}</button>
        ))}
      </div>

      {err && <div className="err" style={{ marginTop: 14 }}>Couldn't load the digest. {err}</div>}
      {!d && !err && <div className="skeleton" style={{ height: 120, marginTop: 14 }} />}

      {c && (
        <div className="funnel">
          <div className="funnel-row">
            <div className="funnel-num"><b className="num">{c.filings}</b><span>filings</span></div>
            <div className="funnel-num"><b className="num">{c.moves}</b><span>price moves</span></div>
            <div className="funnel-arrow">→</div>
            <div className="funnel-num" style={{ textAlign: "right" }}><b className="num accent">{c.needs_you}</b><span>need you</span></div>
          </div>
          {total > 0 && (
            <div className="bar3">
              <i style={{ width: `${(100 * c.needs_you) / total}%`, background: "var(--accent)" }} />
              <i style={{ width: `${(100 * c.worth_knowing) / total}%`, background: "var(--text-2)", opacity: 0.5 }} />
              <i style={{ width: `${(100 * c.routine) / total}%`, background: "var(--line-2)" }} />
            </div>
          )}
          <div className="funnel-note">
            <span>{c.worth_knowing} worth a glance · {c.routine} set aside</span>
            {c.market_today ? <span>NSE today: {c.market_today.toLocaleString("en-IN")}+ filings</span> : null}
          </div>
        </div>
      )}

      {d && (
        <Section title="Needs you" aside={cleared ? `${cleared} cleared` : "swipe → done · ← mute"}>
          {needs.length ? (
            <div className="stack">
              {needs.map((it: any) => (
                <PushCard key={it.id} it={it} onDone={() => markDone(it)} onMute={() => mute(it)} onDig={() => onDig(it.symbol)} />
              ))}
            </div>
          ) : (
            <div className="zero">
              <div className="serif">Inbox zero.</div>
              <div className="muted" style={{ fontSize: 13.5, marginTop: 6 }}>
                FINN read {c.filings} filings and checked every chart in your book so you didn't have to. {c.routine} routine items were set aside.
              </div>
            </div>
          )}
        </Section>
      )}

      {worth.length > 0 && (
        <Section title="Worth a glance" aside={`${worth.length}`}>
          <div className="rows">
            {worth.map((it: any) => (
              <div key={it.id}>
                <WorthRow it={it} onOpen={() => setOpenRow(openRow === it.id ? null : it.id)} />
                {openRow === it.id && (
                  <div style={{ padding: "0 14px 12px 14px" }}>
                    {it.summary && it.summary !== it.oneliner && <div className="sub" style={{ fontSize: 13 }}>{it.title}</div>}
                    <div className="card-actions" style={{ marginTop: 6 }}>
                      <button className="act primary" onClick={() => onDig(it.symbol)}>Dig in <Icon.arrow /></button>
                      {it.url && <a className="act" href={it.url} target="_blank" rel="noreferrer">Filing <Icon.ext /></a>}
                      <span className="spacer" />
                      {it.kind === "filing" && <button className="act" onClick={() => mute(it)}><Icon.mute /> Mute</button>}
                      <button className="act" onClick={() => markDone(it)}><Icon.check /> Done</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {d?.routine?.length > 0 && (
        <Section title="Set aside" aside="routine paperwork">
          <div className="routine">
            {d.routine.map((g: any) => (
              <button key={g.label} className={`chip ${showRoutine === g.label ? "on" : ""}`} onClick={() => setShowRoutine(showRoutine === g.label ? null : g.label)}>
                {g.label}<b>{g.count}</b>
              </button>
            ))}
          </div>
          {showRoutine && (
            <div className="rows" style={{ marginTop: 10 }}>
              {d.routine.find((g: any) => g.label === showRoutine)?.items.map((it: any) => (
                <a key={it.id} className="row" href={it.url} target="_blank" rel="noreferrer">
                  <span className="tick">{it.symbol}</span>
                  <span className="body"><span className="t" style={{ fontSize: 13 }}>{it.title}</span><span className="m">{fmt.ago(it.ts)}{it.muted ? " · muted by you" : ""}</span></span>
                </a>
              ))}
            </div>
          )}
          {muted.length > 0 && (
            <div className="faint" style={{ fontSize: 12, marginTop: 10 }}>
              Muted: {muted.map((m) => m.replace(":", " · ")).join(", ")} · <button className="accent" onClick={() => setMuted([])}>reset</button>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

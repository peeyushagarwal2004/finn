import { useEffect, useMemo, useRef, useState } from "react";
import { api, prefs, Rules } from "../api";
import { PushCard, WorthRow, headlineFor } from "./Cards";
import { fmt, Icon, Section } from "./ui";

export type Win = { key: string; label: string; hours?: number; since?: number };

export function windows(lastVisit: number | null): Win[] {
  const w: Win[] = [];
  if (lastVisit && Date.now() / 1000 - lastVisit > 15 * 60) w.push({ key: "last", label: "Since last visit", since: lastVisit });
  return w.concat([
    { key: "24", label: "Today", hours: 24 },
    { key: "72", label: "3 days", hours: 72 },
    { key: "168", label: "Week", hours: 168 },
    { key: "720", label: "Month", hours: 720 },
  ]);
}

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
      // on a quiet day, open on the first window that has something in it
      const empty = x.counts.filings + x.counts.moves === 0;
      if (empty && !widened.current) {
        const i = wins.findIndex((w) => w.key === win.key);
        if (i >= 0 && i < wins.length - 1) {
          widened.current = true;
          flash(`Nothing new ${win.key === "24" ? "today" : "in that window"}. Showing ${wins[i + 1].label.toLowerCase()}.`);
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
    flash(`Marked read: ${it.symbol}`, () => setDone((x) => { const y = { ...x }; delete y[it.id]; return y; }));
  };
  const mute = (it: any) => {
    const key = `${it.symbol}:${it.category}`;
    setMuted(Array.from(new Set([...muted, key])));
    flash(`Muted ${it.category_label.toLowerCase()} for ${it.symbol}`, () => setMuted(muted.filter((m) => m !== key)));
  };

  const c = d?.counts;
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="page">
      <div className="masthead">
        <h1>{new Date().getHours() < 12 ? "Morning" : new Date().getHours() < 17 ? "Midday" : "Evening"} note</h1>
        <div className="dateline">
          <span>{today}</span>
          {c && <span className="num">{c.filings} filings · {c.moves} price alerts</span>}
          {c?.market_today ? <span className="num">NSE today {c.market_today.toLocaleString("en-IN")}</span> : null}
        </div>
      </div>
      <div className="chips" role="tablist">
        {wins.map((w) => (
          <button key={w.key} className={`chip ${w.key === win.key ? "on" : ""}`} onClick={() => setWin(w)}>{w.label}</button>
        ))}
      </div>

      {err && <div className="err">Couldn't load the note: {err}</div>}
      {!d && !err && <div className="skeleton" style={{ height: 260, marginTop: 14 }} />}

      {d && (
        <Section title="To read" aside={`${needs.length} left${cleared ? ` · ${cleared} read` : ""}`}>
          {needs.length ? (
            <div className="stack">
              {needs.map((it: any, i: number) => (
                <PushCard key={it.id} it={it} lead={i === 0} onDone={() => markDone(it)} onMute={() => mute(it)} onDig={() => onDig(it.symbol)} />
              ))}
            </div>
          ) : (
            <div className="zero">
              <b>All read.</b>
              {c.filings} filings and {c.moves} price alerts in this window. {c.routine} routine filings are filed below.
            </div>
          )}
        </Section>
      )}

      {worth.length > 0 && (
        <Section title="Briefly" aside={`${worth.length}`}>
          <div className="rows">
            {worth.map((it: any) => (
              <div key={it.id}>
                <WorthRow it={it} onOpen={() => setOpenRow(openRow === it.id ? null : it.id)} />
                {openRow === it.id && (
                  <div style={{ padding: "0 0 12px 94px", borderBottom: "1px solid var(--rule)" }}>
                    {it.title && it.title !== headlineFor(it) && <div className="standfirst" style={{ marginTop: 0 }}>{it.title}</div>}
                    <div className="card-actions">
                      <button className="act primary" onClick={() => onDig(it.symbol)}>Research</button>
                      {it.url && <a className="act" href={it.url} target="_blank" rel="noreferrer">Filing <Icon.ext /></a>}
                      <span className="spacer" />
                      {it.kind === "filing" && <button className="act" onClick={() => mute(it)}>Mute</button>}
                      <button className="act" onClick={() => markDone(it)}>Mark read</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {d?.upcoming?.length > 0 && (
        <Section title="Results coming up" aside="from board-meeting notices">
          <div className="cal">
            {Object.entries(d.upcoming.reduce((g: any, u: any) => ((g[u.date] = g[u.date] || []).push(u), g), {})).slice(0, 4).map(([date, us]: any) => {
              const dt = new Date(date + "T00:00:00");
              const days = Math.round((dt.getTime() - new Date(new Date().toDateString()).getTime()) / 86400000);
              return (
                <div key={date} className="cal-row">
                  <span className="num cal-d">{days === 0 ? "Today" : days === 1 ? "Tomorrow" : dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
                  <span>{us.map((u: any, i: number) => <span key={u.symbol}>{i ? ", " : ""}<a className="sym" href={u.url} target="_blank" rel="noreferrer">{u.symbol}</a></span>)}</span>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {d?.routine?.length > 0 && (
        <Section title="Routine filings" aside={`${c.routine}, not shown above`}>
          <div className="chips" style={{ borderBottom: 0 }}>
            {d.routine.map((g: any) => (
              <button key={g.label} className={`chip sm ${showRoutine === g.label ? "on" : ""}`} onClick={() => setShowRoutine(showRoutine === g.label ? null : g.label)}>
                {g.label}<b>{g.count}</b>
              </button>
            ))}
          </div>
          {showRoutine && (
            <div className="rows">
              {d.routine.find((g: any) => g.label === showRoutine)?.items.map((it: any) => (
                <a key={it.id} className="row" href={it.url} target="_blank" rel="noreferrer">
                  <span className="sym">{it.symbol}</span>
                  <span className="body"><span className="t" style={{ fontSize: 13 }}>{it.title}</span><span className="m">{fmt.ago(it.ts)} ago{it.muted ? " · muted" : ""}</span></span>
                </a>
              ))}
            </div>
          )}
          {muted.length > 0 && (
            <div className="faint" style={{ fontSize: 12, marginTop: 10 }}>
              Muted: {muted.map((m) => m.replace(":", " ")).join(", ")}. <button className="link" onClick={() => setMuted([])}>Unmute all</button>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { api, prefs, Rules } from "./api";
import Alerts from "./components/Alerts";
import Brief, { Win, windows } from "./components/Brief";
import Holdings from "./components/Holdings";
import Research from "./components/Research";
import { Icon } from "./components/ui";

type Tab = "brief" | "alerts" | "research" | "book";

// The previous visit defines "since you last looked"; this visit becomes the next one's anchor.
const LAST_VISIT: number | null = prefs.read<number | null>("lastVisit", null);
prefs.write("lastVisit", Date.now() / 1000);

export default function App() {
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1) as Tab) || "brief");
  const [meta, setMeta] = useState<any>(null);
  const [rules, setRulesState] = useState<Rules | null>(() => prefs.read<Rules | null>("rules", null));
  const [muted, setMutedState] = useState<string[]>(() => prefs.read("muted", []));
  const wins = useMemo(() => windows(LAST_VISIT), []);
  const [win, setWin] = useState<Win>(wins.find((w) => w.key === "24") || wins[0]);
  const [symbol, setSymbol] = useState<string | null>(null);
  const [theme, setTheme] = useState<string>(() => prefs.read("theme", matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  const [speaking, setSpeaking] = useState(false);
  const [needCount, setNeedCount] = useState(0);
  const [toast, setToast] = useState<{ msg: string; undo?: () => void } | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const toastT = useRef<number>();

  useEffect(() => { api.meta().then((m) => { setMeta(m); if (!rules) setRulesState(m.default_rules); }); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; prefs.write("theme", theme); document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f4f2ec" : "#0d0e10"); }, [theme]);
  useEffect(() => { if (location.hash.slice(1) !== tab) location.hash = tab; window.scrollTo({ top: 0 }); }, [tab]);
  useEffect(() => {
    const f = () => { const h = location.hash.slice(1) as Tab; if (["brief", "alerts", "research", "book"].includes(h)) setTab(h); };
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  useEffect(() => { const f = () => setScrolled(window.scrollY > 8); addEventListener("scroll", f, { passive: true }); return () => removeEventListener("scroll", f); }, []);
  useEffect(() => { if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {}); }, []);

  const setRules = (r: Rules) => { setRulesState(r); prefs.write("rules", r); flash("Rules saved — FINN is watching"); };
  const setMuted = (m: string[]) => { setMutedState(m); prefs.write("muted", m); };
  const flash = (msg: string, undo?: () => void) => {
    setToast({ msg, undo });
    window.clearTimeout(toastT.current);
    toastT.current = window.setTimeout(() => setToast(null), 3500);
  };
  const dig = (s: string) => { setSymbol(s); setTab("research"); };

  // Push while open: poll for alerts and raise a system notification for anything new.
  useEffect(() => {
    if (!rules) return;
    const check = () => {
      if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
      api.digest({ hours: 24, rules, muted }).then((d) => {
        const seen: string[] = prefs.read("notified", []);
        const fresh = [...d.needs_you].filter((i: any) => i.alert && !seen.includes(i.id));
        fresh.slice(0, 3).forEach((i: any) => {
          const body = i.kind === "move" ? i.title : i.oneliner || i.title;
          navigator.serviceWorker?.ready.then((reg) => reg.showNotification(`${i.symbol} · ${i.category_label}`, { body, tag: i.id, icon: "/icon.svg" }))
            .catch(() => new Notification(`${i.symbol} · ${i.category_label}`, { body }));
        });
        prefs.write("notified", [...seen, ...fresh.map((i: any) => i.id)].slice(-300));
      }).catch(() => {});
    };
    check();
    const t = setInterval(check, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [JSON.stringify(rules), muted.join(",")]);

  const listen = () => {
    if (speaking) { speechSynthesis.cancel(); setSpeaking(false); return; }
    if (!("speechSynthesis" in window)) return flash("Audio brief isn't supported in this browser");
    setSpeaking(true);
    api.brief({ hours: win.hours, since: win.since, rules: rules || undefined, muted }).then(({ script }) => {
      const u = new SpeechSynthesisUtterance(script);
      const v = speechSynthesis.getVoices().find((x) => /en-IN/i.test(x.lang)) || speechSynthesis.getVoices().find((x) => /^en/i.test(x.lang));
      if (v) u.voice = v;
      u.rate = 1.04;
      u.onend = u.onerror = () => setSpeaking(false);
      speechSynthesis.speak(u);
    }).catch(() => setSpeaking(false));
  };

  if (!rules) return <div className="app"><div className="page"><div className="skeleton" style={{ height: 200, marginTop: 60 }} /></div></div>;

  return (
    <div className="app">
      <header className={`topbar ${scrolled ? "scrolled" : ""}`}>
        <div className="brand"><b>F<i>I</i>NN</b><span>{tab === "research" && symbol ? <button onClick={() => setSymbol(null)} className="muted">← research</button> : "your filter on the market"}</span></div>
        <div className="top-actions">
          <button className={`icon-btn ${speaking ? "on" : ""}`} onClick={listen} aria-label={speaking ? "Stop audio brief" : "Play audio brief"} title="Listen to your brief">{speaking ? <Icon.stop /> : <Icon.play />}</button>
          <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? <Icon.sun /> : <Icon.moon />}</button>
        </div>
      </header>
      {speaking && (
        <div className="player"><span className="wave"><i /><i /><i /><i /></span>Playing your {win.label.toLowerCase()} brief<span className="spacer" /><button onClick={listen}>Stop</button></div>
      )}

      {tab === "brief" && <Brief win={win} setWin={setWin} wins={wins} rules={rules} muted={muted} setMuted={setMuted} onDig={dig} onCount={setNeedCount} flash={flash} />}
      {tab === "alerts" && <Alerts rules={rules} setRules={setRules} onDig={dig} />}
      {tab === "research" && <Research symbol={symbol} setSymbol={setSymbol} demo={meta?.research_demo || []} book={meta?.portfolio || []} />}
      {tab === "book" && <Holdings onDig={dig} />}

      {tab !== "research" && (
        <div className="foot">
          Data: NSE/BSE filings, Yahoo Finance EOD, company statements via screener.in.<br />
          {meta?.last_refresh ? `Refreshed ${new Date(meta.last_refresh.ts * 1000).toLocaleString("en-IN", { hour: "numeric", minute: "2-digit", day: "numeric", month: "short" })}` : ""}
          {meta?.llm?.provider ? ` · models: ${meta.llm.cheap} / ${meta.llm.strong}` : " · rules-only mode"}
        </div>
      )}

      {toast && (
        <div className="flash" role="status">{toast.msg}{toast.undo && <button onClick={() => { toast.undo!(); setToast(null); }}>Undo</button>}</div>
      )}

      <nav className="tabbar">
        {([["brief", "Brief", Icon.brief], ["alerts", "Alerts", Icon.bell], ["research", "Research", Icon.search], ["book", "Book", Icon.book]] as const).map(([k, l, I]) => (
          <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k as Tab)}>
            <I />{l}{k === "brief" && needCount > 0 && <span className="badge">{needCount}</span>}
          </button>
        ))}
      </nav>
    </div>
  );
}

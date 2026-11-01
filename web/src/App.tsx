import { useEffect, useMemo, useRef, useState } from "react";
import { api, DEFAULT_RULES, prefs, Rules, swr, syncPush } from "./api";
import About from "./components/About";
import Alerts from "./components/Alerts";
import Brief, { Win, windows } from "./components/Brief";
import Holdings from "./components/Holdings";
import Research from "./components/Research";
import { Icon } from "./components/ui";

type Tab = "brief" | "alerts" | "research" | "book" | "about";

// The previous visit defines "since you last looked"; this visit becomes the next one's anchor.
const LAST_VISIT: number | null = prefs.read<number | null>("lastVisit", null);
prefs.write("lastVisit", Date.now() / 1000);

export default function App() {
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1) as Tab) || "brief");
  const [meta, setMeta] = useState<any>(null);
  const [rules, setRulesState] = useState<Rules | null>(() => prefs.read<Rules | null>("rules", null) || DEFAULT_RULES);
  const [muted, setMutedState] = useState<string[]>(() => prefs.read("muted", []));
  const wins = useMemo(() => windows(LAST_VISIT), []);
  const [win, setWin] = useState<Win>(wins.find((w) => w.key === "24") || wins[0]);
  const [symbol, setSymbol] = useState<string | null>(null);
  const [theme, setTheme] = useState<string>(() => prefs.read("theme", "light"));
  const [speaking, setSpeaking] = useState(false);
  const [needCount, setNeedCount] = useState(0);
  const [toast, setToast] = useState<{ msg: string; undo?: () => void } | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const toastT = useRef<number>();
  const [mounted, setMounted] = useState<Set<Tab>>(() => new Set<Tab>([tab]));
  useEffect(() => { setMounted((m) => (m.has(tab) ? m : new Set([...m, tab]))); }, [tab]);
  useEffect(() => {
    // once the first screen is up, load the other tabs quietly so the first switch is instant
    const t = window.setTimeout(() => setMounted((m) => new Set<Tab>([...m, "brief", "alerts", "book", "research"])), 1200);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => { swr("/api/meta", (m: any) => { setMeta(m); setRulesState((r) => r || m.default_rules); }).catch(() => {}); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; prefs.write("theme", theme); document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f6f2ea" : "#121211"); }, [theme]);
  useEffect(() => { if (location.hash.slice(1) !== tab) location.hash = tab; window.scrollTo({ top: 0 }); }, [tab]);
  useEffect(() => {
    const f = () => { const h = location.hash.slice(1) as Tab; if (["brief", "alerts", "research", "book", "about"].includes(h)) setTab(h); };
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  useEffect(() => { const f = () => setScrolled(window.scrollY > 8); addEventListener("scroll", f, { passive: true }); return () => removeEventListener("scroll", f); }, []);
  useEffect(() => { if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {}); }, []);

  const setRules = (r: Rules) => { setRulesState(r); prefs.write("rules", r); flash("Alert rules saved"); };
  const setMuted = (m: string[]) => { setMutedState(m); prefs.write("muted", m); };
  const flash = (msg: string, undo?: () => void) => {
    setToast({ msg, undo });
    window.clearTimeout(toastT.current);
    toastT.current = window.setTimeout(() => setToast(null), 3500);
  };
  const dig = (s: string) => { setSymbol(s); setTab("research"); };

  // Background alerts: re-register this device (and its current rules) with the server on every
  // open. When push isn't available, fall back to checking while the app is open.
  const [pushState, setPushState] = useState("off");
  useEffect(() => {
    if (!rules) return;
    syncPush(rules, muted).then(setPushState).catch(() => setPushState("off"));
  }, [JSON.stringify(rules), muted.join(",")]);
  useEffect(() => {
    if (!rules || pushState === "on") return;
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
  }, [JSON.stringify(rules), muted.join(","), pushState]);

  const listen = () => {
    if (speaking) { speechSynthesis.cancel(); setSpeaking(false); return; }
    if (!("speechSynthesis" in window)) return flash("This browser can't read the note aloud");
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
        <span className="brand">FINN</span>{tab === "research" && symbol && <button onClick={() => setSymbol(null)} className="brand-sub">← All research</button>}
        <div className="top-actions">
          <button className={`icon-btn ${speaking ? "on" : ""}`} onClick={listen} aria-label={speaking ? "Stop reading" : "Read the note aloud"} title="Read the note aloud">{speaking ? <Icon.stop /> : <Icon.play />}</button>
          <button className={`icon-btn ${tab === "about" ? "on" : ""}`} onClick={() => setTab("about")} aria-label="How FINN works" title="How FINN works"><Icon.info /></button>
          <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? <Icon.sun /> : <Icon.moon />}</button>
        </div>
      </header>
      {speaking && (
        <div className="player">Reading the note aloud ({win.label.toLowerCase()})<span className="spacer" /><button onClick={listen}>Stop</button></div>
      )}

      {/* tabs stay mounted once opened, so switching back is instant and keeps scroll-free state */}
      <div hidden={tab !== "brief"}>{mounted.has("brief") && <Brief win={win} setWin={setWin} wins={wins} rules={rules} muted={muted} setMuted={setMuted} onDig={dig} onCount={setNeedCount} flash={flash} />}</div>
      <div hidden={tab !== "alerts"}>{mounted.has("alerts") && <Alerts rules={rules} setRules={setRules} onDig={dig} muted={muted} pushState={pushState} setPushState={setPushState} />}</div>
      <div hidden={tab !== "research"}>{mounted.has("research") && <Research symbol={symbol} setSymbol={setSymbol} demo={meta?.research_demo || []} book={meta?.portfolio || []} />}</div>
      <div hidden={tab !== "book"}>{mounted.has("book") && <Holdings onDig={dig} />}</div>
      <div hidden={tab !== "about"}>{mounted.has("about") && <About />}</div>

      {tab !== "research" && (
        <div className="foot">
          Sources: NSE/BSE filings, Yahoo Finance end-of-day prices, company statements via screener.in.<br />
          {meta?.last_refresh ? `Refreshed ${new Date(meta.last_refresh.ts * 1000).toLocaleString("en-IN", { hour: "numeric", minute: "2-digit", day: "numeric", month: "short" })}` : ""}
          {meta?.llm?.provider ? ` · models: ${meta.llm.cheap} / ${meta.llm.strong}` : " · no language model configured"}
        </div>
      )}

      {toast && (
        <div className="flash" role="status">{toast.msg}{toast.undo && <button onClick={() => { toast.undo!(); setToast(null); }}>Undo</button>}</div>
      )}

      <nav className="tabbar">
        {([["brief", "Note", Icon.brief], ["alerts", "Alerts", Icon.bell], ["research", "Research", Icon.search], ["book", "Portfolio", Icon.book]] as const).map(([k, l, I]) => (
          <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k as Tab)}>
            <I />{l}{k === "brief" && needCount > 0 && <span className="badge">{needCount}</span>}
          </button>
        ))}
      </nav>
    </div>
  );
}

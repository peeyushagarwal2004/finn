import { Delta, fmt, Icon, Spark, SwipeCard } from "./ui";

const CAT_TONE: Record<string, string> = {
  results: "accent", management_change: "info", "M&A": "info", litigation: "down", move: "down",
  fund_raise: "info", credit_rating: "info", pledging: "down",
};

function Top({ it }: { it: any }) {
  return (
    <div className="card-top">
      <span className="tick">{it.symbol}</span>
      <span className="co">{it.company}</span>
      <span className={`pill ${CAT_TONE[it.category] || ""}`}>{it.category_label}</span>
      <span className="when">{fmt.ago(it.ts)}</span>
    </div>
  );
}

function Reasons({ it }: { it: any }) {
  if (!it.reasons?.length) return null;
  return (
    <div className="reasons">
      {it.reasons.map((r: string) => (
        <span key={r} className={`pill ${/No filing|Departure|downgrad|Immaterial/i.test(r) ? (/Immaterial/.test(r) ? "" : "down") : "accent"}`}>{r}</span>
      ))}
    </div>
  );
}

function ResultsBody({ r }: { r: any }) {
  return (
    <>
      <table className="rt num">
        <thead>
          <tr><th>₹ cr · {r.period}</th><th>Value</th><th>QoQ</th><th>YoY</th></tr>
        </thead>
        <tbody>
          {r.lines.map((l: any) => (
            <tr key={l.key} title={l.note || ""}>
              <td>{l.label}{l.note ? <span className="faint"> *</span> : null}</td>
              <td className="val">{fmt.n(l.cur)}</td>
              <td><Delta v={l.qoq_pct} /></td>
              <td><Delta v={l.yoy_pct} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
        {r.margins?.ebitda_margin != null && (
          <span className="pill">EBITDA margin {r.margins.ebitda_margin}%{r.margins.ebitda_margin_yoy != null && <> · <Delta v={(r.margins.ebitda_margin - r.margins.ebitda_margin_yoy) * 100} d={0} suffix=" bps" /></>}</span>
        )}
        <span className="spacer" />
        <Spark data={r.trend?.revenue || []} w={64} h={22} color="var(--text-2)" />
      </div>
      <div style={{ marginTop: 8 }}>
        <span className={`verify ${r.verified ? "ok" : ""}`}>
          {r.verified ? <><Icon.check /> Read from the filing{r.method.includes("model") ? " (model-read)" : ""}, reconciled with reported totals</> : <>From standardised quarterly data</>}
        </span>
        {r.note && <div className="faint" style={{ fontSize: 11.5, marginTop: 4 }}>{r.note}</div>}
        {r.lines.some((l: any) => l.note) && <div className="faint" style={{ fontSize: 11.5, marginTop: 4 }}>* {r.lines.find((l: any) => l.note).note}</div>}
      </div>
    </>
  );
}

const initials = (n: string) => n.split(" ").filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

function PeopleBody({ people }: { people: any[] }) {
  return (
    <div>
      {people.map((p) => (
        <div className="person" key={p.name}>
          <div className={`avatar ${p.direction === "out" ? "out" : ""}`}>{initials(p.name)}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="nm">{p.name} <span className={`pill ${p.direction === "in" ? "up" : ""}`} style={{ marginLeft: 4 }}>{p.direction === "in" ? "Incoming" : p.direction === "out" ? "Outgoing" : "Named"}</span></div>
            <div className="rl">{p.role || "Role not stated"}</div>
            {p.structured?.headline && <div className="bio"><b>{p.structured.headline}</b>{p.structured.previous?.length ? <> · {p.structured.previous.join(" → ")}</> : null}</div>}
            {p.bio && !p.structured && <div className="bio">{p.bio.length > 320 ? p.bio.slice(0, 317) + "…" : p.bio}</div>}
            {p.bio && <div className="faint" style={{ fontSize: 11.5, marginTop: 4 }}>Source: {p.bio_source === "filing" ? "the exchange filing's mandated profile" : p.bio_source === "wikipedia" ? <a href={p.bio_url} target="_blank" rel="noreferrer">Wikipedia</a> : "an earlier filing"}</div>}
            {!p.bio && p.direction !== "out" && <div className="hint">{p.bio_hint ? `${p.bio_hint}; this filing only references it.` : "No profile in the filing."}</div>}
            {p.direction !== "out" && (
              <a className="act primary" style={{ paddingLeft: 0 }} href={p.linkedin} target="_blank" rel="noreferrer">Background on LinkedIn <Icon.ext /></a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function MoveBody({ it }: { it: any }) {
  const mv = it.move;
  const n = mv.spark.length;
  const vmax = Math.max(...mv.vols, 1);
  return (
    <>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className={`serif num ${mv.ret >= 0 ? "up" : "down"}`} style={{ fontSize: 34, lineHeight: 1 }}>{fmt.pct(mv.ret)}</span>
        <span className="muted num" style={{ fontSize: 13 }}>close ₹{fmt.n(mv.close, 1)} · {new Date(mv.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
      </div>
      <div style={{ position: "relative", marginTop: 8 }}>
        <Spark data={mv.spark} w={320} h={54} fluid mark={n - 1} color={mv.ret >= 0 ? "var(--up)" : "var(--down)"} />
        <div style={{ display: "flex", gap: 2, height: 18, alignItems: "flex-end", marginTop: 2 }}>
          {mv.vols.map((v: number, i: number) => (
            <i key={i} style={{ flex: 1, height: `${Math.max(6, (100 * v) / vmax)}%`, background: i === mv.vols.length - 1 || (mv.vol_mult && v === vmax) ? "var(--accent)" : "var(--line-2)", borderRadius: 1 }} />
          ))}
        </div>
      </div>
      <div className="reasons">{mv.why.map((w: string) => <span key={w} className="pill">{w}</span>)}</div>
      {it.explained_by?.length ? (
        <div className="sub" style={{ marginTop: 10 }}>Likely driver: <b>{it.explained_by[0].title}</b> <span className="faint">({it.explained_by[0].category_label})</span></div>
      ) : (
        <div className="sub" style={{ marginTop: 10 }}>
          <b className={it.score >= 65 ? "down" : ""}>No filing explains this.</b> Moves without disclosure are the ones worth a call to IR.
        </div>
      )}
    </>
  );
}

export function PushCard({ it, onDone, onMute, onDig }: { it: any; onDone: () => void; onMute: () => void; onDig: () => void }) {
  const headline = it.kind === "move" ? null : it.results ? `${it.results.period} results: ${it.results.headline}` : it.oneliner && it.oneliner.length > 20 ? it.oneliner : it.title;
  return (
    <SwipeCard onDone={onDone} onMute={it.kind === "filing" ? onMute : undefined}>
      <Top it={it} />
      {headline && <h3>{headline}</h3>}
      {it.results ? <ResultsBody r={it.results} /> : it.people?.length ? <PeopleBody people={it.people} /> : it.kind === "move" ? <MoveBody it={it} /> : (
        headline !== it.title && <div className="sub">{it.title}</div>
      )}
      {!it.results && it.kind !== "move" && <Reasons it={it} />}
      <div className="card-actions">
        <button className="act primary" onClick={onDig}>Dig in <Icon.arrow /></button>
        {it.url && <a className="act" href={it.url} target="_blank" rel="noreferrer">Filing <Icon.ext /></a>}
        {it.also?.length ? <span className="act faint" title={it.also.map((a: any) => a.title).join("\n")}>+{it.also.length}</span> : null}
        <span className="spacer" />
        {it.kind === "filing" && <button className="act" onClick={onMute} aria-label="Mute similar"><Icon.mute /></button>}
        <button className="act" onClick={onDone} aria-label="Done"><Icon.check /> Done</button>
      </div>
    </SwipeCard>
  );
}

export function WorthRow({ it, onOpen }: { it: any; onOpen: () => void }) {
  const text = it.kind === "move" ? `${it.title}${it.explained_by?.length ? ` — ${it.explained_by[0].category_label.toLowerCase()}` : ""}` : it.oneliner && it.oneliner.length > 20 ? it.oneliner : it.title;
  return (
    <button className={`row ${it.muted ? "muted-row" : ""}`} onClick={onOpen}>
      <span className="tick">{it.symbol}</span>
      <span className="body">
        <span className="t">{text}</span>
        <span className="m"><span>{it.category_label}</span><span>·</span><span>{fmt.ago(it.ts)}</span>{it.reasons?.[0] && <><span>·</span><span>{it.reasons[0]}</span></>}</span>
      </span>
    </button>
  );
}

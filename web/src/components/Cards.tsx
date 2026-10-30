import { Delta, fmt, Icon, Spark, SwipeCard } from "./ui";

const SHORT: Record<string, string> = {
  TCS: "TCS", LT: "L&T", HDFCBANK: "HDFC Bank", BHARTIARTL: "Bharti Airtel", SUNPHARMA: "Sun Pharma",
  MARUTI: "Maruti Suzuki", BAJFINANCE: "Bajaj Finance", DMART: "DMart", HAL: "HAL", DEEPAKNTR: "Deepak Nitrite",
  RELIANCE: "Reliance", ETERNAL: "Eternal", KPITTECH: "KPIT", INDIGO: "IndiGo", PIDILITIND: "Pidilite",
};
export const shortName = (it: any) =>
  SHORT[it.symbol] || (it.company || it.symbol).replace(/\s+(India\s+)?(Ltd|Limited)\.?$/i, "").replace(/\s+Industries$/i, "");

const pct = (v: number) => `${Math.abs(v).toFixed(Math.abs(v) < 10 ? 1 : 0)}%`;

/** Write the item as a news headline, the way a desk editor would. */
export function headlineFor(it: any): string {
  const co = shortName(it);
  if (it.kind === "move") {
    const mv = it.move;
    const vol = mv.vol_mult && mv.vol_mult >= 1.8 ? ` on ${mv.vol_mult.toFixed(1)}x volume` : "";
    const verb = mv.ret >= 0 ? "rises" : "falls";
    if (Math.abs(mv.ret) < 2 && vol) return `Heavy trading in ${co}${vol.replace(" on", ",")}`;
    return `${co} ${verb} ${pct(mv.ret)}${vol}${it.unexplained ? ", no filing behind it" : ""}`;
  }
  const r = it.results;
  if (r) {
    const L = Object.fromEntries(r.lines.map((l: any) => [l.key, l]));
    const p = L.pat?.yoy_pct, rv = L.revenue?.yoy_pct;
    const bps = r.margins?.ebitda_margin != null && r.margins?.ebitda_margin_yoy != null ? Math.round((r.margins.ebitda_margin - r.margins.ebitda_margin_yoy) * 100) : null;
    let h = p != null ? `${co} profit ${p >= 0 ? "up" : "down"} ${pct(p)}` : `${co} ${r.period} results`;
    if (bps != null && Math.abs(bps) >= 50) h += `, margins ${bps > 0 ? "widen" : "narrow"} ${Math.abs(bps)} bps`;
    else if (rv != null) h += ` on ${pct(rv)} ${rv >= 0 ? "higher" : "lower"} revenue`;
    return h;
  }
  if (it.people?.length) {
    const inn = it.people.find((p: any) => p.direction === "in");
    const out = it.people.find((p: any) => p.direction === "out");
    const role = (inn?.role || out?.role || "a senior role").replace(/^Md/, "MD");
    if (inn && out) return `${co}: ${inn.name} takes over from ${out.name} as ${role}`;
    if (inn) return `${co} names ${inn.name} as ${role}`;
    if (out) return `${out.name} steps down as ${role} at ${co}`;
  }
  if (it.category === "fund_raise" && it.amount_cr && /qip|preferential|rights/i.test(`${it.summary} ${it.title}`)) {
    const how = /qip/i.test(`${it.summary} ${it.title}`) ? "a QIP" : /rights/i.test(`${it.summary}`) ? "a rights issue" : "a preferential issue";
    return `${co} raises ₹${fmt.n(it.amount_cr)} cr through ${how}`;
  }
  const s = it.oneliner && it.oneliner.length > 20 ? it.oneliner : it.title;
  return s.replace(/\.$/, "");
}

function Kicker({ it }: { it: any }) {
  const tone = it.category === "move" || it.category === "litigation" ? "down" : it.category === "results" || it.category === "management_change" ? "" : "";
  return (
    <div className="kicker">
      <span className="sym">{it.symbol}</span>
      <span className={`cat ${tone}`}>{it.category_label}</span>
      <span className="when">{fmt.ago(it.ts)} ago</span>
    </div>
  );
}

function ResultsBody({ r }: { r: any }) {
  return (
    <>
      <table className="rt">
        <thead>
          <tr><th>₹ cr, {r.period}</th><th>Value</th><th>QoQ</th><th>YoY</th></tr>
        </thead>
        <tbody>
          {r.lines.map((l: any) => (
            <tr key={l.key}>
              <td>{l.label}{l.note ? "*" : ""}</td>
              <td>{fmt.n(l.cur)}</td>
              <td><Delta v={l.qoq_pct} /></td>
              <td><Delta v={l.yoy_pct} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={`source-note ${r.verified ? "ok" : ""}`}>
        {r.verified ? "Read from the results filing and matched to reported totals." : "From the standardised quarterly table; the filing didn't parse cleanly."}
        {r.lines.some((l: any) => l.note) && <> * {r.lines.find((l: any) => l.note).note}.</>}
      </div>
    </>
  );
}

function PeopleBody({ people }: { people: any[] }) {
  return (
    <div>
      {people.map((p) => (
        <div className="person" key={p.name}>
          <div className={`dir ${p.direction}`}>{p.direction === "in" ? "In" : p.direction === "out" ? "Out" : "Named"}</div>
          <div>
            <span className="nm">{p.name}</span> <span className="rl">{p.role}</span>
            {p.structured?.headline && <div className="bio">{p.structured.headline}{p.structured.previous?.length ? `. Before: ${p.structured.previous.join("; ")}` : ""}</div>}
            {p.bio && !p.structured && <div className="bio">{p.bio.length > 300 ? p.bio.slice(0, 297) + "…" : p.bio}</div>}
            {p.bio && <div className="source-note">Source: {p.bio_source === "filing" ? "the appointment filing" : p.bio_source === "model" ? "language model background, not from a filing; verify before relying on it" : p.bio_source === "wikipedia" ? <a className="link" href={p.bio_url} target="_blank" rel="noreferrer">Wikipedia</a> : "an earlier filing"}</div>}
            {!p.bio && p.direction !== "out" && <div className="hint">{p.bio_hint ? `${p.bio_hint}; this one only refers to it.` : "The filing has no profile."}</div>}
            {p.direction !== "out" && <div style={{ marginTop: 3 }}><a className="act primary" href={p.linkedin} target="_blank" rel="noreferrer">Look up on LinkedIn <Icon.ext /></a></div>}
          </div>
        </div>
      ))}
    </div>
  );
}

function MoveBody({ it }: { it: any }) {
  const mv = it.move;
  return (
    <>
      <div className="standfirst">
        Closed at ₹{fmt.n(mv.close, mv.close < 100 ? 1 : 0)} on {new Date(mv.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
        {mv.vol_mult ? ` · volume ${mv.vol_mult.toFixed(1)}x the 20-day average` : ""}
        {mv.sigma != null ? ` · ${Math.abs(mv.sigma).toFixed(1)}σ for this stock` : ""}
      </div>
      <Spark data={mv.spark} w={320} h={42} fluid fill={false} color={mv.ret >= 0 ? "var(--up)" : "var(--down)"} />
      {it.explained_by?.length ? (
        <div className="standfirst">Probably driven by: {it.explained_by[0].title}</div>
      ) : it.score >= 65 ? (
        <div className="why">No filing explains this. Worth a call to investor relations.</div>
      ) : null}
    </>
  );
}

export function PushCard({ it, lead, onDone, onMute, onDig }: { it: any; lead?: boolean; onDone: () => void; onMute: () => void; onDig: () => void }) {
  const h = headlineFor(it);
  const plain = !it.results && !it.people?.length && it.kind !== "move";
  return (
    <SwipeCard className={lead ? "lead" : ""} onDone={onDone} onMute={it.kind === "filing" ? onMute : undefined}>
      <Kicker it={it} />
      <h3>{h}</h3>
      {it.results && <ResultsBody r={it.results} />}
      {it.guidance_check?.length > 0 && (
        <div className="gcheck">
          {it.guidance_check.map((g: any) => (
            <div key={g.metric}>
              <span className={g.status === "below" ? "down" : g.status === "above" ? "up" : ""}>
                {g.metric} {g.actual}% this quarter, {g.status === "within" ? "within" : g.status} the {g.target} guided for {g.period}
              </span>{" "}
              <a className="link" href={`${g.url}#page=${g.page}`} target="_blank" rel="noreferrer">{g.said_in} call, p.{g.page}</a>
            </div>
          ))}
        </div>
      )}
      {it.people?.length > 0 && <PeopleBody people={it.people} />}
      {it.kind === "move" && <MoveBody it={it} />}
      {plain && it.title && it.title !== h && <div className="standfirst">{it.title}</div>}
      {plain && it.reasons?.length > 0 && <div className="why">{it.reasons.join(" · ")}</div>}
      <div className="card-actions">
        <button className="act primary" onClick={onDig}>Research {it.symbol}</button>
        {it.url && <a className="act" href={it.url} target="_blank" rel="noreferrer">Filing <Icon.ext /></a>}
        <span className="spacer" />
        {it.kind === "filing" && <button className="act" onClick={onMute}>Mute</button>}
        <button className="act" onClick={onDone}>Mark read</button>
      </div>
    </SwipeCard>
  );
}

export function WorthRow({ it, onOpen }: { it: any; onOpen: () => void }) {
  return (
    <button className={`row ${it.muted ? "muted-row" : ""}`} onClick={onOpen}>
      <span className="sym">{it.symbol}</span>
      <span className="body">
        <span className="t">{headlineFor(it)}</span>
        <span className="m"><span>{it.category_label}</span><span>{fmt.ago(it.ts)} ago</span>{it.reasons?.[0] && <span>{it.reasons[0]}</span>}</span>
      </span>
    </button>
  );
}

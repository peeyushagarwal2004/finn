import { useEffect, useState } from "react";
import { api } from "../api";
import { Delta, fmt, Section, Spark } from "./ui";

type Sort = "move" | "sector" | "drawdown";
type View = "prices" | "quality";

const tone = (v: number | null | undefined, good: number, bad: number, higher = true) =>
  v == null ? "faint" : (higher ? v >= good : v <= good) ? "up" : (higher ? v < bad : v > bad) ? "down" : "";

export default function Holdings({ onDig }: { onDig: (s: string) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sort, setSort] = useState<Sort>("move");
  const [view, setView] = useState<View>("prices");
  useEffect(() => { api.holdings().then(setRows).catch(() => setRows([])); }, []);

  const sorted = (rows || []).slice().sort((a, b) =>
    sort === "move" ? Math.abs(b.eod?.ret ?? 0) - Math.abs(a.eod?.ret ?? 0)
      : sort === "drawdown" ? (a.eod?.from_hi ?? 0) - (b.eod?.from_hi ?? 0)
        : a.sector.localeCompare(b.sector));
  const up = (rows || []).filter((r) => (r.eod?.ret ?? 0) > 0).length;
  const asOf = rows?.find((r) => r.eod)?.eod.date;

  return (
    <div className="page">
      <h1 className="page-title">Portfolio</h1>
      <p className="lede">
        {view === "prices"
          ? <>{rows ? `${up} of ${rows.length} up` : ""}{asOf ? ` at the ${new Date(asOf).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} close` : ""}. Tap a company to research it.</>
          : <>The checks a long-term owner runs: does management do what it says, do profits turn into cash, are returns high, are the accounts clean, and is the promoter buying or selling.</>}
      </p>
      <div className="chips">
        <button className={`chip ${view === "prices" ? "on" : ""}`} onClick={() => setView("prices")}>Prices</button>
        <button className={`chip ${view === "quality" ? "on" : ""}`} onClick={() => setView("quality")}>Owner's checklist</button>
      </div>

      {view === "prices" && (
        <>
          <div className="chips" style={{ borderBottom: 0 }}>
            {([["move", "Biggest moves"], ["drawdown", "Furthest from high"], ["sector", "By sector"]] as [Sort, string][]).map(([k, l]) => (
              <button key={k} className={`chip sm ${sort === k ? "on" : ""}`} onClick={() => setSort(k)}>{l}</button>
            ))}
          </div>
          <Section title="Holdings" aside={`${rows?.length || 0} companies`}>
            {!rows ? <div className="skeleton" style={{ height: 400 }} /> : (
              <div className="rows">
                {sorted.map((r) => (
                  <button className="hold" key={r.symbol} onClick={() => onDig(r.symbol)}>
                    <div style={{ minWidth: 0 }}>
                      <div className="nm">{r.symbol} {r.eod?.vol_mult >= 2 && <span className="num" style={{ marginLeft: 6, fontWeight: 400, color: "var(--flag)", fontSize: 12 }}>{r.eod.vol_mult.toFixed(1)}x vol</span>}</div>
                      <div className="sec">{r.sector} · {fmt.cr(r.mcap)}</div>
                      {r.last_filing && <div className="sec">{r.last_filing.category_label}: {r.last_filing.title}</div>}
                    </div>
                    <Spark data={r.eod?.spark || []} w={66} h={26} fill={false} />
                    <div className="px num">
                      <span style={{ fontSize: 13 }}>{fmt.n(r.eod?.close, r.eod?.close < 100 ? 1 : 0)}</span>
                      <Delta v={r.eod?.ret} />
                      <span className="faint" style={{ fontSize: 11 }}>{r.eod?.from_hi != null ? `${r.eod.from_hi}% vs high` : ""}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Section>
        </>
      )}

      {view === "quality" && (
        <Section title="Owner's checklist" aside="from filings, calls and annual reports">
          {!rows ? <div className="skeleton" style={{ height: 400 }} /> : (
            <>
              <table className="qt">
                <thead>
                  <tr><th></th><th>Guidance<br />kept</th><th>Cash /<br />profit 5y</th><th>ROCE<br />(ROE*)</th><th>Audit</th><th>Promoter<br />stake</th></tr>
                </thead>
                <tbody>
                  {rows.slice().sort((a, b) => a.symbol.localeCompare(b.symbol)).map((r) => {
                    const q = r.quality;
                    const [k, n] = (q?.guidance || "").split("/").map(Number);
                    return (
                      <tr key={r.symbol} onClick={() => onDig(r.symbol)}>
                        <td>{r.symbol}</td>
                        <td className={q?.guidance ? tone(k / n, 0.7, 0.5) : "faint"}>{q?.guidance || "–"}</td>
                        <td className={q?.lender ? "faint" : tone(q?.cfo_pat, 0.9, 0.7)}>{q?.lender ? "n/a" : q?.cfo_pat != null ? `${q.cfo_pat.toFixed(2)}x` : "–"}</td>
                        <td className={tone(q?.roce, 18, 10)}>{q?.roce != null ? `${Math.round(q.roce)}%${q.lender ? "*" : ""}` : "–"}</td>
                        <td className={q?.audit === "clean" ? "up" : q?.audit ? "down" : "faint"}>{q?.audit === "clean" ? "Clean" : q?.audit || "–"}</td>
                        <td className={tone(q?.promoter_chg, 0.5, -1)}>{q?.promoter_chg != null ? `${q.promoter_chg > 0 ? "+" : ""}${q.promoter_chg}` : "–"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="faint" style={{ fontSize: 11.5, marginTop: 8, lineHeight: 1.5 }}>
                Guidance kept: checkable targets from the last four calls that were met. Cash/profit: operating cash flow divided by reported profit over five years; below 0.7x means profits aren't turning into cash. Promoter stake: change in percentage points over the last six quarters. *ROE for lenders. Tap a row for the full research.
              </div>
            </>
          )}
        </Section>
      )}
    </div>
  );
}

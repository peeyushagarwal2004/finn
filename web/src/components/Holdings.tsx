import { useEffect, useState } from "react";
import { api } from "../api";
import { Delta, fmt, Section, Spark } from "./ui";

type Sort = "move" | "sector" | "drawdown";

export default function Holdings({ onDig }: { onDig: (s: string) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sort, setSort] = useState<Sort>("move");
  useEffect(() => { api.holdings().then(setRows).catch(() => setRows([])); }, []);

  const sorted = (rows || []).slice().sort((a, b) =>
    sort === "move" ? Math.abs(b.eod?.ret ?? 0) - Math.abs(a.eod?.ret ?? 0)
      : sort === "drawdown" ? (a.eod?.from_hi ?? 0) - (b.eod?.from_hi ?? 0)
        : a.sector.localeCompare(b.sector));
  const up = (rows || []).filter((r) => (r.eod?.ret ?? 0) > 0).length;
  const asOf = rows?.find((r) => r.eod)?.eod.date;

  return (
    <div className="page">
      <h1 className="headline" style={{ marginTop: 12 }}>Your book, <em>{rows ? `${up} of ${rows.length}` : "…"}</em> up.</h1>
      <div className="muted" style={{ fontSize: 13, margin: "-6px 2px 8px" }}>End-of-day{asOf ? ` · ${new Date(asOf).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} close` : ""}. Tap a name to research it.</div>
      <div className="chips">
        {([["move", "Biggest movers"], ["drawdown", "Furthest from high"], ["sector", "By sector"]] as [Sort, string][]).map(([k, l]) => (
          <button key={k} className={`chip ${sort === k ? "on" : ""}`} onClick={() => setSort(k)}>{l}</button>
        ))}
      </div>
      <Section title="Holdings" aside={`${rows?.length || 0} names`}>
        {!rows ? <div className="skeleton" style={{ height: 400 }} /> : (
          <div className="rows">
            {sorted.map((r) => (
              <button className="hold" key={r.symbol} onClick={() => onDig(r.symbol)}>
                <div style={{ minWidth: 0 }}>
                  <div className="nm">{r.symbol} {r.eod?.vol_mult >= 2 && <span className="pill accent" style={{ marginLeft: 4 }}>{r.eod.vol_mult.toFixed(1)}× vol</span>}</div>
                  <div className="sec">{r.sector} · {fmt.cr(r.mcap)}</div>
                  {r.last_filing && <div className="sec" style={{ color: "var(--muted)" }}>{r.last_filing.category_label}: {r.last_filing.title}</div>}
                </div>
                <Spark data={r.eod?.spark || []} w={72} h={28} />
                <div className="px num">
                  <b>₹{fmt.n(r.eod?.close, r.eod?.close < 100 ? 1 : 0)}</b>
                  <Delta v={r.eod?.ret} />
                  <div className="faint" style={{ fontSize: 11 }}>{r.eod?.from_hi != null ? `${r.eod.from_hi}% from high` : ""}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

import { ReactNode, useRef, useState } from "react";

export const fmt = {
  cr: (v?: number | null) => {
    if (v === null || v === undefined || isNaN(v)) return "—";
    const a = Math.abs(v);
    if (a >= 100000) return `₹${(v / 100000).toFixed(a >= 1000000 ? 1 : 2)}L cr`;
    return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: a < 100 ? 1 : 0 })} cr`;
  },
  n: (v?: number | null, d = 0) => (v === null || v === undefined || isNaN(v) ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v?: number | null, d = 1, sign = true) => (v === null || v === undefined || isNaN(v) ? "—" : `${sign && v > 0 ? "+" : ""}${v.toFixed(d)}%`),
  ago: (ts: number) => {
    const s = Date.now() / 1000 - ts;
    if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`;
    if (s < 86400) return `${Math.round(s / 3600)}h`;
    if (s < 86400 * 7) return `${Math.round(s / 86400)}d`;
    return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  },
};

export function Delta({ v, d = 1, suffix = "" }: { v?: number | null; d?: number; suffix?: string }) {
  if (v === null || v === undefined || isNaN(v)) return <span className="faint">—</span>;
  return (
    <span className={`delta num ${v > 0 ? "up" : v < 0 ? "down" : "muted"}`}>
      {v > 0 ? "▲" : v < 0 ? "▼" : ""} {Math.abs(v).toFixed(d)}
      {suffix || "%"}
    </span>
  );
}

export function Spark({ data, w = 72, h = 26, color, fill = true, mark, fluid }: { data: (number | null)[]; w?: number; h?: number; color?: string; fill?: boolean; mark?: number; fluid?: boolean }) {
  const pts = data.map((v, i) => [i, v] as const).filter(([, v]) => v !== null && v !== undefined) as [number, number][];
  if (pts.length < 2) return <svg width={w} height={h} />;
  const ys = pts.map((p) => p[1]);
  const min = Math.min(...ys), max = Math.max(...ys), span = max - min || 1;
  const X = (i: number) => (i / (data.length - 1)) * (w - 2) + 1;
  const Y = (v: number) => h - 2 - ((v - min) / span) * (h - 4);
  const d = pts.map(([i, v], k) => `${k ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const c = color || (ys[ys.length - 1] >= ys[0] ? "var(--up)" : "var(--down)");
  return (
    <svg width={fluid ? "100%" : w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio={fluid ? "none" : undefined} aria-hidden style={fluid ? { display: "block" } : undefined}>
      {fill && <path d={`${d} L${X(pts[pts.length - 1][0])},${h} L${X(pts[0][0])},${h} Z`} fill={c} opacity={0.1} />}
      <path d={d} fill="none" stroke={c} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      {mark !== undefined && data[mark] != null && <circle cx={X(mark)} cy={Y(data[mark] as number)} r={2.6} fill={c} />}
    </svg>
  );
}

/** Bars (e.g. annual revenue) with an optional line overlay (e.g. margin %). */
export function BarLine({ labels, bars, line, h = 150, barColor = "var(--line-2)", lineColor = "var(--accent)", fmtBar, fmtLine }: {
  labels: string[]; bars: (number | null)[]; line?: (number | null)[]; h?: number; barColor?: string; lineColor?: string;
  fmtBar?: (v: number) => string; fmtLine?: (v: number) => string;
}) {
  const W = 340, top = 18, bottom = 20, ih = h - top - bottom;
  const n = labels.length;
  const bw = (W / n) * 0.62;
  const vals = bars.filter((v) => v != null) as number[];
  const bmax = Math.max(...vals, 0), bmin = Math.min(...vals, 0);
  const span = bmax - bmin || 1;
  const zero = top + (bmax / span) * ih;
  const lv = (line || []).filter((v) => v != null) as number[];
  const lmin = Math.min(...lv), lmax = Math.max(...lv), lspan = lmax - lmin || 1;
  const cx = (i: number) => (i + 0.5) * (W / n);
  const ly = (v: number) => top + 6 + (1 - (v - lmin) / lspan) * (ih * 0.55);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${h}`} role="img">
      <line x1={0} x2={W} y1={zero} y2={zero} stroke="var(--line)" />
      {bars.map((v, i) =>
        v == null ? null : (
          <g key={i}>
            <rect x={cx(i) - bw / 2} width={bw} y={v >= 0 ? zero - (v / span) * ih : zero} height={Math.max(1, (Math.abs(v) / span) * ih)} rx={3}
              fill={i === n - 1 ? "var(--text-2)" : barColor} opacity={v < 0 ? 0.6 : 1} />
            {(i === n - 1 || i === 0) && fmtBar && (
              <text x={cx(i)} y={(v >= 0 ? zero - (v / span) * ih : zero) - 4} textAnchor="middle" fontSize={9.5} fill="var(--muted)" className="num">{fmtBar(v)}</text>
            )}
          </g>
        ),
      )}
      {line && lv.length > 1 && (
        <>
          <path d={line.map((v, i) => (v == null ? "" : `${i && line[i - 1] != null ? "L" : "M"}${cx(i)},${ly(v)}`)).join(" ")} fill="none" stroke={lineColor} strokeWidth={2} />
          {line.map((v, i) => (v == null ? null : <circle key={i} cx={cx(i)} cy={ly(v)} r={2.5} fill={lineColor} />))}
          {fmtLine && line[line.length - 1] != null && (
            <text x={cx(n - 1)} y={ly(line[line.length - 1] as number) - 7} textAnchor="end" fontSize={10} fill={lineColor} className="num" fontWeight={600}>{fmtLine(line[line.length - 1] as number)}</text>
          )}
        </>
      )}
      {labels.map((l, i) => (n <= 8 || i % 2 === n % 2 || i === n - 1) && (
        <text key={i} x={cx(i)} y={h - 5} textAnchor="middle" fontSize={9.5} fill="var(--faint)">{l.replace(/^Mar 20(\d\d)$/, "FY$1").replace(/^(\w{3}) 20(\d\d)$/, "$1 $2")}</text>
      ))}
    </svg>
  );
}

export function Ring({ value, size = 64, label }: { value: number | null; size?: number; label?: string }) {
  const r = size / 2 - 5, c = 2 * Math.PI * r;
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  const col = value == null ? "var(--faint)" : v >= 70 ? "var(--up)" : v >= 45 ? "var(--accent)" : "var(--down)";
  return (
    <svg className="ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={5} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={5} strokeLinecap="round"
        strokeDasharray={`${(v / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="52%" textAnchor="middle" dominantBaseline="middle" fontSize={size * 0.28} fill="var(--text)" fontFamily="var(--serif)">
        {value == null ? "—" : label ?? Math.round(v)}
      </text>
    </svg>
  );
}

/** A card the investor can swipe: right = done, left = mute this kind of filing for this company. */
export function SwipeCard({ children, onDone, onMute, className = "" }: { children: ReactNode; onDone: () => void; onMute?: () => void; className?: string }) {
  const [dx, setDx] = useState(0);
  const [leaving, setLeaving] = useState<"" | "right" | "left">("");
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const locked = useRef<"x" | "y" | null>(null);
  const end = () => {
    if (dx > 90) { setLeaving("right"); setTimeout(onDone, 220); }
    else if (dx < -90 && onMute) { setLeaving("left"); setTimeout(onMute, 220); }
    else setDx(0);
    start.current = null; locked.current = null;
  };
  return (
    <div
      className={`card ${className} ${start.current ? "dragging" : ""} ${leaving ? "leaving-" + leaving : ""}`}
      style={!leaving ? { transform: dx ? `translateX(${dx}px) rotate(${dx / 40}deg)` : undefined } : undefined}
      onPointerDown={(e) => { if ((e.target as HTMLElement).closest("a,button,input")) return; start.current = { x: e.clientX, y: e.clientY, id: e.pointerId }; }}
      onPointerMove={(e) => {
        if (!start.current) return;
        const mx = e.clientX - start.current.x, my = e.clientY - start.current.y;
        if (!locked.current && (Math.abs(mx) > 8 || Math.abs(my) > 8)) {
          locked.current = Math.abs(mx) > Math.abs(my) ? "x" : "y";
          if (locked.current === "x") (e.currentTarget as HTMLElement).setPointerCapture(start.current.id);
        }
        if (locked.current === "x") setDx(onMute ? mx : Math.max(0, mx));
      }}
      onPointerUp={end}
      onPointerCancel={() => { setDx(0); start.current = null; locked.current = null; }}
    >
      <div className="swipe-hint done" style={{ opacity: Math.min(1, Math.max(0, dx) / 90) }}>✓ Done</div>
      <div className="swipe-hint mute" style={{ opacity: Math.min(1, Math.max(0, -dx) / 90) }}>Mute similar</div>
      {children}
    </div>
  );
}

const P = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export const Icon = {
  brief: () => (<svg {...P}><path d="M4 5h16M4 10h16M4 15h10M4 20h6" /></svg>),
  bell: () => (<svg {...P}><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>),
  search: () => (<svg {...P}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></svg>),
  book: () => (<svg {...P}><path d="M4 19V5M9 19v-7M14 19V9M19 19v-11" /></svg>),
  play: () => (<svg {...P}><path d="M7 5v14l11-7z" fill="currentColor" /></svg>),
  stop: () => (<svg {...P}><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" /></svg>),
  mic: () => (<svg {...P} width={16} height={16}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>),
  sun: () => (<svg {...P}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" /></svg>),
  moon: () => (<svg {...P}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" /></svg>),
  ext: () => (<svg {...P} width={13} height={13}><path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5" /></svg>),
  check: () => (<svg {...P} width={15} height={15}><path d="m5 12 5 5 9-10" /></svg>),
  mute: () => (<svg {...P} width={15} height={15}><path d="M4 9h4l5-4v14l-5-4H4zM17 9l4 6M21 9l-4 6" /></svg>),
  arrow: () => (<svg {...P} width={15} height={15}><path d="M5 12h14M13 6l6 6-6 6" /></svg>),
  refresh: () => (<svg {...P}><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" /></svg>),
};

export function Section({ title, aside, children, id }: { title: string; aside?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section id={id}>
      <div className="section-h"><h2>{title}</h2>{aside && <span className="aside">{aside}</span>}</div>
      {children}
    </section>
  );
}

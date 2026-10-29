export type Rules = {
  price_pct: number;
  vol_mult: number;
  sigma: number;
  use_sigma: boolean;
  categories: string[];
  min_score: number;
};

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

const q = (o: Record<string, any>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v)}`)
    .join("&");

export const api = {
  meta: () => j<any>("/api/meta"),
  digest: (p: { hours?: number; since?: number; rules?: Rules; muted?: string[] }) =>
    j<any>(`/api/digest?${q({ hours: p.hours, since: p.since, rules: p.rules, muted: (p.muted || []).join(",") })}`),
  brief: (p: { hours?: number; since?: number; rules?: Rules; muted?: string[] }) =>
    j<{ script: string }>(`/api/brief?${q({ hours: p.hours, since: p.since, rules: p.rules, muted: (p.muted || []).join(",") })}`),
  holdings: () => j<any[]>("/api/holdings"),
  backtest: (rules: Rules, sessions = 90) =>
    j<any>("/api/alerts/backtest", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rules, sessions }) }),
  search: (s: string) => j<{ symbol: string; name: string }[]>(`/api/search?q=${encodeURIComponent(s)}`),
  research: (sym: string, force = false) => j<any>(`/api/research/${encodeURIComponent(sym)}${force ? "?force=true" : ""}`, { method: "POST" }),
  researchGet: (sym: string) => j<any>(`/api/research/${encodeURIComponent(sym)}`),
  ask: (symbol: string, question: string) =>
    j<any>("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ symbol, q: question }) }),
  refresh: () => j<any>("/api/refresh", { method: "POST" }),
};

/* ---------- per-device preferences (rules, mutes, triage state) ---------- */
const read = <T,>(k: string, d: T): T => {
  try {
    const v = localStorage.getItem("finn:" + k);
    return v ? (JSON.parse(v) as T) : d;
  } catch {
    return d;
  }
};
const write = (k: string, v: unknown) => {
  try {
    localStorage.setItem("finn:" + k, JSON.stringify(v));
  } catch {
    /* private mode: preferences just won't persist */
  }
};
export const prefs = { read, write };

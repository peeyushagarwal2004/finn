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
  stats: () => j<any>("/api/stats"),
  pushKey: () => j<{ publicKey: string | null }>("/api/push/key"),
  pushSubscribe: (subscription: any, rules: Rules, muted: string[]) =>
    j<any>("/api/push/subscribe", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ subscription, rules, muted }) }),
};

/** Subscribe this device to background alerts, or refresh its rules if already subscribed.
 *  Returns "on", "off", "unsupported", "denied" or "not-configured". */
export async function syncPush(rules: Rules, muted: string[], ask = false): Promise<string> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || typeof Notification === "undefined") return "unsupported";
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission !== "granted") {
    if (!ask) return "off";
    if ((await Notification.requestPermission()) !== "granted") return "denied";
  }
  const { publicKey } = await api.pushKey();
  if (!publicKey) return "not-configured";
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    const raw = atob(publicKey.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (publicKey.length % 4)) % 4));
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)) });
  }
  // sent every time the app opens: the free server's disk is wiped on restart, so this heals it
  await api.pushSubscribe(sub.toJSON(), rules, muted);
  return "on";
}

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

// FINN service worker: keeps the app shell on the phone so it opens instantly, and shows alerts
// pushed by the server even when FINN isn't open. API data is cached by the app itself.
const SHELL = "finn-shell-v2";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/icon.svg", "/manifest.webmanifest"])).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) return; // live data: the app shows its saved copy while this loads

  // hashed build files and fonts never change: serve from the phone, fetch only once
  if (url.pathname.startsWith("/assets/") || url.host.includes("fonts.g")) {
    e.respondWith(caches.open(SHELL).then(async (c) => {
      const hit = await c.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok || res.type === "opaque") c.put(req, res.clone());
      return res;
    }));
    return;
  }

  // the page itself: show the saved copy straight away and update it in the background
  if (req.mode === "navigate") {
    e.respondWith(caches.open(SHELL).then(async (c) => {
      const saved = await c.match("/");
      const network = fetch(req).then((res) => { if (res.ok) c.put("/", res.clone()); return res; });
      return saved || network;
    }));
  }
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { title: "FINN", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "FINN", {
    body: d.body || "", tag: d.tag, icon: "/icon.svg", badge: "/icon.svg", data: { url: d.url || "/#brief" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/#brief";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
    const c = cs.find((x) => "focus" in x);
    if (c) { c.navigate(url); return c.focus(); }
    return self.clients.openWindow(url);
  }));
});

// invitio service worker — offline app shell + cache-first static assets.
// The "-v0" below is a placeholder: the backend rewrites it to the build id
// (BUILD_VERSION / process start time) when serving /sw.js, so each deploy gets a
// fresh CACHE name automatically — no manual bumping needed.
const CACHE = "invitio-v0";
const API_CACHE = "invitio-api-v1";
const SHELL = [
  "/",
  "/static/css/style.css",
  "/static/js/themes.js",
  "/static/js/scheme.js",
  "/static/js/app.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => {})
  );
});

self.addEventListener("activate", (event) => {
  const keep = [CACHE, API_CACHE];
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // API reads: network-first so data is always live; cache the latest so the app
  // can still render last-known data offline. (Writes are POST/PUT/DELETE — not
  // GET — so they never hit this and always require the network.)
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(API_CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // App-shell navigations: network-first so a freshly published page (and any
  // edited invite) always wins; fall back to the cached shell only when offline.
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/")));
    return;
  }

  // Versioned static assets (?v= build query): exact-match cache-first with a
  // background refresh, so a same-version asset is instant but a new ?v= after a
  // deploy misses and fetches the fresh bytes. Falls back to any cached copy
  // (ignoreSearch) when the network is gone.
  event.respondWith(
    caches.match(req).then((hit) => {
      if (hit) {
        fetch(req).then((res) => {
          if (res && res.ok) caches.open(CACHE).then((c) => c.put(req, res.clone()));
        }).catch(() => {});
        return hit;
      }
      return fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }));
    })
  );
});

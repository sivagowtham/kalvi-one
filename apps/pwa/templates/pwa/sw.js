// KalviOne service worker (decision D33).
// Pages hold personal data, so they are never cached: every page comes from the network.
// Only the offline page and the app icons are kept, so the app can say "no network"
// instead of showing the browser's error.
const CACHE = "{{ cache_version }}";
const OFFLINE_URL = "/offline/";
const PRECACHE = [OFFLINE_URL, "/app/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (url.pathname.startsWith("/app/icons/")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
  }
});

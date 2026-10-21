/* Минимальный service worker: установка PWA. Страницы НЕ кэшируем — только статику манифеста,
   иначе браузер навсегда держит старый HTML и подмешивает его к новым сборкам. */
const CACHE = "learnos-shell-v3";
const SHELL = ["/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api")) return; // API и SSE — мимо кэша
  // статику SHELL берём из кэша, всё остальное (страницы, чанки) — из сети
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request)),
  );
});

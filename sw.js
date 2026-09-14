/* Sideline service worker.
   Bump CACHE when you upload a new index.html — that's what tells installed
   phones to pick the new version up. */
const CACHE = "sideline-v4";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-192-maskable.png",
  "./icon-512-maskable.png",
  "./apple-touch-icon.png"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      /* one bad URL shouldn't sink the whole install, so add them individually */
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", e => { if(e.data === "skipWaiting") self.skipWaiting(); });

self.addEventListener("fetch", e => {
  const req = e.request;
  if(req.method !== "GET") return;
  const url = new URL(req.url);
  if(url.origin !== self.location.origin) return;

  /* The page itself goes network-first so a coach who has signal picks up new
     versions, and cache-second so the one who doesn't still gets a working app. */
  if(req.mode === "navigate" || url.pathname.endsWith("index.html") || url.pathname.endsWith("/")){
    e.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put("./index.html", copy)).catch(()=>{});
          return res;
        })
        .catch(() => caches.match("./index.html").then(r => r || caches.match("./")))
    );
    return;
  }

  /* Icons and the manifest never change within a version — serve them instantly. */
  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(res => {
      if(res && res.status === 200){
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(()=>{});
      }
      return res;
    }).catch(() => hit))
  );
});

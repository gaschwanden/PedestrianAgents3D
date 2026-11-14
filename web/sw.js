/* Offline shell for the field client.

   - The app shell is fetched from the network when there is one, so an update
     on the laptop reaches the phone, and from the cache otherwise.
   - Scene packs and the Python runtime are large and versioned by URL
     (?v=<build>), so they are served cache-first and never re-downloaded.
   - Google / Esri / OSM tiles stay on the network and are never stored. */
const CACHE = "pedsim-field-v18";
const SHELL = [
  "./",
  "./index.html",
  "./styles.css?v=18",
  "./app.js?v=18",
  "./worker.js?v=18",
  "./strings.js?v=18",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./vendor/maplibre-gl.js",
  "./vendor/maplibre-gl.css",
  "./packs/goebekli/index.json",
];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return cache.addAll(SHELL);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (key) { return key !== CACHE; }).map(function (key) {
      return caches.delete(key);
    }));
  }).then(function () { return self.clients.claim(); }));
});

function store(request, response) {
  if (response.ok && request.method === "GET") {
    const copy = response.clone();
    caches.open(CACHE).then(function (cache) { cache.put(request, copy); });
  }
  return response;
}

self.addEventListener("fetch", function (event) {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.method !== "GET") return;
  if (url.pathname.indexOf("/tiles/") >= 0 || url.pathname.indexOf("/api/") >= 0) return;
  const heavy = /\/vendor\/|\/packs\/[^/]+\/[^/]+\.(bin|jpg)$|\/packs\/[^/]+\/(cluster|village-[^/]+)\.json$/
    .test(url.pathname);
  if (heavy) {
    event.respondWith(caches.match(event.request).then(function (hit) {
      return hit || fetch(event.request).then(function (response) {
        return store(event.request, response);
      });
    }));
    return;
  }
  event.respondWith(fetch(event.request).then(function (response) {
    return store(event.request, response);
  }).catch(function () {
    return caches.match(event.request, { ignoreSearch: true });
  }));
});

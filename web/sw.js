/* Caches the app shell and packed scenes. Google / Esri / OSM tiles stay on
   the network and are never written into this cache. */
const CACHE = "pedsim-field-v13";
const SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./worker.js",
  "./strings.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./vendor/maplibre-gl.js",
  "./vendor/maplibre-gl.css",
  "./packs/goebekli/scene.json",
  "./packs/goebekli/cluster.json",
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

self.addEventListener("fetch", function (event) {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/tiles/") === 0) return;
  if (/google|gstatic|ggpht|googleapis|openstreetmap|opentopomap|arcgisonline/i.test(url.hostname + url.pathname)) {
    return;
  }
  event.respondWith(fetch(event.request).then(function (response) {
    if (response.ok && event.request.method === "GET") {
      const copy = response.clone();
      caches.open(CACHE).then(function (cache) { cache.put(event.request, copy); });
    }
    return response;
  }).catch(function () {
    return caches.match(event.request);
  }));
});

var CACHE = 'hegel-v1';
var SHELL = [
  '/',
  '/index.html',
  '/text.html',
  '/search.html',
  '/feedback.html',
  '/404.html',
  '/assets/style.css',
  '/assets/edition-data.js',
  '/assets/favicon.svg',
  '/manifest.json'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(cache) { return cache.addAll(SHELL); })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.match(/\.(js|css|svg|json)$/)) {
    e.respondWith(
      caches.open(CACHE).then(function(cache) {
        return cache.match(e.request).then(function(cached) {
          var fetched = fetch(e.request).then(function(resp) {
            if (resp.ok) cache.put(e.request, resp.clone());
            return resp;
          }).catch(function() { return cached; });
          return cached || fetched;
        });
      })
    );
    return;
  }

  e.respondWith(
    fetch(e.request).then(function(resp) {
      if (resp.ok && e.request.method === 'GET') {
        var clone = resp.clone();
        caches.open(CACHE).then(function(cache) { cache.put(e.request, clone); });
      }
      return resp;
    }).catch(function() {
      return caches.match(e.request).then(function(cached) {
        return cached || caches.match('/404.html');
      });
    })
  );
});

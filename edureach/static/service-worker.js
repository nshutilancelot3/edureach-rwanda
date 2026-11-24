// Simple, reliable Service Worker for offline support
const CACHE = 'edureach-cache-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
  caches.open(CACHE).then(cache => {
    console.log('[SW] Caching assets...');
    cache.addAll([
      '/',
      '/login',
      '/static/style.css',
    ]).catch(() => {}); // OK if some assets don't exist yet
  });
});

self.addEventListener('activate', () => {
  self.clients.claim();
  caches.keys().then(names => {
    names.forEach(name => {
      if (name !== CACHE) caches.delete(name);
    });
  });
});

self.addEventListener('fetch', (event) => {
  // GET requests only
  if (event.request.method !== 'GET') return;

  event.respondWith(
    // Try network first
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        if (response.ok) {
          caches.open(CACHE).then(cache => {
            cache.put(event.request, response.clone());
          });
        }
        return response;
      })
      .catch(() => {
        // Network failed, try cache
        return caches.match(event.request)
          .then(cached => cached || new Response('Offline', { status: 503 }));
      })
  );
});

// Service Worker for complete offline support
const CACHE_NAME = 'edureach-v2';

// Install - immediately become active
self.addEventListener('install', () => {
  self.skipWaiting();
});

// Activate - take control of all pages
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Fetch - network first, cache fallback
self.addEventListener('fetch', (event) => {
  // Only handle GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    // Try network first
    fetch(event.request)
      .then((response) => {
        // Cache successful responses
        if (response && response.status === 200) {
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, response.clone());
          });
        }
        return response;
      })
      .catch(() => {
        // Network failed - try cache
        return caches.match(event.request).then((cached) => {
          if (cached) {
            return cached;
          }
          // If not in cache and offline, return a generic offline page
          if (event.request.destination === 'document') {
            return new Response(
              '<h1>Offline</h1><p>This page is not cached. Load it while online to use offline.</p>',
              { status: 503, statusText: 'Service Unavailable', headers: { 'Content-Type': 'text/html' } }
            );
          }
          return new Response('Offline', { status: 503 });
        });
      })
  );
});

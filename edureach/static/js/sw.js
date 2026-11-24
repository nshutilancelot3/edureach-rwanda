/* EduReach — Service Worker.
 *
 * Strategy per request type:
 *   navigations  network-first, then exact cache hit, then the offline shell.
 *                The shell rebuilds any student/teacher screen from IndexedDB,
 *                so a lesson the device has never opened still works offline.
 *   /static/*    cache-first with background refresh (app code and styles).
 *   /files/*     cache-first (lesson attachments; large and immutable).
 *   /api/*       network-only — the page's JS decides what to do on failure.
 */

var VERSION = 'v4';
var SHELL_CACHE = 'edureach-shell-' + VERSION;
var PAGE_CACHE = 'edureach-pages-' + VERSION;
var FILE_CACHE = 'edureach-files-' + VERSION;

var SHELL_URL = '/offline-shell';

var PRECACHE = [
  SHELL_URL,
  '/static/style.css',
  '/static/js/db.js',
  '/static/js/sync.js',
  '/static/js/shell.js',
  '/static/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function (cache) {
      // addAll is atomic: one 404 would discard the whole shell, so fetch each
      // entry on its own and keep whatever succeeds.
      return Promise.all(PRECACHE.map(function (url) {
        return fetch(url, { credentials: 'same-origin', cache: 'reload' })
          .then(function (res) { if (res.ok) return cache.put(url, res); })
          .catch(function () { /* retried on next activation */ });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  var keep = [SHELL_CACHE, PAGE_CACHE, FILE_CACHE];
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (name) {
        if (name.indexOf('edureach-') === 0 && keep.indexOf(name) === -1) {
          return caches.delete(name);
        }
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

function isNavigation(request) {
  if (request.mode === 'navigate') return true;
  var accept = request.headers.get('accept') || '';
  return accept.indexOf('text/html') !== -1;
}

/* Pages: try the hub, fall back to this exact page, then to the shell. */
function handleNavigation(request) {
  return fetch(request)
    .then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        caches.open(PAGE_CACHE).then(function (c) { c.put(request, copy); });
      }
      return response;
    })
    .catch(function () {
      return caches.match(request, { ignoreSearch: false }).then(function (hit) {
        if (hit) return hit;
        return caches.match(SHELL_URL).then(function (shell) {
          if (shell) return shell;
          return new Response(
            '<!doctype html><meta charset="utf-8"><title>Offline</title>' +
            '<p style="font:17px system-ui;padding:24px">EduReach has not finished ' +
            'installing on this device yet. Connect once, then try again.</p>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        });
      });
    });
}

/* App code and styles: serve instantly, refresh quietly in the background. */
function handleStatic(request) {
  return caches.match(request).then(function (hit) {
    var network = fetch(request).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        caches.open(SHELL_CACHE).then(function (c) { c.put(request, copy); });
      }
      return response;
    }).catch(function () { return hit; });
    return hit || network;
  });
}

/* Lesson attachments: once fetched, keep them. */
function handleFile(request) {
  return caches.match(request).then(function (hit) {
    if (hit) return hit;
    return fetch(request).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        caches.open(FILE_CACHE).then(function (c) { c.put(request, copy); });
      }
      return response;
    }).catch(function () {
      return new Response('', { status: 504, statusText: 'Attachment not available offline' });
    });
  });
}

self.addEventListener('fetch', function (event) {
  var request = event.request;

  if (request.method !== 'GET') return;                 // POSTs are queued by the page
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;      // nothing external to begin with
  if (url.pathname.indexOf('/api/') === 0) return;      // network-only; JS handles failure

  if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(handleStatic(request));
  } else if (url.pathname.indexOf('/files/') === 0) {
    event.respondWith(handleFile(request));
  } else if (isNavigation(request)) {
    event.respondWith(handleNavigation(request));
  }
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.action === 'skipWaiting') self.skipWaiting();
});

/* EduReach — connectivity, bootstrap and synchronisation.
 *
 * Runs on every signed-in page. Three jobs:
 *   1. Register the service worker so the shell survives a cold start.
 *   2. Keep a truthful online/offline reading and show it in the header.
 *   3. Mirror the hub into IndexedDB, and replay the outbox once reachable.
 *
 * A queued write is removed only after the hub confirms it. A failed sync
 * leaves local data untouched and retries later.
 */
(function (global) {
  'use strict';

  var PING = '/api/ping';
  var BOOTSTRAP = '/api/bootstrap';
  var SYNC = '/api/sync';
  var POLL_MS = 20000;

  var state = {
    online: null,        // null = not yet determined
    syncing: false,
    pending: 0,
    lastSync: null
  };

  /* ------------------------------------------------------------------ net */

  function withTimeout(promise, ms) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { reject(new Error('timeout')); }, ms);
      promise.then(
        function (v) { clearTimeout(timer); resolve(v); },
        function (e) { clearTimeout(timer); reject(e); }
      );
    });
  }

  /* navigator.onLine only proves a link exists, not that the hub answers —
   * a school Wi-Fi with no uplink reports "online". So we ask the hub. */
  function probe() {
    if (global.navigator && navigator.onLine === false) return Promise.resolve(false);
    return withTimeout(
      fetch(PING, { method: 'GET', cache: 'no-store', credentials: 'same-origin' }),
      4000
    ).then(function (res) { return res.ok; }).catch(function () { return false; });
  }

  function setOnline(value) {
    if (state.online === value) return Promise.resolve(value);
    state.online = value;
    render();
    emit('edureach:netchange', { online: value });
    if (value) return cycle();
    return Promise.resolve(value);
  }

  function emit(name, detail) {
    try {
      global.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
    } catch (e) { /* older browsers */ }
  }

  /* ------------------------------------------------------------ indicator */

  function indicator() {
    var el = document.getElementById('net-indicator');
    if (el) return el;
    var host = document.querySelector('.top nav');
    if (!host) return null;
    el = document.createElement('span');
    el.id = 'net-indicator';
    el.className = 'netpill';
    el.innerHTML = '<span class="netdot"></span><span class="nettext"></span><span class="netbadge"></span>';
    host.insertBefore(el, host.firstChild);
    return el;
  }

  function render() {
    var el = indicator();
    if (!el) return;
    var mode = state.online === false ? 'offline' : (state.syncing ? 'syncing' : 'online');
    var label = mode === 'offline' ? 'Offline' : (mode === 'syncing' ? 'Syncing…' : 'Online');

    el.setAttribute('data-state', mode);
    el.querySelector('.nettext').textContent = label;

    var badge = el.querySelector('.netbadge');
    if (state.pending > 0) {
      badge.textContent = state.pending;
      badge.hidden = false;
      el.title = state.pending + ' change(s) waiting to reach the hub';
    } else {
      badge.hidden = true;
      el.title = mode === 'offline'
        ? 'Working offline — your work is saved on this device'
        : 'Connected to the hub. Everything is saved.';
    }
    document.documentElement.setAttribute('data-net', mode);
  }

  function refreshPending() {
    return global.EduDB.pendingCount().then(function (n) {
      state.pending = n;
      render();
      return n;
    }).catch(function () { return 0; });
  }

  /* ------------------------------------------------------------ bootstrap */

  /** Pull the hub's current state into IndexedDB. */
  function bootstrap() {
    return fetch(BOOTSTRAP, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (res) {
        if (res.status === 401) throw new Error('signed out');
        if (!res.ok) throw new Error('bootstrap failed: ' + res.status);
        return res.json();
      })
      .then(function (data) {
        var D = global.EduDB;
        // Locally-created results carry negative ids; keep them so a refresh
        // before sync never loses a student's submitted quiz.
        return D.all('results').then(function (existing) {
          var localOnly = existing.filter(function (r) { return r.id < 0; });
          var merged = data.results.concat(localOnly.filter(function (l) {
            return !data.results.some(function (s) { return s.client_uuid && s.client_uuid === l.client_uuid; });
          }));
          return Promise.all([
            D.replaceAll('lessons', data.lessons),
            D.replaceAll('quizzes', data.quizzes),
            D.replaceAll('questions', data.questions),
            D.replaceAll('results', merged),
            D.setMeta('user', data.user),
            D.setMeta('lang', (data.user && data.user.language) || 'en'),
            D.setMeta('counts', data.counts || {}),
            D.setMeta('last_sync', new Date().toISOString())
          ]);
        }).then(function () {
          // Drop queued items the hub has already absorbed.
          return D.pending().then(function (rows) {
            var known = {};
            data.results.forEach(function (r) { if (r.client_uuid) known[r.client_uuid] = true; });
            data.lessons.forEach(function (l) { if (l.client_uuid) known[l.client_uuid] = true; });
            return Promise.all(rows.map(function (row) {
              return known[row.uuid] ? D.remove('outbox', row.uuid) : null;
            }));
          });
        }).then(function () {
          state.lastSync = new Date().toISOString();
          emit('edureach:data', {});
        });
      });
  }

  /* ----------------------------------------------------------------- push */

  function flush() {
    var D = global.EduDB;
    return D.pending().then(function (items) {
      if (!items.length) return { sent: 0 };
      return fetch(SYNC, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-EduReach-Sync': '1' },
        body: JSON.stringify({ items: items.map(function (i) {
          return { uuid: i.uuid, entity: i.entity, op: i.op, payload: i.payload };
        }) })
      }).then(function (res) {
        if (!res.ok) throw new Error('sync rejected: ' + res.status);
        return res.json();
      }).then(function (data) {
        var byUuid = {};
        items.forEach(function (i) { byUuid[i.uuid] = i; });
        return Promise.all((data.results || []).map(function (r) {
          var item = byUuid[r.uuid];
          if (!item) return null;
          // 'duplicate' means the hub already has it — just as final as 'applied'.
          if (r.status === 'applied' || r.status === 'duplicate') {
            return D.remove('outbox', r.uuid);
          }
          // Keep it. Never discard a student's work because a sync failed.
          item.attempts = (item.attempts || 0) + 1;
          item.last_error = r.error || 'unknown error';
          return D.put('outbox', item);
        })).then(function () { return { sent: items.length }; });
      });
    });
  }

  /** One full round trip: push queued work, then pull the hub's state. */
  function cycle() {
    if (state.syncing) return Promise.resolve();
    state.syncing = true;
    render();
    return flush()
      .then(bootstrap)
      .then(refreshPending)
      .then(function () {
        state.syncing = false;
        // A completed round trip is proof of reachability — don't make the
        // badge wait for the next poll to catch up.
        state.online = true;
        render();
        emit('edureach:sync', { ok: true });
      })
      .catch(function (err) {
        state.syncing = false;
        if (String(err && err.message).indexOf('signed out') === -1) {
          state.online = false;
        }
        render();
        refreshPending();
        emit('edureach:sync', { ok: false, error: String(err && err.message || err) });
      });
  }

  /* ----------------------------------------------------------------- init */

  function registerWorker() {
    if (!('serviceWorker' in navigator)) return Promise.resolve();
    return navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .catch(function (err) { console.warn('[EduReach] service worker failed:', err); });
  }

  var Sync = {
    state: state,
    cycle: cycle,
    flush: flush,
    bootstrap: bootstrap,
    refreshPending: refreshPending,
    isOnline: function () { return state.online !== false; },

    init: function () {
      registerWorker();
      render();
      refreshPending();

      global.addEventListener('online', function () { probe().then(setOnline); });
      global.addEventListener('offline', function () { setOnline(false); });

      // Re-check when the user comes back to the tab, and on a slow poll.
      document.addEventListener('visibilitychange', function () {
        if (!document.hidden) probe().then(setOnline);
      });
      setInterval(function () { probe().then(setOnline); }, POLL_MS);

      return probe().then(setOnline);
    }
  };

  global.EduSync = Sync;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { Sync.init(); });
  } else {
    Sync.init();
  }
})(window);

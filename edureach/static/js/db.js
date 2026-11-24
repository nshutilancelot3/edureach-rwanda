/* EduReach — IndexedDB layer.
 *
 * Mirrors the hub's SQLite tables on the device so every student and teacher
 * screen can be rebuilt with no network. Writes made offline are appended to
 * `outbox` and replayed by sync.js once the hub is reachable again.
 *
 * Every call resolves on transaction completion, not on request success, so a
 * resolved promise means the data is durable — it survives a tab crash or a
 * power cut mid-write (NFR 6).
 */
(function (global) {
  'use strict';

  var NAME = 'edureach';
  var VERSION = 1;

  var STORES = {
    meta:      { keyPath: 'key',  indexes: [] },
    lessons:   { keyPath: 'id',   indexes: ['subject', 'grade', 'teacher_id'] },
    quizzes:   { keyPath: 'id',   indexes: ['lesson_id'] },
    questions: { keyPath: 'id',   indexes: ['quiz_id'] },
    results:   { keyPath: 'id',   indexes: ['quiz_id'] },
    activity:  { keyPath: 'id',   indexes: [] },
    outbox:    { keyPath: 'uuid', indexes: ['state', 'entity'] }
  };

  var dbPromise = null;

  function open() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise(function (resolve, reject) {
      if (!global.indexedDB) {
        reject(new Error('IndexedDB is not available in this browser'));
        return;
      }
      var req = indexedDB.open(NAME, VERSION);
      req.onupgradeneeded = function (event) {
        var db = event.target.result;
        var upgradeTx = event.target.transaction;
        Object.keys(STORES).forEach(function (name) {
          var spec = STORES[name];
          var store = db.objectStoreNames.contains(name)
            ? upgradeTx.objectStore(name)
            : db.createObjectStore(name, { keyPath: spec.keyPath });
          spec.indexes.forEach(function (ix) {
            if (!store.indexNames.contains(ix)) store.createIndex(ix, ix, { unique: false });
          });
        });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
      req.onblocked = function () { reject(new Error('IndexedDB upgrade blocked by another tab')); };
    });
    return dbPromise;
  }

  /* Runs `fn(store, set)` inside one transaction. `set(value)` records what the
   * returned promise should resolve with. */
  function run(storeName, mode, fn) {
    return open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(storeName, mode);
        var result = null;
        var failed = false;

        tx.oncomplete = function () { if (!failed) resolve(result); };
        tx.onerror = function () { failed = true; reject(tx.error); };
        tx.onabort = function () { failed = true; reject(tx.error || new Error('transaction aborted')); };

        try {
          fn(tx.objectStore(storeName), function (value) { result = value; });
        } catch (err) {
          failed = true;
          try { tx.abort(); } catch (ignored) { /* already dead */ }
          reject(err);
        }
      });
    });
  }

  var API = {
    open: open,

    put: function (store, value) {
      return run(store, 'readwrite', function (s, set) {
        s.put(value).onsuccess = function (e) { set(e.target.result); };
      });
    },

    putAll: function (store, values) {
      if (!values || !values.length) return Promise.resolve(0);
      return run(store, 'readwrite', function (s, set) {
        values.forEach(function (v) { s.put(v); });
        set(values.length);
      });
    },

    get: function (store, key) {
      return run(store, 'readonly', function (s, set) {
        s.get(key).onsuccess = function (e) { set(e.target.result); };
      });
    },

    all: function (store) {
      return run(store, 'readonly', function (s, set) {
        s.getAll().onsuccess = function (e) { set(e.target.result || []); };
      });
    },

    byIndex: function (store, index, value) {
      return run(store, 'readonly', function (s, set) {
        s.index(index).getAll(value).onsuccess = function (e) { set(e.target.result || []); };
      });
    },

    remove: function (store, key) {
      return run(store, 'readwrite', function (s, set) {
        s.delete(key).onsuccess = function () { set(true); };
      });
    },

    /* Replaces a store's contents in one transaction. Used by the bootstrap
     * refresh so a half-applied snapshot can never be observed. */
    replaceAll: function (store, values) {
      return run(store, 'readwrite', function (s, set) {
        s.clear();
        (values || []).forEach(function (v) { s.put(v); });
        set((values || []).length);
      });
    },

    /* ---------------- meta ---------------- */

    setMeta: function (key, value) {
      return API.put('meta', { key: key, value: value });
    },

    getMeta: function (key) {
      return API.get('meta', key).then(function (row) { return row ? row.value : null; });
    },

    /* ---------------- outbox ---------------- */

    uuid: function () {
      if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : ((r & 0x3) | 0x8)).toString(16);
      });
    },

    /** Queue a write for the hub. The uuid is the server's dedupe key. */
    enqueue: function (entity, op, payload) {
      var item = {
        uuid: API.uuid(),
        entity: entity,          // 'quiz_result' | 'lesson' | 'activity'
        op: op,                  // 'create' | 'update' | 'delete'
        payload: payload,
        state: 'pending',
        attempts: 0,
        last_error: null,
        queued_at: new Date().toISOString()
      };
      return API.put('outbox', item).then(function () { return item; });
    },

    pending: function () {
      return API.byIndex('outbox', 'state', 'pending');
    },

    pendingCount: function () {
      return API.pending().then(function (rows) { return rows.length; });
    }
  };

  global.EduDB = API;
})(window);

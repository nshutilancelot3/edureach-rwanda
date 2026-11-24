/**
 * IndexedDB Manager for EduReach Offline Support
 * Handles all local data storage and retrieval
 */

class OfflineDB {
  constructor() {
    this.dbName = 'EduReachDB';
    this.version = 1;
    this.db = null;
  }

  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.version);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        console.log('[OfflineDB] Initialized');
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        this.createSchema(db);
      };
    });
  }

  createSchema(db) {
    const stores = [
      { name: 'users', keyPath: 'id', indexes: ['username', 'role'] },
      { name: 'lessons', keyPath: 'id', indexes: ['teacher_id', 'subject', 'grade', 'sync_status'] },
      { name: 'quizzes', keyPath: 'id', indexes: ['lesson_id', 'teacher_id', 'sync_status'] },
      { name: 'questions', keyPath: 'id', indexes: ['quiz_id'] },
      { name: 'quiz_results', keyPath: 'id', indexes: ['quiz_id', 'student_id', 'sync_status'] },
      { name: 'activity', keyPath: 'id', indexes: ['student_id', 'sync_status'] },
      { name: 'pending_sync', keyPath: 'id', indexes: ['table_name', 'record_id', 'operation'] },
    ];

    stores.forEach((store) => {
      if (!db.objectStoreNames.contains(store.name)) {
        const objectStore = db.createObjectStore(store.name, { keyPath: store.keyPath });
        store.indexes.forEach((indexName) => {
          objectStore.createIndex(indexName, indexName, { unique: false });
        });
        console.log(`[OfflineDB] Created store: ${store.name}`);
      }
    });
  }

  async put(storeName, data) {
    const tx = this.db.transaction([storeName], 'readwrite');
    return new Promise((resolve, reject) => {
      const request = tx.objectStore(storeName).put(data);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async get(storeName, key) {
    const tx = this.db.transaction([storeName], 'readonly');
    return new Promise((resolve, reject) => {
      const request = tx.objectStore(storeName).get(key);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async getAll(storeName) {
    const tx = this.db.transaction([storeName], 'readonly');
    return new Promise((resolve, reject) => {
      const request = tx.objectStore(storeName).getAll();
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async query(storeName, indexName, value) {
    const tx = this.db.transaction([storeName], 'readonly');
    return new Promise((resolve, reject) => {
      const index = tx.objectStore(storeName).index(indexName);
      const request = index.getAll(value);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async delete(storeName, key) {
    const tx = this.db.transaction([storeName], 'readwrite');
    return new Promise((resolve, reject) => {
      const request = tx.objectStore(storeName).delete(key);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async recordPending(operation, tableName, recordId, data) {
    const pending = {
      id: `${tableName}_${recordId}_${Date.now()}`,
      table_name: tableName,
      record_id: recordId,
      operation: operation,
      data: data,
      timestamp: new Date().toISOString(),
      synced: false,
    };
    return this.put('pending_sync', pending);
  }

  async getPending() {
    return this.query('pending_sync', 'synced', false);
  }

  async clearPending(pendingId) {
    return this.delete('pending_sync', pendingId);
  }
}

// Initialize and export
const offlineDB = new OfflineDB();

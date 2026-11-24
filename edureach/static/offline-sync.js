/**
 * Offline Sync Manager
 * Synchronizes pending changes with the backend
 */

class OfflineSync {
  constructor(offlineDB) {
    this.db = offlineDB;
    this.isSyncing = false;
    this.syncInterval = null;
  }

  async init() {
    // Register Service Worker
    if ('serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/static/service-worker.js', {
          scope: '/',
        });
        console.log('[Sync] Service Worker registered');
      } catch (error) {
        console.error('[Sync] Service Worker registration failed:', error);
      }
    }

    // Listen for online/offline events
    window.addEventListener('online', () => this.handleOnline());
    window.addEventListener('offline', () => this.handleOffline());

    // Check connection and sync if online
    if (navigator.onLine) {
      await this.sync();
    }

    // Setup periodic sync attempts
    this.syncInterval = setInterval(() => {
      if (navigator.onLine && !this.isSyncing) {
        this.sync();
      }
    }, 30000); // Every 30 seconds

    this.updateUI();
  }

  async handleOnline() {
    console.log('[Sync] Connection restored');
    this.updateUI();
    await this.sync();
  }

  handleOffline() {
    console.log('[Sync] Connection lost');
    this.updateUI();
  }

  async sync() {
    if (this.isSyncing) return;

    this.isSyncing = true;
    console.log('[Sync] Starting synchronization...');

    try {
      const pending = await this.db.getPending();
      if (pending.length === 0) {
        console.log('[Sync] No pending changes');
        this.isSyncing = false;
        return;
      }

      console.log(`[Sync] Found ${pending.length} pending changes`);

      for (const item of pending) {
        await this.syncItem(item);
      }

      console.log('[Sync] Synchronization complete');
      this.showNotification('All changes synced successfully');
    } catch (error) {
      console.error('[Sync] Sync failed:', error);
      this.showNotification('Sync failed - will retry when online', 'error');
    } finally {
      this.isSyncing = false;
      this.updateUI();
    }
  }

  async syncItem(pending) {
    const { table_name, record_id, operation, data, id } = pending;

    try {
      const response = await fetch(`/api/sync/${table_name}/${record_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          operation,
          data,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // Clear pending record after successful sync
      await this.db.clearPending(id);
      console.log(`[Sync] Synced ${table_name} ${record_id}`);
    } catch (error) {
      console.error(`[Sync] Failed to sync ${table_name}:`, error);
      throw error;
    }
  }

  updateUI() {
    const status = navigator.onLine ? 'online' : 'offline';
    document.documentElement.setAttribute('data-sync-status', status);

    const indicator = document.getElementById('sync-status');
    if (indicator) {
      indicator.textContent = status === 'online' ? '●' : '◯';
      indicator.className = `sync-status ${status}`;
    }
  }

  showNotification(message, type = 'success') {
    // Simple notification - can be enhanced
    console.log(`[Notify] ${message}`);
  }

  async loadFromServer() {
    try {
      console.log('[Sync] Loading initial data from server...');

      // Fetch all data types
      const [users, lessons, quizzes, questions, results] = await Promise.all([
        fetch('/api/data/users').then((r) => r.json()),
        fetch('/api/data/lessons').then((r) => r.json()),
        fetch('/api/data/quizzes').then((r) => r.json()),
        fetch('/api/data/questions').then((r) => r.json()),
        fetch('/api/data/quiz-results').then((r) => r.json()),
      ]);

      // Store in IndexedDB
      for (const user of users) await this.db.put('users', user);
      for (const lesson of lessons) await this.db.put('lessons', lesson);
      for (const quiz of quizzes) await this.db.put('quizzes', quiz);
      for (const question of questions) await this.db.put('questions', question);
      for (const result of results) await this.db.put('quiz_results', result);

      console.log('[Sync] Data loaded and cached locally');
    } catch (error) {
      console.error('[Sync] Failed to load initial data:', error);
      // This is OK - app can still use locally cached data
    }
  }

  destroy() {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
    }
  }
}

// Initialize
(async () => {
  if (!offlineDB.db) {
    await offlineDB.init();
  }
  window.offlineSync = new OfflineSync(offlineDB);
  await window.offlineSync.init();

  // Load data on first visit while online
  if (navigator.onLine) {
    await window.offlineSync.loadFromServer();
  }
})().catch(console.error);

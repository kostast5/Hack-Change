// Хранение сессий в браузере. Если localStorage недоступен, работает в памяти.

export class LocalStorageRepository {
  constructor(key) { this.key = key; }

  load() {
    try { return JSON.parse(localStorage.getItem(this.key) || '[]'); } catch (e) { return []; }
  }

  save(sessions) {
    try { localStorage.setItem(this.key, JSON.stringify(sessions)); } catch (e) { /* ignore */ }
  }
}

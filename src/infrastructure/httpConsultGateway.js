// Бэкенд (server.py → consult() из solution.py): POST /api/consult и POST /api/lead
// Ответ consult: { answer, sources:[{path,title,quote,score}], lead: null | {fio,phone,company,summary} }

export class HttpConsultGateway {
  constructor(apiBase = '') {
    this.apiBase = apiBase;
  }

  async fetchSuggestions(answer) {
    const res = await fetch(`${this.apiBase}/api/suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.suggestions) ? data.suggestions.filter(Boolean) : [];
  }

  async consult(messages) {
    const t0 = performance.now();
    const res = await fetch(`${this.apiBase}/api/consult`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { ...data, ms: Math.round(performance.now() - t0), mock: false };
  }

  async submitLead(body) {
    await fetch(`${this.apiBase}/api/lead`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  async syncSessions(sessions) {
    await fetch(`${this.apiBase}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessions }),
    });
  }

  async loadSessions() {
    const res = await fetch(`${this.apiBase}/api/sessions`, { cache: 'no-store' });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.sessions) ? data.sessions : [];
  }

  async resetRuntime() {
    await fetch(`${this.apiBase}/api/reset`, { method: 'POST' });
  }
}

// Адаптер под порт leadGateway
export class HttpLeadGateway {
  constructor(consultGateway) { this.gateway = consultGateway; }
  submit(data) { return this.gateway.submitLead(data); }
}

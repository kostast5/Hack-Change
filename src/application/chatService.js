// Сценарии использования. Зависит только от доменных функций и «портов»:
//   consultGateway.consult(messages) -> { answer, sources, lead, ms, mock }
//   leadGateway.submit(data)         -> Promise<void>
//   repository.load() / repository.save(sessions)

import {
  LeadState, createSession, isEmpty, addUserMessage, addAssistantMessage,
  addErrorMessage, offerLead, declineLead, markLeadSent, toPayload,
} from '../domain/session.js?v=3';

export class ChatService {
  constructor({ consultGateway, leadGateway, repository, titleMaxLength = 48, debug = false }) {
    this.consultGateway = consultGateway;
    this.leadGateway = leadGateway;
    this.repository = repository;
    this.titleMaxLength = titleMaxLength;
    this.listeners = new Set();

    const sessions = repository.load();
    this.state = { sessions, currentId: sessions[0] ? sessions[0].id : null, busy: false, debug };
    if (!this.current) this.newDialog();
  }

  get current() {
    return this.state.sessions.find((s) => s.id === this.state.currentId) || null;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  #snapshot() {
    return this.state.sessions.map((session) => ({
      id: session.id,
      title: session.title,
      ts: session.ts,
      leadState: session.leadState,
      lead: session.lead,
      messages: toPayload(session),
    }));
  }

  #commit() {
    this.repository.save(this.state.sessions);
    this.listeners.forEach((fn) => fn(this.state));
    const payload = this.#snapshot();
    if (this.consultGateway.syncSessions) {
      this.consultGateway.syncSessions(payload).catch(() => {});
    }
  }

  mergeRemote(remote) {
    if (!Array.isArray(remote) || !remote.length) return;
    const byId = new Map(this.state.sessions.map((session) => [String(session.id), session]));
    if (this.state.sessions.length === 1 && isEmpty(this.state.sessions[0])) byId.clear();
    remote.forEach((item) => {
      if (!item || item.id == null) return;
      const prev = byId.get(String(item.id));
      if (!prev || (item.ts || 0) > (prev.ts || 0)) {
        byId.set(String(item.id), {
          id: item.id,
          title: item.title || 'Диалог',
          messages: Array.isArray(item.messages) ? item.messages : [],
          leadState: item.leadState || LeadState.NONE,
          lead: item.lead || null,
          ts: item.ts || Date.now(),
        });
      }
    });
    this.state.sessions = [...byId.values()].sort((a, b) => b.ts - a.ts);
    if (!this.current && this.state.sessions[0]) this.state.currentId = this.state.sessions[0].id;
    this.#commit();
  }

  selectSession(id) {
    const found = this.state.sessions.find((session) => String(session.id) === String(id));
    if (!found) return;
    this.state.currentId = found.id;
    this.#commit();
  }

  setDebug(on) {
    this.state.debug = on;
    this.listeners.forEach((fn) => fn(this.state));
  }

  newDialog() {
    // пустую текущую сессию не плодим
    if (this.current && isEmpty(this.current)) return;
    const session = createSession();
    this.state.sessions.unshift(session);
    this.state.currentId = session.id;
    this.#commit();
  }

  startFreshChat() {
    const greeting = 'Здравствуйте! Чем могу вам помочь?';
    let session = this.current;
    if (!session || !isEmpty(session)) {
      session = createSession();
      this.state.sessions.unshift(session);
      this.state.currentId = session.id;
    }
    if (session.messages.some((m) => m.role === 'assistant' && m.content === greeting)) {
      this.#commit();
      return;
    }
    session.messages.push({
      role: 'assistant',
      content: greeting,
      sources: [],
      suggestions: [],
    });
    session.ts = Date.now();
    this.#commit();
  }

  openLeadForm() {
    if (!this.current) this.newDialog();
    const session = this.current;
    if (!session || session.leadState !== LeadState.NONE) return;
    const lastUser = [...session.messages].reverse().find((m) => m.role === 'user');
    offerLead(session, {
      fio: '',
      phone: '',
      company: '',
      summary: lastUser ? String(lastUser.content).slice(0, 800) : '',
    });
    this.#commit();
  }

  async send(rawText) {
    const text = rawText.trim();
    if (!text || this.state.busy) return;
    if (!this.current) this.newDialog();

    const session = this.current;
    if (session.leadState === LeadState.DRAFT) {
      declineLead(session);
    }
    addUserMessage(session, text, this.titleMaxLength);
    this.state.busy = true;
    this.#commit();

    try {
      const reply = await this.consultGateway.consult(toPayload(session));
      addAssistantMessage(session, reply);
      if (reply.lead) offerLead(session, reply.lead);
    } catch (e) {
      addErrorMessage(session, 'Не удалось получить ответ. Повторите сообщение или оставьте заявку.');
    } finally {
      this.state.busy = false;
      this.#commit();
    }
  }

  async submitLead(data) {
    const session = this.current;
    if (!session || session.leadState !== LeadState.DRAFT) return;
    let summary = String(data.summary || '').trim();
    if (!summary && session.lead?.summary) {
      summary = String(session.lead.summary);
    }
    summary = summary
      .replace('имя не указано', data.fio || 'имя не указано')
      .replace('компания не названа', data.company || 'компания не указана');
    data = { ...data, summary };
    const payload = {
      ...data,
      sessionId: session.id,
      title: session.title,
      ts: session.ts,
      messages: toPayload(session),
    };
    markLeadSent(session, data);
    this.#commit();
    try { await this.leadGateway.submit(payload); } catch (e) { /* заявка уже в списке сессий */ }
  }

  declineLead() {
    if (!this.current) return;
    declineLead(this.current);
    this.#commit();
  }
}

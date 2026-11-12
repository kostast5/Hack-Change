// Сценарии использования. Зависит только от доменных функций и «портов»:
//   consultGateway.consult(messages) -> { answer, sources, lead, ms, mock }
//   leadGateway.submit(data)         -> Promise<void>
//   repository.load() / repository.save(sessions)

import {
  LeadState, createSession, isEmpty, addUserMessage, addAssistantMessage,
  addErrorMessage, offerLead, declineLead, markLeadSent, toPayload,
} from '../domain/session.js';

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

  #commit() {
    this.repository.save(this.state.sessions);
    this.listeners.forEach((fn) => fn(this.state));
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

  selectSession(id) {
    this.state.currentId = id;
    this.#commit();
  }

  async send(rawText) {
    const text = rawText.trim();
    if (!text || this.state.busy) return;
    if (!this.current) this.newDialog();

    const session = this.current;
    addUserMessage(session, text, this.titleMaxLength);
    this.state.busy = true;
    this.#commit();

    try {
      const reply = await this.consultGateway.consult(toPayload(session));
      addAssistantMessage(session, reply);
      if (reply.lead) offerLead(session, reply.lead);
    } catch (e) {
      addErrorMessage(session, 'Не удалось получить ответ. Попробуйте ещё раз.');
    } finally {
      this.state.busy = false;
      this.#commit();
    }
  }

  async submitLead(data) {
    const session = this.current;
    if (!session || session.leadState !== LeadState.DRAFT) return;
    try { await this.leadGateway.submit(data); } catch (e) { /* CRM не подключаем */ }
    markLeadSent(session, data);
    this.#commit();
  }

  declineLead() {
    if (!this.current) return;
    declineLead(this.current);
    this.#commit();
  }
}

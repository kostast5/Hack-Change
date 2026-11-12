// Сущности и правила предметной области. Не знает ни про DOM, ни про сеть.

export const LeadState = Object.freeze({ NONE: 'none', DRAFT: 'draft', SENT: 'sent' });
export const DEFAULT_TITLE = 'Новый диалог';

export function createSession(now = Date.now()) {
  return { id: now, title: DEFAULT_TITLE, messages: [], leadState: LeadState.NONE, lead: null, ts: now };
}

export const isEmpty = (session) => session.messages.length === 0;

export function addUserMessage(session, text, titleMaxLength = 48) {
  session.messages.push({ role: 'user', content: text });
  if (session.title === DEFAULT_TITLE) session.title = text.slice(0, titleMaxLength);
  session.ts = Date.now();
}

export function addAssistantMessage(session, reply) {
  session.messages.push({
    role: 'assistant',
    content: reply.answer,
    sources: reply.sources || [],
    ms: reply.ms,
    mock: Boolean(reply.mock),
  });
}

export function addErrorMessage(session, text) {
  session.messages.push({ role: 'error', content: text });
}

export function offerLead(session, draft) {
  if (session.leadState !== LeadState.NONE) return;
  session.lead = draft;
  session.leadState = LeadState.DRAFT;
}

export function declineLead(session) {
  session.lead = null;
  session.leadState = LeadState.NONE;
}

export function markLeadSent(session, data) {
  session.lead = data;
  session.leadState = LeadState.SENT;
}

// Что уходит в consult(): только реплики пользователя и ассистента
export function toPayload(session) {
  return session.messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role, content: m.content }));
}

import { el } from './dom.js';
import { renderDebugPanel } from './debugPanel.js?v=3';
import { renderLeadCard, renderLeadDone } from './leadCard.js?v=8';
import { LeadState } from '../domain/session.js?v=3';

function renderWelcome(demos, onDemo) {
  const box = el('div', 'empty');
  box.append(
    el('h2', '', 'Чем могу помочь?'),
    el('p', '', 'Опишите проблему. Помогу разобраться и предложить решение.'),
  );
  const list = el('div', 'demos');
  demos.forEach((d) => {
    const btn = el('button', 'demo', d.title);
    btn.type = 'button';
    if (d.hint) btn.append(el('small', '', d.hint));
    btn.onclick = () => onDemo(d);
    list.append(btn);
  });
  box.append(list);
  return box;
}

function renderTyping() {
  const node = el('div', 'msg bot dots');
  node.innerHTML = '<span></span><span></span><span></span>';
  return node;
}

export function renderChat(container, state, session, { demos, onDemo, onSubmitLead, onDeclineLead, onQuick, onRequestLead }) {
  container.innerHTML = '';

  if (!session || !session.messages.length) {
    container.append(renderWelcome(demos, onDemo));
    return;
  }

  const lastAssistant = [...session.messages].reverse().find((m) => m.role === 'assistant');

  session.messages.forEach((m) => {
    if (m.role === 'user') container.append(el('div', 'msg user', m.content));
    else if (m.role === 'error') container.append(el('div', 'msg bot err', m.content));
    else {
      container.append(el('div', 'msg bot', m.content));
      if (state.debug) container.append(renderDebugPanel(m));
      const chips = m.suggestions || [];
      if (!state.busy && m === lastAssistant && session.leadState === LeadState.NONE && chips.length) {
        const row = el('div', 'chips');
        chips.forEach((label) => {
          const btn = el('button', '', label);
          btn.type = 'button';
          btn.onclick = () => onQuick(label);
          row.append(btn);
        });
        container.append(row);
      }
    }
  });

  if (state.busy) container.append(renderTyping());
  const userSpoke = session.messages.some((m) => m.role === 'user');
  if (!state.busy && userSpoke && session.leadState === LeadState.NONE && lastAssistant) {
    const ask = el('button', 'btn sec ask-lead', 'Оставить заявку');
    ask.type = 'button';
    ask.onclick = () => onRequestLead();
    container.append(ask);
  }
  if (session.leadState === LeadState.DRAFT) container.append(renderLeadCard(session.lead, { onSubmit: onSubmitLead, onDecline: onDeclineLead }));
  if (session.leadState === LeadState.SENT) container.append(renderLeadDone());

  container.scrollTop = container.scrollHeight;
}

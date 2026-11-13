import { el } from './dom.js';
import { renderDebugPanel } from './debugPanel.js';
import { renderLeadCard, renderLeadDone } from './leadCard.js';
import { LeadState } from '../domain/session.js';

function renderWelcome(demos, onDemo) {
  const box = el('div', 'empty');
  box.append(
    el('h2', '', 'Чем помочь вашему объекту?'),
    el('p', '', 'Расскажите о задаче — подскажу, какое решение Energytool подходит, и что нужно для оценки.'),
  );
  const list = el('div', 'demos');
  demos.forEach((d) => {
    const btn = el('button', 'demo', d.title);
    btn.type = 'button';
    btn.append(el('small', '', d.hint));
    btn.onclick = () => onDemo(d.question);
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

export function renderChat(container, state, session, { demos, onDemo, onSubmitLead, onDeclineLead }) {
  container.innerHTML = '';

  if (!session || !session.messages.length) {
    container.append(renderWelcome(demos, onDemo));
    return;
  }

  session.messages.forEach((m) => {
    if (m.role === 'user') container.append(el('div', 'msg user', m.content));
    else if (m.role === 'error') container.append(el('div', 'msg bot err', m.content));
    else {
      container.append(el('div', 'msg bot', m.content));
      if (state.debug) container.append(renderDebugPanel(m));
    }
  });

  if (state.busy) container.append(renderTyping());
  if (session.leadState === LeadState.DRAFT) container.append(renderLeadCard(session.lead, { onSubmit: onSubmitLead, onDecline: onDeclineLead }));
  if (session.leadState === LeadState.SENT) container.append(renderLeadDone());

  container.scrollTop = container.scrollHeight;
}

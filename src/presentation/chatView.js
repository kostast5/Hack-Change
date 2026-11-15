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

export function renderChat(container, state, session, {
  demos, onDemo, onSubmitLead, onDeclineLead, onQuick, onRequestLead, animateFrom = 0,
}) {
  container.innerHTML = '';

  if (!session || !session.messages.length) {
    container.append(renderWelcome(demos, onDemo));
    return;
  }

  const lastAssistant = [...session.messages].reverse().find((m) => m.role === 'assistant');

  session.messages.forEach((m, index) => {
    const animate = index >= animateFrom;
    if (m.role === 'user') {
      const node = el('div', animate ? 'msg user msg-in' : 'msg user', m.content);
      container.append(node);
    } else if (m.role === 'error') {
      const node = el('div', animate ? 'msg bot err msg-in' : 'msg bot err', m.content);
      container.append(node);
    } else {
      const node = el('div', animate ? 'msg bot msg-in' : 'msg bot', m.content);
      container.append(node);
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

  if (state.busy) {
    const typing = renderTyping();
    typing.classList.add('msg-in');
    container.append(typing);
  }
  const userSpoke = session.messages.some((m) => m.role === 'user');
  if (!state.busy && userSpoke && session.leadState === LeadState.NONE && lastAssistant) {
    const ask = el('button', 'btn sec ask-lead', 'Оставить заявку');
    ask.type = 'button';
    ask.onclick = () => onRequestLead();
    container.append(ask);
  }
  if (session.leadState === LeadState.DRAFT) {
    const lead = renderLeadCard(session.lead, { onSubmit: onSubmitLead, onDecline: onDeclineLead });
    lead.classList.add('msg-in');
    container.append(lead);
  }
  if (session.leadState === LeadState.SENT) {
    const done = renderLeadDone();
    done.classList.add('msg-in');
    container.append(done);
  }

  container.scrollTop = container.scrollHeight;
}

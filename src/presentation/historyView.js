import { el } from './dom.js';
import { LeadState } from '../domain/session.js';

export function renderHistory(container, state, onSelect) {
  container.innerHTML = '';
  if (!state.sessions.length) container.append(el('p', 'hist-empty', 'Диалогов пока нет'));

  state.sessions.forEach((s) => {
    const btn = el('button', 'h-item');
    btn.type = 'button';
    if (s.id === state.currentId) btn.setAttribute('aria-current', 'true');

    const title = el('b', '', s.title);
    if (s.leadState === LeadState.SENT) title.append(el('span', 'tag', 'заявка'));

    const date = new Date(s.ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const info = `${date} · ${s.messages.length} сообщ.` + (s.leadState === LeadState.SENT ? '' : ' · без заявки');

    btn.append(title, el('small', '', info));
    btn.onclick = () => onSelect(s.id);
    container.append(btn);
  });
}

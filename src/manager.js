import { el } from './presentation/dom.js';

const leadsBox = document.getElementById('leads');
const sessionsBox = document.getElementById('sessions');
const dialogBox = document.getElementById('dialog');

const when = (ts) => new Date(ts || Date.now()).toLocaleString('ru-RU', {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});

function openDialog(session) {
  dialogBox.innerHTML = '';
  const box = el('div', 'thread');
  box.append(el('h2', '', session.title || 'Чат'));
  const messages = session.messages || [];
  if (!messages.length) box.append(el('p', 'empty-line', 'В чате нет сообщений'));
  messages.forEach((message) => {
    const css = message.role === 'user' ? 'msg user' : 'msg bot';
    box.append(el('div', css, message.content));
  });
  const back = el('a', 'btn sec', 'Продолжить в чате');
  back.href = `/?session=${encodeURIComponent(session.id)}&persist=1`;
  box.append(back);
  dialogBox.append(box);
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function ticket(session) {
  const lead = session.lead || {};
  const card = el('article', 'ticket');
  const top = el('div', 'ticket-top');
  top.append(el('strong', '', lead.company || 'Компания не указана'), el('time', '', when(lead.sentAt || session.ts)));
  const who = [lead.fio, lead.phone].filter(Boolean).join(' · ');
  card.append(top);
  if (who) card.append(el('p', 'who', who));
  card.append(el('p', 'task', session.title || 'Вопрос'));
  if (lead.summary) card.append(el('p', 'sum', lead.summary));
  const btn = el('button', 'btn sec', 'Открыть чат');
  btn.type = 'button';
  btn.onclick = () => openDialog(session);
  card.append(btn);
  return card;
}

function render(sessions) {
  const sent = sessions.filter((session) => session.leadState === 'sent' && session.lead);
  leadsBox.innerHTML = '';
  sessionsBox.innerHTML = '';
  if (!sent.length) {
    leadsBox.append(el('p', 'empty-line', 'Пока заявок нет.'));
  } else {
    const grid = el('div', 'tickets');
    sent.forEach((session) => grid.append(ticket(session)));
    leadsBox.append(grid);
  }
  if (!sessions.length) {
    sessionsBox.append(el('p', 'empty-line', 'Чатов пока нет.'));
    return;
  }
  const list = el('div', 'talks');
  sessions.forEach((session) => {
    const row = el('button', 'talk');
    row.type = 'button';
    const count = (session.messages || []).length;
    const mark = session.leadState === 'sent' ? ' · есть заявка' : '';
    row.append(el('b', '', session.title || 'чат'), el('small', '', `${when(session.ts)} · ${count} сообщ.${mark}`));
    row.onclick = () => openDialog(session);
    list.append(row);
  });
  sessionsBox.append(list);
}

const data = await fetch('/api/sessions', { cache: 'no-store' }).then((res) => res.json());
render(Array.isArray(data.sessions) ? data.sessions : []);

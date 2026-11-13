import { el } from './dom.js';

export function renderLeadCard(lead, { onSubmit, onDecline }) {
  const form = el('form', 'lead');
  form.append(
    el('h3', '', 'Оставить заявку специалисту'),
    el('p', 'n', 'Заполните только то, чем готовы поделиться. Резюме можно поправить.'),
  );

  const field = (name, label, tag = 'input') => {
    const wrap = el('label', '', label);
    const input = el(tag);
    input.name = name;
    input.value = lead[name] || '';
    if (tag === 'textarea') input.rows = 4;
    wrap.append(input);
    form.append(wrap);
    return input;
  };
  field('fio', 'ФИО');
  field('phone', 'Телефон').type = 'tel';
  field('company', 'Компания');
  field('summary', 'Резюме для менеджера', 'textarea');

  const row = el('div', 'row');
  const ok = el('button', 'btn', 'Отправить заявку');
  ok.type = 'submit';
  const no = el('button', 'btn sec', 'Не сейчас');
  no.type = 'button';
  no.onclick = onDecline;
  row.append(ok, no);
  form.append(row);

  form.onsubmit = (e) => {
    e.preventDefault();
    ok.disabled = true;
    onSubmit(Object.fromEntries(new FormData(form)));
  };
  return form;
}

export function renderLeadDone() {
  const card = el('div', 'lead done');
  card.append(
    el('h3', '', 'Заявка передана специалисту'),
    el('p', 'n', 'Менеджер пресейла свяжется с вами. Это демо: заявка в CRM не отправляется.'),
  );
  return card;
}

import { el } from './dom.js';

export function renderLeadCard(lead, { onSubmit, onDecline }) {
  const form = el('form', 'lead');
  form.append(
    el('h3', '', 'Контакты для связи'),
    el('p', 'n', 'Введите имя и номер телефона.'),
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
  field('fio', 'ФИО').required = true;
  const phone = field('phone', 'Телефон');
  phone.type = 'tel';
  phone.required = true;
  field('company', 'Компания');
  const summary = field('summary', 'Описание проблемы', 'textarea');
  summary.value = '';

  const row = el('div', 'row');
  const ok = el('button', 'btn', 'Отправить');
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
  const link = el('a', 'btn sec', 'Список заявок');
  link.href = '/manager';
  card.append(
    el('h3', '', 'Ожидайте, заявка в работе'),
    el('p', 'n', 'Специалист вернется к вам с решением.'),
    link,
  );
  return card;
}

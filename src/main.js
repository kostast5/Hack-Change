// Точка сборки: создаёт зависимости и связывает слои. Бизнес-логики здесь нет.

import { config } from './config.js';
import { DEMOS } from './domain/demos.js';
import { ChatService } from './application/chatService.js';
import { HttpConsultGateway, HttpLeadGateway } from './infrastructure/httpConsultGateway.js';
import { LocalStorageRepository } from './infrastructure/localStorageRepository.js';
import { renderHistory } from './presentation/historyView.js';
import { renderChat } from './presentation/chatView.js';
import { setupComposer } from './presentation/composer.js';

const $ = (id) => document.getElementById(id);

const http = new HttpConsultGateway(config.apiBase);
const chat = new ChatService({
  consultGateway: http,
  leadGateway: new HttpLeadGateway(http),
  repository: new LocalStorageRepository(config.storageKey),
  titleMaxLength: config.titleMaxLength,
  debug: config.debug,
});

const composer = setupComposer({
  form: $('form'), input: $('inp'), button: $('send'),
  onSend: async (text) => { await chat.send(text); composer.focus(); },
});

$('dbgToggle').checked = config.debug;
$('dbgToggle').onchange = (e) => chat.setDebug(e.target.checked);
$('newBtn').onclick = () => { chat.newDialog(); composer.focus(); };

function render(state) {
  renderHistory($('hist'), state, (id) => chat.selectSession(id));
  renderChat($('log'), state, chat.current, {
    demos: DEMOS,
    onDemo: (q) => chat.send(q),
    onSubmitLead: (data) => chat.submitLead(data),
    onDeclineLead: () => chat.declineLead(),
  });
  composer.setBusy(state.busy);
}

chat.subscribe(render);
render(chat.state);

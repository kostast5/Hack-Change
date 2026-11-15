// Точка сборки: создаёт зависимости и связывает слои. Бизнес-логики здесь нет.

import { config } from './config.js?v=4';
import { DEMOS } from './domain/demos.js?v=4';
import { ChatService } from './application/chatService.js?v=9';
import { HttpConsultGateway, HttpLeadGateway } from './infrastructure/httpConsultGateway.js?v=4';
import { LocalStorageRepository } from './infrastructure/localStorageRepository.js';
import { renderHistory } from './presentation/historyView.js?v=3';
import { renderChat } from './presentation/chatView.js?v=6';
import { setupComposer } from './presentation/composer.js';

const $ = (id) => document.getElementById(id);

const http = new HttpConsultGateway(config.apiBase);

if (!config.persist) {
  try { localStorage.removeItem(config.storageKey); } catch (e) { /* ignore */ }
  await http.resetRuntime().catch(() => {});
}

const chat = new ChatService({
  consultGateway: http,
  leadGateway: new HttpLeadGateway(http),
  repository: new LocalStorageRepository(config.storageKey),
  titleMaxLength: config.titleMaxLength,
  debug: config.debug,
});

if (config.embed) document.body.classList.add('embed');

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
    onDemo: (demo) => {
      if (!demo.question) { chat.startFreshChat(); composer.focus(); return; }
      chat.send(demo.question);
    },
    onQuick: (q) => chat.send(q),
    onRequestLead: () => chat.requestLead(),
    onSubmitLead: (data) => chat.submitLead(data),
    onDeclineLead: () => chat.declineLead(),
  });
  composer.setBusy(state.busy);
}

chat.subscribe(render);
render(chat.state);

if (config.persist) {
  const remote = await http.loadSessions().catch(() => []);
  chat.mergeRemote(remote);
  if (config.session) chat.selectSession(config.session);
}

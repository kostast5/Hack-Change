// Точка сборки: создаёт зависимости и связывает слои. Бизнес-логики здесь нет.

import { config } from './config.js?v=4';
import { DEMOS } from './domain/demos.js?v=4';
import { ChatService } from './application/chatService.js?v=11';
import { HttpConsultGateway, HttpLeadGateway } from './infrastructure/httpConsultGateway.js?v=4';
import { LocalStorageRepository } from './infrastructure/localStorageRepository.js';
import { renderHistory } from './presentation/historyView.js?v=3';
import { renderChat } from './presentation/chatView.js?v=7';
import { setupComposer } from './presentation/composer.js';

const $ = (id) => document.getElementById(id);

const http = new HttpConsultGateway(config.apiBase);

const keepSessions = config.persist || Boolean(config.session);
if (!keepSessions) {
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

const renderedLen = new Map();

function render(state) {
  const session = chat.current;
  const sid = session ? String(session.id) : '';
  const animateFrom = renderedLen.get(sid) ?? 0;
  renderHistory($('hist'), state, (id) => chat.selectSession(id));
  renderChat($('log'), state, chat.current, {
    animateFrom,
    demos: DEMOS,
    onDemo: (demo) => {
      if (!demo.question) { chat.startFreshChat(); composer.focus(); return; }
      chat.send(demo.question);
    },
    onQuick: (q) => chat.send(q),
    onRequestLead: () => chat.openLeadForm(),
    onSubmitLead: (data) => chat.submitLead(data),
    onDeclineLead: () => chat.declineLead(),
  });
  if (session) renderedLen.set(sid, session.messages.length);
  composer.setBusy(state.busy);
}

chat.subscribe(render);
render(chat.state);

const remote = await http.loadSessions().catch(() => []);
if (keepSessions || remote.length) chat.mergeRemote(remote);
if (config.session) chat.selectSession(config.session);

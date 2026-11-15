import { el } from './dom.js';

// Режим отладки: время ответа, путь файла базы, раздел, оценка и цитата
export function renderDebugPanel(message) {
  const box = el('div', 'dbg');
  const mockNote = message.mock ? ' · без вызова API' : '';
  const cacheNote = message.cached ? ' · из кэша' : '';
  box.append(el('div', 't', `Время ответа: ${(message.ms / 1000).toFixed(2)} с${mockNote}${cacheNote}`));

  if (!message.sources.length) {
    box.append(el('div', 'src', 'К ответу не приложён фрагмент базы знаний.'));
    return box;
  }
  message.sources.forEach((s) => {
    const row = el('div', 'src');
    const score = s.score != null ? ` · оценка ${Number(s.score).toFixed(2)}` : '';
    row.append(el('code', '', s.path), document.createTextNode(` · ${s.title || ''}${score}`));
    if (s.quote) row.append(el('blockquote', '', s.quote));
    box.append(row);
  });
  return box;
}

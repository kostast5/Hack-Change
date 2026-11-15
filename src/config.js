const params = new URLSearchParams(location.search);

export const config = {
  apiBase: (params.get('api') || '').replace(/\/$/, ''), // ?api=http://host:port
  debug: params.get('debug') === '1',                    // ?debug=1
  embed: params.get('embed') === '1',                    // ?embed=1 виджет на сайте
  session: params.get('session') || '',
  // ?persist=1 — не сбрасывать диалоги и кэш при перезагрузке страницы
  persist: params.get('persist') === '1',
  storageKey: 'energytool_sessions',
  titleMaxLength: 48,
};

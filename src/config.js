const params = new URLSearchParams(location.search);

export const config = {
  apiBase: (params.get('api') || '').replace(/\/$/, ''), // ?api=http://host:port
  debug: params.get('debug') === '1',                    // ?debug=1
  storageKey: 'energytool_sessions',
  titleMaxLength: 48,
};

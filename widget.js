/* Одна строка на сайте Energytool: <script src="https://хост/widget.js"></script> */
(function () {
  if (window.__energytoolWidget) return;
  window.__energytoolWidget = true;
  if (window.top !== window.self) return;

  var script = document.currentScript;
  var origin = script ? new URL(script.src, window.location.href).origin : window.location.origin;

  function mount() {
    var host = document.createElement('div');
    var root = host.attachShadow({ mode: 'open' });
    root.innerHTML = [
      '<style>',
      ':host{all:initial}',
      '.btn{position:fixed;z-index:2147483000;right:20px;bottom:20px;width:60px;height:60px;border:0;border-radius:50%;background:#E30613;color:#fff;display:grid;place-items:center;cursor:pointer;box-shadow:0 8px 24px rgba(227,6,19,.35)}',
      '.panel{position:fixed;z-index:2147483000;right:20px;bottom:92px;width:min(400px,calc(100vw - 24px));height:min(640px,calc(100vh - 120px));background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 16px 50px rgba(0,0,0,.22);display:none;flex-direction:column}',
      '.panel.open{display:flex}',
      '.bar{display:flex;align-items:center;justify-content:space-between;padding:10px 12px 10px 16px;background:#111;color:#fff;font:600 14px/1.2 Inter,sans-serif}',
      '.bar button{border:0;background:transparent;color:#fff;font-size:20px;cursor:pointer}',
      'iframe{border:0;flex:1;width:100%;background:#f5f5f5}',
      '</style>',
      '<button class="btn" type="button" aria-label="Открыть чат Energytool"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" stroke-width="2" aria-hidden="true"><path d="M5 6.5h14v8.5H8.5L5 18z"/></svg></button>',
      '<section class="panel" aria-label="Чат Energytool">',
      '<div class="bar"><span>Energytool</span><button type="button" aria-label="Закрыть чат">×</button></div>',
      '<iframe title="Консультант Energytool" src="about:blank"></iframe>',
      '</section>',
    ].join('');
    document.body.appendChild(host);

    var button = root.querySelector('.btn');
    var panel = root.querySelector('.panel');
    var frame = root.querySelector('iframe');
    var close = root.querySelector('.bar button');
    var opened = false;

    function show(on) {
      opened = on;
      panel.classList.toggle('open', on);
      button.setAttribute('aria-expanded', on ? 'true' : 'false');
      if (on && frame.getAttribute('src') === 'about:blank') frame.src = origin + '/?embed=1';
    }

    button.addEventListener('click', function () { show(!opened); });
    close.addEventListener('click', function () { show(false); });
  }

  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();

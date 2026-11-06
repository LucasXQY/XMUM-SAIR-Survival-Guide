/* XMUM SAIR 生存指南 — 小帮手 chat window. Questions go to the helper service (assistant/ in the repo); the first question of
   a session needs one human check (Turnstile). The conversation stays in this tab only (sessionStorage). */
(function () {
  'use strict';
  var root = document.getElementById('helper');
  if (!root) return;
  var endpoint = root.dataset.url.replace(/\/$/, '') + '/chat';
  var siteKey = root.dataset.sitekey;
  var KEY = 'helper-chat';
  var EXAMPLES = ['COM107 有往年试卷吗？', '哪里有讲傅里叶变换的资料？', 'EEE308 的课程评价怎么样？', 'How do I upload my notes?'];

  function load() {
    try { var s = JSON.parse(sessionStorage.getItem(KEY)); if (s && Array.isArray(s.messages)) return s; } catch (e) { /* private mode */ }
    return { messages: [], session: '' };
  }
  var state = load();
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* the chat still works */ } }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function escapeHtml(s) { return s.replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function rich(text) {   // escaped text; [label](url) becomes a link only for this site or its GitHub organisation; **bold**
    return escapeHtml(text)
      .replace(/\[([^\]]+)\]\((https:\/\/(?:xmum-sair\.github\.io|github\.com\/xmum-sair)\/[^)\s]*)\)/g, '<a href="$2">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  var btn = el('button', 'helper-btn', '💬 小帮手');
  btn.type = 'button';
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-controls', 'helper-panel');
  var panel = el('section', 'helper-panel');
  panel.id = 'helper-panel';
  panel.hidden = true;
  panel.setAttribute('aria-label', '小帮手 | Helper');
  var head = el('div', 'helper-head');
  head.appendChild(el('strong', null, '小帮手 | Helper'));
  var fresh = el('button', 'helper-link', '新对话 | New');
  fresh.type = 'button';
  var close = el('button', 'helper-link', '✕');
  close.type = 'button';
  close.setAttribute('aria-label', '关闭 | Close');
  head.appendChild(fresh);
  head.appendChild(close);
  var log = el('div', 'helper-log');
  log.setAttribute('aria-live', 'polite');
  var verify = el('div', 'helper-verify');
  verify.hidden = true;
  var form = el('form', 'helper-form');
  var input = el('textarea');
  input.maxLength = 500;
  input.rows = 2;
  input.placeholder = '问课程、资料、评价、怎么用本站… | Ask about courses, material, reviews, the site…';
  var send = el('button', 'btn big', '发送 | Send');
  send.type = 'submit';
  form.appendChild(input);
  form.appendChild(send);
  var note = el('p', 'helper-note', '回答由 AI 生成，可能出错；只回答本站和课程、学习相关的问题，不帮做作业和试卷题。| AI answers can be wrong. Site and study questions only; no homework solving.');
  [head, log, verify, form, note].forEach(function (x) { panel.appendChild(x); });
  root.appendChild(btn);
  root.appendChild(panel);

  function bubble(role, html) { var b = el('div', 'helper-msg ' + role); b.innerHTML = html; log.appendChild(b); log.scrollTop = log.scrollHeight; return b; }
  function render() {
    log.innerHTML = '';
    if (!state.messages.length) {
      bubble('assistant', rich('你好！我可以帮你找课程资料、看课程评价、解释知识点，或者说明怎么上传和评价。试试：\nHi! I can find course material, show reviews, explain concepts, or explain how the site works. Try:'));
      var ex = el('div', 'helper-examples');
      EXAMPLES.forEach(function (q) {
        var c = el('button', 'chip', q);
        c.type = 'button';
        c.addEventListener('click', function () { input.value = q; input.focus(); });
        ex.appendChild(c);
      });
      log.appendChild(ex);
    }
    state.messages.forEach(function (m) { bubble(m.role, m.role === 'user' ? escapeHtml(m.content).replace(/\n/g, '<br>') : rich(m.content)); });
  }
  function setOpen(open) {
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) { render(); input.focus(); }
  }
  btn.addEventListener('click', function () { setOpen(panel.hidden); });
  close.addEventListener('click', function () { setOpen(false); btn.focus(); });
  fresh.addEventListener('click', function () { state.messages = []; save(); render(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) { setOpen(false); btn.focus(); } });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });

  var turnstileLoading = null;
  function human(done) {   // one Turnstile check; the token goes along with the waiting question
    verify.hidden = false;
    verify.innerHTML = '';
    verify.appendChild(el('p', 'helper-note', '第一次提问前请完成人机验证 | Please complete the human check first'));
    var box = el('div');
    verify.appendChild(box);
    turnstileLoading = turnstileLoading || new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      s.async = true;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
    turnstileLoading.then(function () {
      window.turnstile.render(box, { sitekey: siteKey, callback: function (token) { verify.hidden = true; done(token); } });
    }).catch(function () { verify.appendChild(el('p', 'helper-note', '验证组件加载失败，请刷新 | The check failed to load; please refresh')); });
  }

  var busy = false;
  function ask(token) {
    busy = true;
    send.disabled = true;
    var wait = bubble('assistant wait', '思考中… | Thinking…');
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: state.messages.slice(-11), session: state.session, turnstile: token || undefined })
    }).then(function (r) { return r.json().then(function (d) { return { status: r.status, d: d }; }); })
      .then(function (res) {
        wait.remove();
        if (res.d.session) state.session = res.d.session;
        if (res.status === 200) {
          state.messages.push({ role: 'assistant', content: res.d.reply });
          save();
          render();
        } else if (res.status === 401 && res.d.error === 'verify') {
          state.session = '';
          human(function (t) { ask(t); });
          return;
        } else {
          state.messages.pop();                  // keep the history alternating: the unanswered question is dropped
          save();
          render();
          bubble('assistant notice', rich(res.d.message || '出错了，稍后再试 | Something went wrong; try again later'));
        }
        busy = false;
        send.disabled = false;
      })
      .catch(function () {
        wait.remove();
        state.messages.pop();
        save();
        render();
        bubble('assistant notice', rich('连不上小帮手，稍后再试 | Cannot reach the helper; try again later'));
        busy = false;
        send.disabled = false;
      });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (!q || busy) return;
    input.value = '';
    state.messages.push({ role: 'user', content: q });
    save();
    render();
    ask();
  });
})();

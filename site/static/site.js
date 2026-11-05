/* XMUM SAIR 生存指南 — page-wide behaviour: the current header block and the light/dark toggle (search is in search.js). */
(function () {
  'use strict';
  var root = document.documentElement;
  var base = document.body.dataset.base || '/';

  // 1. mark the header block that covers the current URL
  var here = location.pathname.replace(/\/index\.html$/, '/');
  var best = null;
  document.querySelectorAll('.nav-blocks a[href]').forEach(function (a) {
    var p = a.getAttribute('href');
    if (p.indexOf('http') === 0 || p === base) return;
    if (here === p || here.indexOf(p) === 0) {
      if (!best || p.length > best.getAttribute('href').length) best = a;
    }
  });
  if (best) best.setAttribute('aria-current', 'page');

  // 2. light / dark: follow the system unless the visitor chose; the choice is kept in localStorage
  function stored() { try { return localStorage.getItem('theme'); } catch (e) { return null; } }
  function effective() {
    var t = stored();
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function tellGiscus(theme) {
    var frame = document.querySelector('iframe.giscus-frame');
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ giscus: { setConfig: { theme: theme } } }, 'https://giscus.app');
    }
  }
  var btn = document.querySelector('.theme-toggle');
  function paint() {
    var t = effective();
    if (btn) {
      btn.textContent = t === 'dark' ? '☀️' : '🌙';
      btn.setAttribute('aria-label', t === 'dark' ? '切换到浅色 | Switch to light' : '切换到深色 | Switch to dark');
      btn.title = btn.getAttribute('aria-label');
    }
    tellGiscus(t);
  }
  if (btn) {
    btn.addEventListener('click', function () {
      var next = effective() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* private mode: the choice lasts for this page only */ }
      paint();
    });
  }
  paint();

  // 3. lecturer finder: cards filter as you type; Enter opens the first match
  var q = document.getElementById('lect-q');
  if (q) {
    var cards = Array.prototype.slice.call(document.querySelectorAll('.card.lect'));
    var none = document.getElementById('lect-none');
    var filter = function () {
      var s = q.value.trim().toLowerCase(), shown = 0;
      cards.forEach(function (c) {
        var hit = !s || c.dataset.name.indexOf(s) >= 0 || c.dataset.codes.indexOf(s) >= 0;
        c.hidden = !hit;
        if (hit) shown++;
      });
      if (none) none.hidden = !(s && shown === 0);
    };
    q.addEventListener('input', filter);
    if (q.form) {
      q.form.addEventListener('submit', function (e) {
        e.preventDefault();
        var first = cards.filter(function (c) { return !c.hidden; })[0];
        if (first) location.href = first.href;
      });
    }
    var want = new URLSearchParams(location.search).get('q');
    if (want) { q.value = want; filter(); }
  }

  // 4. /rate/: type a course or lecturer, get one row per (course, lecturer) with a Rate button
  var rq = document.getElementById('rate-q'), results = document.getElementById('rate-results');
  if (rq && results) {
    var pairs = null;
    var mk = function (tag, cls, text) { var el = document.createElement(tag); if (cls) el.className = cls; if (text) el.textContent = text; return el; };
    var show = function () {
      var s = rq.value.trim().toLowerCase();
      while (results.firstChild) results.removeChild(results.firstChild);
      if (!s) { results.appendChild(mk('p', 'muted', '输入后这里会列出匹配的课程和老师。| Matches appear here as you type.')); return; }
      var hits = pairs.filter(function (p) { return p.hay.indexOf(s) >= 0; }).slice(0, 40);
      if (!hits.length) { results.appendChild(mk('p', 'muted', '没有匹配的课程或老师。| Nothing matches.')); return; }
      hits.forEach(function (p) {
        var row = mk('div', 'rate-row');
        row.appendChild(mk('span', 'rate-course', p.code + ' ' + p.name));
        row.appendChild(mk('span', 'rate-lect', p.lecturer || '老师未知 | lecturer unknown'));
        var rateBtn = mk('a', 'btn', '打分 | Rate');
        rateBtn.href = results.dataset.form + '&code=' + encodeURIComponent(p.code) + (p.lecturer ? '&lecturer=' + encodeURIComponent(p.lecturer) : '');
        row.appendChild(rateBtn);
        results.appendChild(row);
      });
    };
    var ready = function () {
      if (pairs) { show(); return; }
      fetch(base + 'search.json').then(function (r) { return r.json(); }).then(function (d) {
        pairs = [];
        d.courses.forEach(function (c) {
          var names = c.lecturers && c.lecturers.length ? c.lecturers : [''];
          names.forEach(function (l) {
            pairs.push({ code: c.code, name: c.name, lecturer: l, hay: (c.code + ' ' + c.name + ' ' + l).toLowerCase() });
          });
        });
        show();
      }).catch(function () { results.appendChild(mk('p', 'muted', '课程列表加载失败，请刷新。| Course list failed to load; please refresh.')); });
    };
    rq.addEventListener('input', ready);
    rq.addEventListener('focus', ready);
    if (rq.form) rq.form.addEventListener('submit', function (e) { e.preventDefault(); ready(); });
    var pre = new URLSearchParams(location.search).get('q');
    if (pre) { rq.value = pre; ready(); }
  }
  // giscus arrives after this script: once its iframe exists, tell it the chosen theme
  if (stored() && !document.querySelector('iframe.giscus-frame') && window.MutationObserver) {
    var mo = new MutationObserver(function () {
      var f = document.querySelector('iframe.giscus-frame');
      if (f) { f.addEventListener('load', function () { tellGiscus(effective()); }); mo.disconnect(); }
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }
})();

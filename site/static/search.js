/* XMUM SAIR 生存指南 — client-side search over search.json (home page only). */
(function () {
  'use strict';
  var base = document.body.dataset.base || '/';
  var form = document.getElementById('search');
  var input = document.getElementById('q');
  var results = document.getElementById('results');
  if (!form || !input || !results) return;

  var index = null, loading = null, timer = null;

  function load() {
    if (!loading) {
      loading = fetch(base + 'search.json').then(function (r) { return r.json(); })
        .then(function (d) { index = d; return d; });
    }
    return loading;
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function link(href, text, cls) { var a = el('a', cls, text); a.href = href; return a; }
  function hay(parts) { return parts.join(' ').toLowerCase(); }

  function render(q) {
    results.replaceChildren();
    q = q.trim().toLowerCase();
    if (!q) return;
    var courses = index.courses.filter(function (c) {
      return hay([c.code, c.name, c.lecturers.join(' ')]).indexOf(q) !== -1;
    }).slice(0, 20);
    var files = index.files.filter(function (f) {   // file contents count too, through the topic index
      return hay([f.code, f.course, f.session, f.type, f.name, (f.topics || []).join(' '), f.about || '']).indexOf(q) !== -1;
    }).slice(0, 50);
    if (!courses.length && !files.length) {
      results.append(el('p', 'empty', '没有找到 | No results'));
      return;
    }
    if (courses.length) {
      results.append(el('h2', null, '课程 | Courses'));
      var cul = el('ul', 'hits');
      courses.forEach(function (c) {
        var li = el('li');
        li.append(link(c.url, c.code + ' ' + c.name, 'hit-title'));
        var meta = [c.lecturers.join(', '), c.sessions.join(' · '), c.files + ' 份 | files']
          .filter(Boolean).join(' · ');
        li.append(el('span', 'hit-meta', meta));
        cul.append(li);
      });
      results.append(cul);
    }
    if (files.length) {
      results.append(el('h2', null, '文件 | Files'));
      var ful = el('ul', 'hits');
      files.forEach(function (f) {
        var li = el('li');
        li.append(el('span', 'hit-title', f.name));
        li.append(el('span', 'hit-meta', f.code + ' · ' + f.session + ' · ' + f.type));
        var hitTopics = (f.topics || []).filter(function (t) { return t.toLowerCase().indexOf(q) !== -1; });
        if (hitTopics.length) li.append(el('span', 'hit-topics', '知识点 | Topics: ' + hitTopics.join('、')));
        if (f.preview) li.append(link(f.preview, '预览 | Preview', 'btn'));
        li.append(link(f.download, '下载 | Download', 'btn'));
        ful.append(li);
      });
      results.append(ful);
    }
  }

  function run() {
    var q = input.value;
    var url = new URL(location.href);
    if (q.trim()) url.searchParams.set('q', q); else url.searchParams.delete('q');
    history.replaceState(null, '', url);
    load().then(function () { render(q); });
  }

  input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(run, 150); });
  form.addEventListener('submit', function (e) { e.preventDefault(); clearTimeout(timer); run(); });
  var initial = new URLSearchParams(location.search).get('q');
  if (initial) { input.value = initial; run(); }
})();

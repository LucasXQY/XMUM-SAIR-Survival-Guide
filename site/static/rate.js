/* XMUM SAIR 生存指南 — /rate/: find a course and lecturer, rate on this page. Votes go to the site's Worker
   (assistant/src/reviews.js): no account, one human check (Turnstile) per vote, one vote per browser per course and
   lecturer (a random id kept in localStorage; submitting again changes the vote). */
(function () {
  'use strict';
  var form = document.getElementById('rate-form');
  if (!form) return;
  var base = document.body.dataset.base || '/';
  var $ = function (id) { return document.getElementById(id); };
  var q = $('rate-q'), results = $('rate-results'), done = $('rate-done'), err = $('rate-error');
  var code = $('rate-code'), lect = $('rate-lecturer'), lectList = $('rate-lects'), title = $('rate-title');
  var year = $('rate-year'), term = $('rate-term'), other = $('rate-other'), confirmBox = $('rate-confirm'), verify = $('rate-verify');
  var MAIN = ['course', 'instructor', 'difficulty', 'work'], EXTRA = ['learned', 'communication', 'access', 'recommend'];
  var index = null, token = '', widget = null, loading = null;

  function mk(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function loadIndex() {
    if (!loading) loading = fetch(base + 'search.json').then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
    return loading;
  }
  function device() {   // one random id per browser; without storage every vote counts as a new browser
    try {
      var d = localStorage.getItem('rate-device');
      if (!d) { d = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now(); localStorage.setItem('rate-device', d); }
      return d;
    } catch (e) { return ''; }
  }
  function lecturersOf(c) {
    if (!index) return [];
    return (index.lecturers || []).filter(function (l) { return (l.codes || []).indexOf(c) >= 0; }).map(function (l) { return l.name; });
  }
  function fillLecturers() {
    while (lectList.firstChild) lectList.removeChild(lectList.firstChild);
    lecturersOf(code.value.trim().toUpperCase()).forEach(function (n) { var o = document.createElement('option'); o.value = n; lectList.appendChild(o); });
  }

  // the human check: one token per vote (tokens are single use), so the widget is reset after every submission
  function human() {
    if (widget !== null) { window.turnstile.reset(widget); token = ''; return; }
    var s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true;
    s.onload = function () {
      widget = window.turnstile.render(verify, { sitekey: form.dataset.sitekey, callback: function (t) { token = t; },
                                                  'expired-callback': function () { token = ''; } });
    };
    s.onerror = function () { err.textContent = '人机验证加载失败，请刷新 | The human check failed to load; please refresh'; };
    document.head.appendChild(s);
  }

  function openForm(c, name, lecturer) {
    code.value = c || '';
    lect.value = lecturer || '';
    title.textContent = c ? ('打分 | Rate: ' + c + (name ? ' ' + name : '')) : '打分 | Rate';
    fillLecturers();
    done.hidden = true;
    form.hidden = false;
    err.textContent = '';
    human();
    form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // 1. search: one row per (course, lecturer) with a Rate button
  function show() {
    var s = q.value.trim().toLowerCase();
    while (results.firstChild) results.removeChild(results.firstChild);
    if (!s) { results.appendChild(mk('p', 'muted', '输入后这里会列出匹配的课程和老师。| Matches appear here as you type.')); return; }
    var rows = [];
    index.courses.forEach(function (c) {
      var names = lecturersOf(c.code);
      (names.length ? names : ['']).forEach(function (l) {
        if ((c.code + ' ' + c.name + ' ' + l).toLowerCase().indexOf(s) >= 0) rows.push({ code: c.code, name: c.name, lecturer: l });
      });
    });
    if (!rows.length) {
      results.appendChild(mk('p', 'muted', '没有匹配的课程或老师；也可以直接填表 | Nothing matches; you can fill in the form directly.'));
      var b = mk('button', 'btn', '直接打分 | Rate anyway'); b.type = 'button';
      b.addEventListener('click', function () { openForm(s.toUpperCase().indexOf(' ') < 0 ? s.toUpperCase() : '', '', ''); });
      results.appendChild(b);
      return;
    }
    rows.slice(0, 40).forEach(function (r) {
      var row = mk('div', 'rate-row');
      row.appendChild(mk('span', 'rate-course', r.code + ' ' + r.name));
      row.appendChild(mk('span', 'rate-lect', r.lecturer || '老师未知 | lecturer unknown'));
      var btn = mk('button', 'btn', '打分 | Rate'); btn.type = 'button';
      btn.addEventListener('click', function () { openForm(r.code, r.name, r.lecturer); });
      row.appendChild(btn);
      results.appendChild(row);
    });
  }
  function ready() { loadIndex().then(show).catch(function () { results.textContent = '课程列表加载失败，请刷新 | Course list failed to load; please refresh'; }); }
  q.addEventListener('input', ready);
  q.addEventListener('focus', ready);
  if (q.form) q.form.addEventListener('submit', function (e) { e.preventDefault(); ready(); });

  // 2. the form
  code.addEventListener('change', function () { loadIndex().then(fillLecturers); });
  term.addEventListener('change', function () { other.hidden = term.value !== 'other'; if (!other.hidden) other.focus(); });
  function picked(name) { var c = form.querySelector('input[name="' + name + '"]:checked'); return c && c.value ? Number(c.value) : null; }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var scores = {}, miss = [];
    MAIN.concat(EXTRA).forEach(function (d) { var v = picked(d); if (v) scores[d] = v; });
    if (!code.value.trim()) miss.push('课程代码 | course code');
    if (!lect.value.trim()) miss.push('老师 | lecturer');
    if (MAIN.some(function (d) { return !scores[d]; })) miss.push('四个主维度 | the four main scores');
    var session = term.value === 'other' ? other.value.trim() : (year.value && term.value ? year.value + '-' + term.value : '');
    if (session && !/^\d{4}-\d{2}$/.test(session)) miss.push('学期格式 YYYY-MM | session as YYYY-MM');
    if (!confirmBox.checked) miss.push('确认 | confirmation');
    if (!token) miss.push('人机验证 | the human check');
    if (miss.length) { err.textContent = '还差 | Still needed: ' + miss.join('、'); return; }
    err.textContent = '';
    var btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    fetch(form.dataset.vote, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code.value.trim(), lecturer: lect.value.trim(), session: session, scores: scores,
                             confirm: true, device: device(), turnstile: token })
    }).then(function (r) { return r.json().then(function (d) { return { status: r.status, d: d }; }); })
      .then(function (res) {
        btn.disabled = false;
        if (res.status === 200) {
          var all = res.d.course && res.d.course.all;
          done.textContent = (res.d.replaced ? '已更新你之前的评价，谢谢！| Your earlier vote was updated, thanks! ' : '已登记，谢谢！| Recorded, thanks! ')
            + (all ? '这门课现在有 ' + all.n + ' 人评价' + (all.n < 3 ? '，满 3 人显示平均分' : '') + '。| ' + all.n + ' voter(s) for this course.' : '');
          done.hidden = false;
          form.hidden = true;
          form.reset();
          other.hidden = true;
          token = '';
          done.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }
        err.textContent = (res.d && res.d.message) || '提交失败，请稍后再试 | Could not submit; please try again later';
        human();   // a token is used up by any attempt
      })
      .catch(function () { btn.disabled = false; err.textContent = '连不上评价服务，请稍后再试 | Cannot reach the review service; try again later'; human(); });
  });

  // links from course pages and the reviews page: /rate/?code=COM107&lecturer=...
  var p = new URLSearchParams(location.search);
  if (p.get('code')) {
    loadIndex().then(function () {
      var c = p.get('code').toUpperCase(), course = (index.courses || []).filter(function (x) { return x.code === c; })[0];
      openForm(c, course ? course.name : '', p.get('lecturer') || '');
    }).catch(function () { openForm(p.get('code').toUpperCase(), '', p.get('lecturer') || ''); });
  } else if (p.get('q')) {
    q.value = p.get('q');
    ready();
  }
})();

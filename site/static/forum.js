/* XMUM SAIR 生存指南 — the discussion area. One mount point per page (.forum-app), filled from the site's Worker
   (assistant/src/forum.js). data-mode says what to show:
     full      the discussion page (/qa/): boards, search, a thread with its replies (?t=<id>), new threads and replies
     course    a course page: that course's threads, and "ask about this course"
     preview   the home page: the latest threads
     requests  the wanted page: material requests grouped by course
   Posting needs no account: one human check (Turnstile) per browser per hour, then the keyword lists and an automatic
   check decide "live", "held for a maintainer" or "sent back with a reason". Everything is drawn with textContent:
   post text never becomes HTML. */
(function () {
  'use strict';
  var app = document.querySelector('.forum-app');
  var dataEl = document.querySelector('.forum-data');
  if (!app || !dataEl) return;
  var DATA = JSON.parse(dataEl.textContent);
  var API = app.dataset.forum, MODE = app.dataset.mode || 'full', COURSE = app.dataset.course || '';
  var QA = (document.body.dataset.base || '/') + 'qa/';
  var BOARDS = DATA.boards;
  var threads = null;

  function mk(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function board(key) { return BOARDS.filter(function (b) { return b.key === key; })[0] || BOARDS[BOARDS.length - 1]; }
  function course(code) { return DATA.courses[code]; }
  function when(at) {
    var mins = Math.floor((Date.now() - Date.parse(at)) / 60000);
    if (isNaN(mins)) return '';
    if (mins < 60) return Math.max(1, mins) + ' 分钟前 | ' + Math.max(1, mins) + 'm ago';
    if (mins < 1440) return Math.floor(mins / 60) + ' 小时前 | ' + Math.floor(mins / 60) + 'h ago';
    var days = Math.floor(mins / 1440);
    return days < 30 ? days + ' 天前 | ' + days + 'd ago' : at.slice(0, 10);
  }
  function linkify(el, text) {   // URLs become links; everything else stays text
    var re = /https?:\/\/[^\s<>"'）)，。]+/g, last = 0, m;
    while ((m = re.exec(text))) {
      el.appendChild(document.createTextNode(text.slice(last, m.index)));
      var a = mk('a', '', m[0]); a.href = m[0]; a.target = '_blank'; a.rel = 'noopener nofollow ugc';
      el.appendChild(a);
      last = m.index + m[0].length;
    }
    el.appendChild(document.createTextNode(text.slice(last)));
  }
  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  function get(kind, k) { try { return (store(kind) || {}).getItem ? store(kind).getItem(k) : null; } catch (e) { return null; } }
  function set(kind, k, v) { try { store(kind).setItem(k, v); } catch (e) { /* private window: fine */ } }
  function device() {
    var d = get('localStorage', 'rate-device');
    if (!d) { d = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now(); set('localStorage', 'rate-device', d); }
    return d;
  }
  function mine() { try { return JSON.parse(get('localStorage', 'forum-mine') || '[]'); } catch (e) { return []; } }
  function remember(id) { var m = mine(); m.push(id); set('localStorage', 'forum-mine', JSON.stringify(m.slice(-200))); }
  function post(path, body) {
    return fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, data: j }; }); });
  }
  function load(path) {
    return fetch(API + path, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function threadUrl(id) { return QA + '?t=' + encodeURIComponent(id); }

  // ------------------------------------------------------------ rows

  function row(t, asLink) {
    var b = board(t.board), c = t.course && course(t.course);
    var li = mk('li', 'thread-row');
    var a = mk('a', 'thread-title', t.title);
    a.href = threadUrl(t.id);
    if (!asLink) a.addEventListener('click', function (e) { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); openThread(t.id, true); });
    li.appendChild(mk('span', 'thread-board', b.icon));
    var main = mk('span', 'thread-main');
    main.appendChild(a);
    var meta = mk('small', 'thread-meta');
    meta.appendChild(document.createTextNode(b.zh + ' · '));
    if (t.course) {
      var ca = mk(c ? 'a' : 'span', 'thread-course', t.course);
      if (c) ca.href = c.url;
      meta.appendChild(ca); meta.appendChild(document.createTextNode(' · '));
    }
    meta.appendChild(document.createTextNode((t.author || '匿名同学') + ' · 💬 ' + t.replies + ' · ' + when(t.last)));
    main.appendChild(meta);
    li.appendChild(main);
    return li;
  }
  function list(ts, asLink) {
    var ul = mk('ul', 'threads');
    ts.forEach(function (t) { ul.appendChild(row(t, asLink)); });
    return ul;
  }
  function empty(text) { return mk('p', 'muted', text); }

  // ------------------------------------------------------------ the discussion page

  var state = { board: '', q: '', sort: 'last' };
  function readQuery() {
    var p = new URLSearchParams(location.search);
    state.board = BOARDS.some(function (b) { return b.key === p.get('board'); }) ? p.get('board') : '';
    return p.get('t');
  }

  function renderFull() {
    clear(app);
    var bar = mk('div', 'forum-bar');
    var add = mk('button', 'btn big', '＋ 发新帖 | New thread'); add.type = 'button';
    add.addEventListener('click', function () { compose({ board: state.board }); });
    bar.appendChild(add);
    var q = mk('input', 'forum-search'); q.type = 'search'; q.placeholder = '搜索标题和内容 | Search'; q.value = state.q;
    q.setAttribute('aria-label', '搜索帖子 | Search threads');
    bar.appendChild(q);
    var sort = mk('select', 'forum-sort'); sort.setAttribute('aria-label', '排序 | Sort');
    [['last', '最新回复 | Latest activity'], ['new', '最新发布 | Newest'], ['open', '还没人回 | Unanswered']].forEach(function (o) {
      var op = mk('option', '', o[1]); op.value = o[0]; sort.appendChild(op);
    });
    sort.value = state.sort;
    bar.appendChild(sort);
    app.appendChild(bar);
    var chips = mk('div', 'board-filters'); chips.setAttribute('role', 'group');
    [{ key: '', zh: '全部', en: 'All', icon: '' }].concat(BOARDS).forEach(function (b) {
      var c = mk('button', 'chip' + (state.board === b.key ? ' on' : ''), (b.icon ? b.icon + ' ' : '') + b.zh);
      c.type = 'button'; c.title = b.en; c.setAttribute('aria-pressed', state.board === b.key ? 'true' : 'false');
      c.addEventListener('click', function () {
        state.board = b.key;
        try { history.replaceState(null, '', b.key ? '?board=' + b.key : location.pathname); } catch (e) { /* file:// */ }
        renderFull();
      });
      chips.appendChild(c);
    });
    app.appendChild(chips);
    var box = mk('div', 'forum-list');
    app.appendChild(box);
    function fill() {
      clear(box);
      if (threads === null) { box.appendChild(empty('帖子加载中… | Loading…')); return; }
      var needle = state.q.trim().toLowerCase();
      var ts = threads.filter(function (t) {
        return (!state.board || t.board === state.board) &&
               (!needle || (t.title + ' ' + t.excerpt + ' ' + t.course).toLowerCase().indexOf(needle) >= 0);
      });
      if (state.sort === 'new') ts = ts.slice().sort(function (a, b) { return b.at.localeCompare(a.at); });
      if (state.sort === 'open') ts = ts.filter(function (t) { return !t.replies; });
      if (!ts.length) { box.appendChild(empty(needle ? '没有找到 | Nothing found' : '这里还没有帖子，来发第一帖 | No threads yet: start one')); return; }
      box.appendChild(list(ts));
    }
    q.addEventListener('input', function () { state.q = q.value; fill(); });
    sort.addEventListener('change', function () { state.sort = sort.value; fill(); });
    fill();
  }

  // ------------------------------------------------------------ one thread

  function openThread(id, push) {
    if (MODE !== 'full') { location.href = threadUrl(id); return; }
    if (push) { try { history.pushState({ t: id }, '', '?t=' + encodeURIComponent(id)); } catch (e) { /* file:// */ } }
    clear(app);
    var back = mk('a', 'forum-back', '← 返回讨论区 | All threads'); back.href = QA;
    back.addEventListener('click', function (e) { e.preventDefault(); try { history.pushState(null, '', location.pathname); } catch (x) { /* ignore */ } renderFull(); });
    app.appendChild(back);
    var box = mk('div', 'forum-thread'); app.appendChild(box);
    box.appendChild(empty('加载中… | Loading…'));
    load('/thread?id=' + encodeURIComponent(id)).then(function (d) { drawThread(box, d); })
      .catch(function () { clear(box); box.appendChild(empty('这一帖不存在、正在审核或已被撤下。| This thread does not exist, is being checked, or was taken down.')); });
  }

  function owned(id) { return mine().indexOf(id) >= 0; }

  function actions(item, threadId) {
    var span = mk('span', 'post-actions');
    var rep = mk('button', 'linkish', '举报 | Report'); rep.type = 'button';
    rep.addEventListener('click', function () {
      if (!confirm('举报这一条？被 3 个人举报后会先隐藏，等维护者处理。\nReport this? After three reports it is hidden until a maintainer looks.')) return;
      post('/report', { id: item.id, device: device() }).then(function (r) {
        rep.textContent = r.data.counted === false ? '你已举报过 | Already reported' : '已举报，谢谢 | Reported, thanks'; rep.disabled = true;
      }).catch(function () { rep.textContent = '举报失败 | Failed'; });
    });
    span.appendChild(rep);
    if (owned(item.id)) {
      var wd = mk('button', 'linkish', '撤回 | Withdraw'); wd.type = 'button';
      wd.addEventListener('click', function () {
        if (!confirm('撤回这一条？撤回后不能恢复。\nWithdraw this? It cannot be undone.')) return;
        post('/withdraw', { id: item.id, device: device() }).then(function (r) {
          if (r.status !== 200) { wd.textContent = '撤回失败 | Failed'; return; }
          if (item.id === threadId) { renderFull(); load('').then(function (d) { threads = d.threads; renderFull(); }); }
          else openThread(threadId, false);
        });
      });
      span.appendChild(document.createTextNode(' · ')); span.appendChild(wd);
    }
    return span;
  }

  function drawThread(box, d) {
    clear(box);
    var t = d.thread, b = board(t.board), c = t.course && course(t.course);
    document.title = t.title + ' | 讨论区';
    var top = mk('p', 'dlg-cat');
    var bl = mk('a', '', b.icon + ' ' + b.zh); bl.href = QA + '?board=' + b.key; top.appendChild(bl);
    if (t.course) {
      top.appendChild(document.createTextNode(' · '));
      var cl = mk(c ? 'a' : 'span', '', t.course + (c ? ' ' + c.name : '')); if (c) cl.href = c.url; top.appendChild(cl);
    }
    box.appendChild(top);
    box.appendChild(mk('h2', 'thread-h', t.title));
    var first = mk('article', 'post post-op');
    var head = mk('p', 'post-head');
    head.appendChild(mk('strong', '', t.author || '匿名同学'));
    head.appendChild(mk('span', 'badge', '楼主 | OP'));
    head.appendChild(mk('small', 'muted', ' ' + when(t.at)));
    first.appendChild(head);
    var body = mk('div', 'post-body'); linkify(body, t.body); first.appendChild(body);
    first.appendChild(actions(t, t.id));
    box.appendChild(first);
    box.appendChild(mk('h3', '', d.replies.length ? d.replies.length + ' 条回复 | replies' : '还没有回复 | No replies yet'));
    d.replies.forEach(function (r, i) {
      var a = mk('article', 'post');
      a.id = 'r-' + r.id;
      var h = mk('p', 'post-head');
      h.appendChild(mk('strong', '', r.author || '匿名同学'));
      if (r.op) h.appendChild(mk('span', 'badge', '楼主 | OP'));
      h.appendChild(mk('small', 'muted', ' #' + (i + 1) + ' · ' + when(r.at)));
      a.appendChild(h);
      var bd = mk('div', 'post-body'); linkify(bd, r.body); a.appendChild(bd);
      a.appendChild(actions(r, t.id));
      box.appendChild(a);
    });
    box.appendChild(form({ thread: t.id }, function (r) {
      if (r.status === 'live') openThread(t.id, false);
    }));
  }

  // ------------------------------------------------------------ the posting form (new threads in a dialog, replies inline)

  var widgets = [];
  function human(box, onToken) {
    function draw() {
      widgets.push(window.turnstile.render(box, { sitekey: app.dataset.sitekey, callback: onToken, 'expired-callback': function () { onToken(''); } }));
    }
    if (window.turnstile) { draw(); return; }
    var s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true; s.onload = draw;
    s.onerror = function () { box.textContent = '人机验证加载失败，请刷新 | The human check failed to load; please refresh'; };
    document.head.appendChild(s);
  }

  function field(f, id, label, el, hint) {
    var wrap = mk('div', 'f f-' + id);
    var l = mk('label', '', label); l.htmlFor = 'ff-' + id + (f.dataset.n || '');
    el.id = l.htmlFor; el.name = id;
    wrap.appendChild(l); wrap.appendChild(el);
    if (hint) wrap.appendChild(mk('small', '', hint));
    f.appendChild(wrap);
  }
  function input(max, ph) { var i = mk('input'); i.type = 'text'; i.maxLength = max; if (ph) i.placeholder = ph; return i; }

  var formN = 0;
  // opts: { thread } for a reply, else { board, course } presets for a new thread. done(result) after a successful send.
  function form(opts, done) {
    var isReply = Boolean(opts.thread);
    var f = mk('form', 'board-form forum-form' + (isReply ? ' reply-form' : ''));
    f.dataset.n = String(++formN);
    if (isReply) f.appendChild(mk('h3', '', '回复 | Reply'));
    var sel, cin;
    if (!isReply) {
      sel = mk('select');
      BOARDS.forEach(function (b) { var o = mk('option', '', b.icon + ' ' + b.zh + ' | ' + b.en); o.value = b.key; sel.appendChild(o); });
      sel.value = opts.board || (opts.course ? 'study' : 'other');
      field(f, 'board', '板块 | Board *', sel);
      cin = input(20, '例如 EEE308，可不填 | e.g. EEE308, optional');
      cin.setAttribute('list', 'forum-courses');
      cin.value = opts.course || '';
      field(f, 'course', '相关课程 | Course', cin, '填了课程代码，帖子也会出现在那门课的页面上 | the thread also shows on that course\'s page');
      if (!document.getElementById('forum-courses')) {
        var dl = mk('datalist'); dl.id = 'forum-courses';
        Object.keys(DATA.courses).forEach(function (code) { var o = mk('option'); o.value = code; o.label = DATA.courses[code].name; dl.appendChild(o); });
        document.body.appendChild(dl);
      }
      field(f, 'title', '标题 | Title *', input(80, '一句话说清问题 | the question in one line'));
    }
    var ta = mk('textarea'); ta.rows = isReply ? 4 : 8; ta.maxLength = isReply ? 2000 : 4000;
    ta.placeholder = '只谈课程、学习和校园生活。不要贴答案、评分标准、别人的姓名学号电话。| Courses, study and campus life. No answers, marking schemes or other people\'s personal data.';
    field(f, 'body', (isReply ? '内容' : '正文') + ' | Text *', ta);
    field(f, 'author', '昵称（可不填）| Nickname (optional)', input(30, '留空显示「匿名同学」| blank shows as anonymous'));
    var ok = mk('label', 'confirm'); var cb = mk('input'); cb.type = 'checkbox';
    ok.appendChild(cb); ok.appendChild(document.createTextNode(' 我会遵守发言规则，内容会先经过审核 | I follow the rules; posts are checked before they appear'));
    f.appendChild(ok);
    var box = mk('div', 'verify'); f.appendChild(box);
    var err = mk('p', 'error'); err.setAttribute('role', 'alert'); f.appendChild(err);
    var note = mk('p', 'forum-result'); note.setAttribute('aria-live', 'polite'); f.appendChild(note);
    var go = mk('button', 'btn big', isReply ? '发送回复 | Send' : '发布 | Post'); go.type = 'submit';
    var p = mk('p'); p.appendChild(go); f.appendChild(p);
    var token = '';
    var session = get('sessionStorage', 'forum-session') || '';
    function needHuman() { if (!box.childNodes.length) human(box, function (t) { token = t; }); }
    if (!session) needHuman();
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      err.textContent = ''; note.textContent = '';
      if (!session && !token) { err.textContent = '请先完成人机验证 | Please complete the human check'; needHuman(); return; }
      var body = { kind: isReply ? 'reply' : 'thread', body: ta.value.trim(), author: f.elements.author.value.trim(), confirm: cb.checked,
                   device: device(), session: session, turnstile: token };
      if (isReply) body.thread = opts.thread;
      else { body.board = sel.value; body.course = cin.value.trim(); body.title = f.elements.title.value.trim(); }
      go.disabled = true; var label = go.textContent; go.textContent = '审核中… | Checking…';
      post('/post', body).then(function (r) {
        go.disabled = false; go.textContent = label;
        if (r.data.session) { session = r.data.session; set('sessionStorage', 'forum-session', session); }
        if (r.status === 401) { session = ''; set('sessionStorage', 'forum-session', ''); token = ''; err.textContent = r.data.message; needHuman(); return; }
        if (r.status !== 200) { err.textContent = r.data.message || '发送失败 | Failed'; return; }
        remember(r.data.id);
        var reason = [r.data.reason_zh, r.data.reason_en].filter(Boolean).join(' | ');
        if (r.data.status === 'live') { f.reset(); note.textContent = '已发布 ✓ | Posted'; }
        else if (r.data.status === 'pending') { f.reset(); note.textContent = '已提交，等维护者看一眼后出现，通常一两天。| Sent; it appears once a maintainer has looked, usually within a day or two.' + (reason ? ' ' + reason : ''); }
        else note.textContent = '没有发出：' + (reason || '内容不符合规则') + ' 改一下再发即可；觉得判断错了，发邮件到 xieqiyi@ieee.org。| Not posted. Edit and try again; if you think this is wrong, email xieqiyi@ieee.org.';
        if (done) done(r.data);
      }).catch(function () { go.disabled = false; go.textContent = label; err.textContent = '网络出错，请稍后再试 | Network error; try again later'; });
    });
    return f;
  }

  var dlg = null;
  function compose(opts) {
    if (!dlg) {
      dlg = mk('dialog', 'board-dialog dlg-form');
      dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
      document.body.appendChild(dlg);
    }
    clear(dlg);
    var x = mk('button', 'dlg-close', '×'); x.type = 'button'; x.setAttribute('aria-label', '关闭 | Close');
    x.addEventListener('click', function () { dlg.close(); });
    dlg.appendChild(x);
    dlg.appendChild(mk('h2', '', '发新帖 | New thread'));
    dlg.appendChild(mk('p', 'muted', '不用登录，不用 GitHub 账号。发出前会先自动审核：没问题直接出现，拿不准的等维护者看。| No login and no GitHub account. Each post is checked first: fine ones appear at once, unsure ones wait for a maintainer.'));
    dlg.appendChild(form(opts, function (r) {
      if (r.status !== 'live') return;
      dlg.close();
      if (MODE === 'full') openThread(r.id, true); else location.href = threadUrl(r.id);
    }));
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  }

  // ------------------------------------------------------------ the other pages

  function renderCourse() {
    clear(app);
    var ts = (threads || []).filter(function (t) { return t.course === COURSE; });
    var add = mk('button', 'btn', '＋ 就这门课提问 | Ask about this course'); add.type = 'button';
    add.addEventListener('click', function () { compose({ course: COURSE }); });
    var p = mk('p', 'forum-bar'); p.appendChild(add); app.appendChild(p);
    if (threads === null) app.appendChild(empty('帖子加载中… | Loading…'));
    else if (!ts.length) app.appendChild(empty('这门课还没有帖子 | No threads about this course yet'));
    else app.appendChild(list(ts.slice(0, 15), true));
  }

  function renderPreview() {
    clear(app);
    if (threads === null) return;
    if (!threads.length) { app.appendChild(empty('还没有帖子，来发第一帖 | No threads yet: start one')); return; }
    app.appendChild(list(threads.slice(0, Number(app.dataset.preview || 5)), true));
  }

  function renderRequests() {
    clear(app);
    var rs = (threads || []).filter(function (t) { return t.board === 'requests'; });
    if (!rs.length) return;
    var by = {};
    rs.forEach(function (t) { (by[t.course] = by[t.course] || []).push(t); });
    app.appendChild(mk('h2', '', '同学在求的资料 | Requested by students'));
    app.appendChild(mk('p', '', '讨论区「资料求助」板块里的帖子。手上有的话请上传，并在帖子里回一句。| Posts on the material-requests board. If you have it, upload it and reply in the thread.'));
    var ul = mk('ul');
    Object.keys(by).sort(function (a, b) { return by[b].length - by[a].length || (a || '~').localeCompare(b || '~'); }).forEach(function (code) {
      var li = mk('li'), c = code && course(code);
      if (c) { var a = mk('a', '', code + ' ' + c.name); a.href = c.url; li.appendChild(a); }
      else li.appendChild(document.createTextNode(code || '没写课程 | no course named'));
      li.appendChild(mk('small', '', ' ' + by[code].length + ' 人在求 | requests：'));
      by[code].forEach(function (t, i) {
        if (i) li.appendChild(document.createTextNode('、'));
        var a = mk('a', '', t.title); a.href = threadUrl(t.id); li.appendChild(a);
      });
      ul.appendChild(li);
    });
    app.appendChild(ul);
  }

  var RENDER = { full: renderFull, course: renderCourse, preview: renderPreview, requests: renderRequests };
  var render = RENDER[MODE] || renderFull;

  // ------------------------------------------------------------ start

  var open = MODE === 'full' ? readQuery() : null;
  if (open) openThread(open, false); else render();
  window.addEventListener('popstate', function () { if (MODE !== 'full') return; var id = readQuery(); if (id) openThread(id, false); else render(); });
  load('').then(function (d) { threads = d.threads || []; if (!(MODE === 'full' && new URLSearchParams(location.search).get('t'))) render(); })
    .catch(function () {
      threads = [];
      if (MODE === 'requests' || MODE === 'preview') { clear(app); if (MODE === 'preview') app.appendChild(empty('帖子暂时读不到 | Posts are not available right now')); return; }
      if (!new URLSearchParams(location.search).get('t')) { render(); app.insertBefore(empty('帖子暂时读不到，稍后再来 | Posts are not available right now; try again later'), app.firstChild); }
    });
})();

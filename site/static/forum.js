/* XMUM SAIR 生存指南 — the discussion area and the blog. One mount point per page (.forum-app), filled from the site's Worker
   (assistant/src/forum.js). data-mode says what to show:
     full      the discussion page (/qa/): boards, search, a thread with its replies (?t=<id>), new threads and replies
     blog      the blog (/blog/): post cards, one post with its comments (?p=<id>), the editor (?write=1)
     course    a course page: that course's threads and blog posts, and "ask about this course"
     preview   the home page: the latest threads
     requests  the wanted page: material requests grouped by course
   Posting needs no account: one human check (Turnstile) per browser per hour, then the keyword lists and an automatic
   check (which also looks at a blog post's images) decide "live", "held for a maintainer" or "sent back with a reason".
   Everything is drawn with textContent and createElement: post text, including a blog post's Markdown, never becomes HTML. */
(function () {
  'use strict';
  var app = document.querySelector('.forum-app');
  var dataEl = document.querySelector('.forum-data');
  if (!app || !dataEl) return;
  var DATA = JSON.parse(dataEl.textContent);
  var API = app.dataset.forum, MODE = app.dataset.mode || 'full', COURSE = app.dataset.course || '';
  var BASE = document.body.dataset.base || '/';
  var QA = BASE + 'qa/', BLOG = BASE + 'blog/';
  var BOARDS = DATA.boards, CATS = DATA.cats || [];
  var LIMIT = { images: 6, body: 20000, imageTarget: 400 * 1024, imageMax: 1000 * 1000, side: 1600 };
  var threads = null;

  function mk(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function board(key) { return BOARDS.filter(function (b) { return b.key === key; })[0] || BOARDS[BOARDS.length - 1]; }
  function cat(key) { return CATS.filter(function (c) { return c.key === key; })[0] || { key: key, zh: key, en: '', icon: '📝' }; }
  function course(code) { return DATA.courses[code]; }
  function when(at) {
    var mins = Math.floor((Date.now() - Date.parse(at)) / 60000);
    if (isNaN(mins)) return '';
    if (mins < 60) return Math.max(1, mins) + ' 分钟前 | ' + Math.max(1, mins) + 'm ago';
    if (mins < 1440) return Math.floor(mins / 60) + ' 小时前 | ' + Math.floor(mins / 60) + 'h ago';
    var days = Math.floor(mins / 1440);
    return days < 30 ? days + ' 天前 | ' + days + 'd ago' : at.slice(0, 10);
  }
  function link(text, href) { var a = mk('a', '', text); a.href = href; a.target = '_blank'; a.rel = 'noopener nofollow ugc'; return a; }
  function linkify(el, text) {   // URLs become links; everything else stays text
    var re = /https?:\/\/[^\s<>"'）)，。]+/g, last = 0, m;
    while ((m = re.exec(text))) {
      el.appendChild(document.createTextNode(text.slice(last, m.index)));
      el.appendChild(link(m[0], m[0]));
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
  function owned(id) { return mine().indexOf(id) >= 0; }
  function session() {   // the signed session from the last post or upload, '' once it has run out (the server renews it on every use)
    var s = get('sessionStorage', 'forum-session') || '';
    try { if (s && JSON.parse(atob(s.split('.')[0].replace(/-/g, '+').replace(/_/g, '/'))).exp * 1000 < Date.now() + 60000) return ''; } catch (e) { return ''; }
    return s;
  }
  function keepSession(s) { set('sessionStorage', 'forum-session', s || ''); }
  function post(path, body) {
    return fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, data: j }; }); });
  }
  function load(path) {
    return fetch(API + path, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function threadUrl(id) { return QA + '?t=' + encodeURIComponent(id); }
  function postUrl(id) { return BLOG + '?p=' + encodeURIComponent(id); }
  function imgUrl(id) { return API + '/img?id=' + encodeURIComponent(id); }
  function go(query) { try { history.pushState(null, '', query || location.pathname); } catch (e) { /* file:// */ } }
  function empty(text) { return mk('p', 'muted', text); }
  function intro(show) {   // the page's heading and rules: shown over a list, hidden over one thread, one post or the editor
    var el = document.querySelector('.forum-intro'); if (el) el.hidden = !show;
  }

  // ------------------------------------------------------------ a small, safe Markdown: headings, lists, quotes, code, links, images

  var INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\s\n][^*\n]*\*)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(https?:\/\/[^\s<>"'）)，。]+)/g;
  function inline(el, text) {
    var last = 0, m;
    INLINE.lastIndex = 0;
    while ((m = INLINE.exec(text))) {
      el.appendChild(document.createTextNode(text.slice(last, m.index)));
      var t = m[0];
      if (m[1]) el.appendChild(mk('code', '', t.slice(1, -1)));
      else if (m[2]) el.appendChild(mk('strong', '', t.slice(2, -2)));
      else if (m[3]) el.appendChild(mk('em', '', t.slice(1, -1)));
      else if (m[4]) { var k = t.indexOf(']('); el.appendChild(link(t.slice(1, k), t.slice(k + 2, -1))); }
      else el.appendChild(link(t, t));
      last = m.index + t.length;
    }
    el.appendChild(document.createTextNode(text.slice(last)));
  }
  // src(id) → the image address: the Worker's for a live post, a local preview while writing
  function markdown(box, text, src) {
    var lines = String(text).split('\n'), i = 0, para = [];
    function flush() {
      if (!para.length) return;
      var p = mk('p');
      para.forEach(function (l, j) { if (j) p.appendChild(mk('br')); inline(p, l); });
      box.appendChild(p); para = [];
    }
    while (i < lines.length) {
      var l = lines[i], m;
      if (/^```/.test(l)) {
        flush();
        var code = [];
        for (i++; i < lines.length && !/^```/.test(lines[i]); i++) code.push(lines[i]);
        var pre = mk('pre'); pre.appendChild(mk('code', '', code.join('\n'))); box.appendChild(pre);
        i++; continue;
      }
      if ((m = /^\s*!\[([^\]\n]{0,120})\]\(img:([a-f0-9]{16})\)\s*$/.exec(l))) {
        flush();
        var fig = mk('figure', 'post-figure'), img = mk('img');
        img.alt = m[1] || '图片 | image'; img.loading = 'lazy'; img.decoding = 'async';
        var s = src(m[2]);
        if (s) img.src = s; else { img.alt = '图片（发布后显示）| image (shown once posted)'; fig.classList.add('is-missing'); }
        fig.appendChild(img);
        if (m[1]) fig.appendChild(mk('figcaption', '', m[1]));
        box.appendChild(fig); i++; continue;
      }
      // # → h2, ## → h3, ### → h4 (the post's title is the h1)
      if ((m = /^(#{1,3})\s+(.+)$/.exec(l))) { flush(); var h = mk('h' + (m[1].length + 1)); inline(h, m[2]); box.appendChild(h); i++; continue; }
      if (/^>\s?/.test(l)) {
        flush();
        var q = mk('blockquote'), first = true;
        for (; i < lines.length && /^>\s?/.test(lines[i]); i++) { if (!first) q.appendChild(mk('br')); inline(q, lines[i].replace(/^>\s?/, '')); first = false; }
        box.appendChild(q); continue;
      }
      if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
        flush();
        var ordered = /^\s*\d+\./.test(l), list = mk(ordered ? 'ol' : 'ul');
        for (; i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i]); i++) { var li = mk('li'); inline(li, lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '')); list.appendChild(li); }
        box.appendChild(list); continue;
      }
      if (!l.trim()) { flush(); i++; continue; }
      para.push(l); i++;
    }
    flush();
  }

  // ------------------------------------------------------------ rows and cards

  function row(t, inPage) {
    var isPost = t.type === 'post';
    var b = isPost ? cat(t.board) : board(t.board), c = t.course && course(t.course);
    var li = mk('li', 'thread-row' + (isPost ? ' is-post' : ''));
    var a = mk('a', 'thread-title', t.title);
    a.href = isPost ? postUrl(t.id) : threadUrl(t.id);
    if (inPage) a.addEventListener('click', function (e) { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); openThread(t.id, true); });
    li.appendChild(mk('span', 'thread-board', isPost ? '📝' : b.icon));
    var main = mk('span', 'thread-main');
    main.appendChild(a);
    var meta = mk('small', 'thread-meta');
    meta.appendChild(document.createTextNode((isPost ? '博客 · ' : '') + b.zh + ' · '));
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
  function list(ts, inPage) {
    var ul = mk('ul', 'threads');
    ts.forEach(function (t) { ul.appendChild(row(t, inPage)); });
    return ul;
  }
  function card(p) {
    var c = cat(p.board);
    var a = mk('a', 'post-card'); a.href = postUrl(p.id);
    a.addEventListener('click', function (e) { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); openPost(p.id, true); });
    var cover = mk('span', 'post-cover');
    if (p.cover) { var img = mk('img'); img.src = imgUrl(p.cover); img.alt = ''; img.loading = 'lazy'; cover.appendChild(img); }
    else cover.appendChild(mk('span', 'post-cover-icon', c.icon));
    a.appendChild(cover);
    var body = mk('span', 'post-card-body');
    body.appendChild(mk('span', 'post-card-cat', c.icon + ' ' + c.zh + (p.course ? ' · ' + p.course : '')));
    body.appendChild(mk('span', 'post-card-title', p.title));
    body.appendChild(mk('span', 'post-card-excerpt', p.excerpt));
    body.appendChild(mk('span', 'post-card-meta', [p.author || '匿名同学', p.minutes + ' 分钟读完 | ' + p.minutes + ' min', '💬 ' + p.replies, when(p.at)].join(' · ')));
    a.appendChild(body);
    return a;
  }
  function chips(items, current, onPick) {
    var row = mk('div', 'board-filters'); row.setAttribute('role', 'group');
    [{ key: '', zh: '全部', en: 'All', icon: '' }].concat(items).forEach(function (b) {
      var c = mk('button', 'chip' + (current === b.key ? ' on' : ''), (b.icon ? b.icon + ' ' : '') + b.zh);
      c.type = 'button'; c.title = b.en; c.setAttribute('aria-pressed', current === b.key ? 'true' : 'false');
      c.addEventListener('click', function () { onPick(b.key); });
      row.appendChild(c);
    });
    return row;
  }

  // ------------------------------------------------------------ the discussion page

  var state = { board: '', q: '', sort: 'last', cat: '' };
  function readQuery() {
    var p = new URLSearchParams(location.search);
    state.board = BOARDS.some(function (b) { return b.key === p.get('board'); }) ? p.get('board') : '';
    state.cat = CATS.some(function (c) { return c.key === p.get('cat'); }) ? p.get('cat') : '';
    return p;
  }
  function onlyThreads() { return (threads || []).filter(function (t) { return t.type !== 'post'; }); }
  function onlyPosts() { return (threads || []).filter(function (t) { return t.type === 'post'; }); }

  function renderFull() {
    clear(app); intro(true);
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
    app.appendChild(chips(BOARDS, state.board, function (key) {
      state.board = key;
      try { history.replaceState(null, '', key ? '?board=' + key : location.pathname); } catch (e) { /* file:// */ }
      renderFull();
    }));
    var box = mk('div', 'forum-list');
    app.appendChild(box);
    function fill() {
      clear(box);
      if (threads === null) { box.appendChild(empty('帖子加载中… | Loading…')); return; }
      var needle = state.q.trim().toLowerCase();
      var ts = onlyThreads().filter(function (t) {
        return (!state.board || t.board === state.board) &&
               (!needle || (t.title + ' ' + t.excerpt + ' ' + t.course).toLowerCase().indexOf(needle) >= 0);
      });
      if (state.sort === 'new') ts = ts.slice().sort(function (a, b) { return b.at.localeCompare(a.at); });
      if (state.sort === 'open') ts = ts.filter(function (t) { return !t.replies; });
      if (!ts.length) { box.appendChild(empty(needle ? '没有找到 | Nothing found' : '这里还没有帖子，来发第一帖 | No threads yet: start one')); return; }
      box.appendChild(list(ts, true));
    }
    q.addEventListener('input', function () { state.q = q.value; fill(); });
    sort.addEventListener('change', function () { state.sort = sort.value; fill(); });
    fill();
  }

  // ------------------------------------------------------------ one thread or one blog post, with replies

  function actions(item, threadId, onGone) {
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
          onGone(item.id === threadId);
        });
      });
      span.appendChild(document.createTextNode(' · ')); span.appendChild(wd);
    }
    return span;
  }

  function author(head, name, op, at) {
    head.appendChild(mk('strong', '', name || '匿名同学'));
    if (op) head.appendChild(mk('span', 'badge', '楼主 | OP'));
    head.appendChild(mk('small', 'muted', ' ' + at));
  }

  function replies(box, d, reopen, onGone) {
    var t = d.thread;
    box.appendChild(mk('h3', '', d.replies.length ? d.replies.length + ' 条' + (t.type === 'post' ? '评论 | comments' : '回复 | replies')
                                                 : (t.type === 'post' ? '还没有评论 | No comments yet' : '还没有回复 | No replies yet')));
    d.replies.forEach(function (r, i) {
      var a = mk('article', 'post');
      a.id = 'r-' + r.id;
      var h = mk('p', 'post-head');
      author(h, r.author, r.op, '#' + (i + 1) + ' · ' + when(r.at));
      a.appendChild(h);
      var bd = mk('div', 'post-body'); linkify(bd, r.body); a.appendChild(bd);
      a.appendChild(actions(r, t.id, onGone));
      box.appendChild(a);
    });
    box.appendChild(form({ thread: t.id, comment: t.type === 'post' }, function (r) { if (r.status === 'live') reopen(); }));
  }

  function openThread(id, push) {
    if (MODE !== 'full') { location.href = threadUrl(id); return; }
    if (push) go('?t=' + encodeURIComponent(id));
    clear(app); intro(false);
    var back = mk('a', 'forum-back', '← 返回讨论区 | All threads'); back.href = QA;
    back.addEventListener('click', function (e) { e.preventDefault(); go(); renderFull(); });
    app.appendChild(back);
    var box = mk('div', 'forum-thread'); app.appendChild(box);
    box.appendChild(empty('加载中… | Loading…'));
    load('/thread?id=' + encodeURIComponent(id)).then(function (d) { drawThread(box, d); })
      .catch(function () { clear(box); box.appendChild(empty('这一帖不存在、正在审核或已被撤下。| This thread does not exist, is being checked, or was taken down.')); });
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
    var head = mk('p', 'post-head'); author(head, t.author, true, when(t.at)); first.appendChild(head);
    var body = mk('div', 'post-body'); linkify(body, t.body); first.appendChild(body);
    var gone = function (all) { if (all) { renderFull(); refresh(); } else openThread(t.id, false); };
    first.appendChild(actions(t, t.id, gone));
    box.appendChild(first);
    replies(box, d, function () { openThread(t.id, false); }, gone);
  }

  function openPost(id, push) {
    if (MODE !== 'blog') { location.href = postUrl(id); return; }
    if (push) go('?p=' + encodeURIComponent(id));
    clear(app); intro(false);
    var back = mk('a', 'forum-back', '← 返回博客 | All posts'); back.href = BLOG;
    back.addEventListener('click', function (e) { e.preventDefault(); go(); renderBlog(); });
    app.appendChild(back);
    var box = mk('article', 'blog-post'); app.appendChild(box);
    box.appendChild(empty('加载中… | Loading…'));
    load('/thread?id=' + encodeURIComponent(id)).then(function (d) { drawPost(box, d); window.scrollTo(0, 0); })
      .catch(function () { clear(box); box.appendChild(empty('这篇文章不存在、正在审核或已被撤下。| This post does not exist, is being checked, or was taken down.')); });
  }

  function drawPost(box, d) {
    clear(box);
    var t = d.thread, c = cat(t.board), cr = t.course && course(t.course);
    document.title = t.title + ' | 博客';
    var top = mk('p', 'dlg-cat');
    var cl = mk('a', '', c.icon + ' ' + c.zh); cl.href = BLOG + '?cat=' + c.key; top.appendChild(cl);
    if (t.course) {
      top.appendChild(document.createTextNode(' · '));
      var ca = mk(cr ? 'a' : 'span', '', t.course + (cr ? ' ' + cr.name : '')); if (cr) ca.href = cr.url; top.appendChild(ca);
    }
    box.appendChild(top);
    box.appendChild(mk('h1', 'blog-title', t.title));
    box.appendChild(mk('p', 'blog-meta', [t.author || '匿名同学', when(t.at), t.minutes + ' 分钟读完 | ' + t.minutes + ' min read'].join(' · ')));
    var body = mk('div', 'blog-body'); markdown(body, t.body, imgUrl); box.appendChild(body);
    var gone = function (all) { if (all) { go(); renderBlog(); refresh(); } else openPost(t.id, false); };
    box.appendChild(actions(t, t.id, gone));
    var talk = mk('section', 'blog-comments'); box.appendChild(talk);
    replies(talk, d, function () { openPost(t.id, false); }, gone);
  }

  // ------------------------------------------------------------ the human check and the short forms (new threads in a dialog, replies inline)

  function human(box, onToken) {
    function draw() { window.turnstile.render(box, { sitekey: app.dataset.sitekey, callback: onToken, 'expired-callback': function () { onToken(''); } }); }
    if (window.turnstile) { draw(); return; }
    var s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true; s.onload = draw;
    s.onerror = function () { box.textContent = '人机验证加载失败，请刷新 | The human check failed to load; please refresh'; };
    document.head.appendChild(s);
  }

  var formN = 0;
  function field(f, id, label, el, hint) {
    var wrap = mk('div', 'f f-' + id);
    var l = mk('label', '', label); l.htmlFor = 'ff-' + id + f.dataset.n;
    el.id = l.htmlFor; el.name = id;
    wrap.appendChild(l); wrap.appendChild(el);
    if (hint) wrap.appendChild(mk('small', '', hint));
    f.appendChild(wrap);
    return wrap;
  }
  function input(max, ph) { var i = mk('input'); i.type = 'text'; i.maxLength = max; if (ph) i.placeholder = ph; return i; }
  function courseList() {
    if (document.getElementById('forum-courses')) return;
    var dl = mk('datalist'); dl.id = 'forum-courses';
    Object.keys(DATA.courses).forEach(function (code) { var o = mk('option'); o.value = code; o.label = DATA.courses[code].name; dl.appendChild(o); });
    document.body.appendChild(dl);
  }
  function courseInput(f, value) {
    courseList();
    var cin = input(20, '例如 EEE308，可不填 | e.g. EEE308, optional');
    cin.setAttribute('list', 'forum-courses'); cin.value = value || '';
    field(f, 'course', '相关课程 | Course', cin, '填了课程代码，也会出现在那门课的页面上 | it also shows on that course\'s page');
    return cin;
  }
  // the bottom of every form: nickname, the promise, the human check, errors and the result, the send button.
  // send(body) → Promise of { status, data }; the caller adds its own fields to body.
  function tail(f, label, onSent, build) {
    field(f, 'author', '昵称（可不填）| Nickname (optional)', input(30, '留空显示「匿名同学」| blank shows as anonymous'));
    var ok = mk('label', 'confirm'); var cb = mk('input'); cb.type = 'checkbox';
    ok.appendChild(cb); ok.appendChild(document.createTextNode(' 我会遵守发言规则，内容会先经过审核 | I follow the rules; posts are checked before they appear'));
    f.appendChild(ok);
    var box = mk('div', 'verify'); f.appendChild(box);
    var err = mk('p', 'error'); err.setAttribute('role', 'alert'); f.appendChild(err);
    var note = mk('p', 'forum-result'); note.setAttribute('aria-live', 'polite'); f.appendChild(note);
    var btn = mk('button', 'btn big', label); btn.type = 'submit';
    var p = mk('p'); p.appendChild(btn); f.appendChild(p);
    var h = { token: '', box: box, err: err, need: function () { if (!box.childNodes.length) human(box, function (t) { h.token = t; }); } };
    if (!session()) h.need();
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      err.textContent = ''; note.textContent = '';
      if (!session() && !h.token) { err.textContent = '请先完成人机验证 | Please complete the human check'; h.need(); return; }
      var body = build();
      if (!body) return;
      body.author = f.elements.author.value.trim(); body.confirm = cb.checked; body.device = device(); body.session = session(); body.turnstile = h.token;
      btn.disabled = true; btn.textContent = '审核中… | Checking…';
      post('/post', body).then(function (r) {
        btn.disabled = false; btn.textContent = label;
        if (r.data.session) { keepSession(r.data.session); h.token = ''; }
        if (r.status === 401) { keepSession(''); h.token = ''; err.textContent = r.data.message; h.need(); return; }
        if (r.status !== 200) { err.textContent = r.data.message || '发送失败 | Failed'; return; }
        remember(r.data.id);
        var reason = [r.data.reason_zh, r.data.reason_en].filter(Boolean).join(' | ');
        if (r.data.status === 'live') note.textContent = '已发布 ✓ | Posted';
        else if (r.data.status === 'pending') note.textContent = '已提交，等维护者看一眼后出现，通常一两天。| Sent; it appears once a maintainer has looked, usually within a day or two.' + (reason ? ' ' + reason : '');
        else note.textContent = '没有发出：' + (reason || '内容不符合规则') + ' 改一下再发即可；觉得判断错了，发邮件到 xieqiyi@ieee.org。| Not posted. Edit and try again; if you think this is wrong, email xieqiyi@ieee.org.';
        if (r.data.status !== 'rejected') f.reset();
        if (onSent) onSent(r.data);
      }).catch(function () { btn.disabled = false; btn.textContent = label; err.textContent = '网络出错，请稍后再试 | Network error; try again later'; });
    });
    return h;
  }

  // opts: { thread, comment } for a reply, else { board, course } presets for a new thread. done(result) after a send.
  function form(opts, done) {
    var isReply = Boolean(opts.thread);
    var f = mk('form', 'board-form forum-form' + (isReply ? ' reply-form' : ''));
    f.dataset.n = String(++formN);
    if (isReply) f.appendChild(mk('h3', '', opts.comment ? '写评论 | Comment' : '回复 | Reply'));
    var sel, cin;
    if (!isReply) {
      sel = mk('select');
      BOARDS.forEach(function (b) { var o = mk('option', '', b.icon + ' ' + b.zh + ' | ' + b.en); o.value = b.key; sel.appendChild(o); });
      sel.value = opts.board || (opts.course ? 'study' : 'other');
      field(f, 'board', '板块 | Board *', sel);
      cin = courseInput(f, opts.course);
      field(f, 'title', '标题 | Title *', input(80, '一句话说清问题 | the question in one line'));
    }
    var ta = mk('textarea'); ta.rows = isReply ? 4 : 8; ta.maxLength = isReply ? 2000 : 4000;
    ta.placeholder = '只谈课程、学习和校园生活。不要贴答案、评分标准、别人的姓名学号电话。| Courses, study and campus life. No answers, marking schemes or other people\'s personal data.';
    field(f, 'body', (isReply ? '内容' : '正文') + ' | Text *', ta);
    tail(f, isReply ? '发送 | Send' : '发布 | Post', done, function () {
      var body = { kind: isReply ? 'reply' : 'thread', body: ta.value.trim() };
      if (isReply) body.thread = opts.thread;
      else { body.board = sel.value; body.course = cin.value.trim(); body.title = f.elements.title.value.trim(); }
      return body;
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

  // ------------------------------------------------------------ the blog: list, editor, images

  function renderBlog() {
    clear(app); intro(true);
    document.title = '博客 | Blog · XMUM SAIR 生存指南';
    var bar = mk('div', 'forum-bar');
    var add = mk('button', 'btn big', '✍️ 写一篇 | Write a post'); add.type = 'button';
    add.addEventListener('click', function () { go('?write=1'); editor(); });
    bar.appendChild(add);
    var q = mk('input', 'forum-search'); q.type = 'search'; q.placeholder = '搜索文章 | Search posts'; q.value = state.q;
    q.setAttribute('aria-label', '搜索文章 | Search posts');
    bar.appendChild(q);
    app.appendChild(bar);
    app.appendChild(chips(CATS, state.cat, function (key) {
      state.cat = key;
      try { history.replaceState(null, '', key ? '?cat=' + key : location.pathname); } catch (e) { /* file:// */ }
      renderBlog();
    }));
    var grid = mk('div', 'post-grid'); app.appendChild(grid);
    function fill() {
      clear(grid);
      if (threads === null) { grid.appendChild(empty('文章加载中… | Loading…')); return; }
      var needle = state.q.trim().toLowerCase();
      var ps = onlyPosts().filter(function (p) {
        return (!state.cat || p.board === state.cat) && (!needle || (p.title + ' ' + p.excerpt + ' ' + p.course).toLowerCase().indexOf(needle) >= 0);
      }).sort(function (a, b) { return b.at.localeCompare(a.at); });
      if (!ps.length) { grid.appendChild(empty(needle ? '没有找到 | Nothing found' : '这一类还没有人写，来写第一篇 | Nobody has written here yet: write the first one')); return; }
      ps.forEach(function (p) { grid.appendChild(card(p)); });
    }
    q.addEventListener('input', function () { state.q = q.value; fill(); });
    fill();
  }

  // shrink an image in the browser: long side at most 1600 px, WebP (JPEG where the browser cannot write WebP), about 400 KB.
  // Drawing it on a canvas also drops the photo's metadata (GPS position, camera, time).
  function toBlob(canvas, type, q) { return new Promise(function (res) { canvas.toBlob(res, type, q); }); }
  function shrink(file) {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return Promise.reject(new Error('只收 JPG、PNG、WebP | JPG, PNG or WebP only'));
    var open = window.createImageBitmap ? createImageBitmap(file, { imageOrientation: 'from-image' }).catch(function () { return createImageBitmap(file); })
                                        : Promise.reject(new Error('浏览器太旧，不能处理图片 | This browser cannot process images'));
    return open.then(function (bmp) {
      var side = LIMIT.side, tries = [[1, 0.82], [1, 0.7], [0.75, 0.7], [0.6, 0.65]];
      function attempt(i) {
        var scale = Math.min(1, side / Math.max(bmp.width, bmp.height)) * tries[i][0];
        var canvas = mk('canvas'); canvas.width = Math.max(1, Math.round(bmp.width * scale)); canvas.height = Math.max(1, Math.round(bmp.height * scale));
        canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
        return toBlob(canvas, 'image/webp', tries[i][1]).then(function (b) {
          return b && b.type === 'image/webp' ? b : toBlob(canvas, 'image/jpeg', tries[i][1]);
        }).then(function (b) {
          if (!b) throw new Error('图片处理失败 | Could not process the image');
          if (b.size <= LIMIT.imageTarget || i === tries.length - 1) {
            if (b.size > LIMIT.imageMax) throw new Error('图片压缩后仍然太大 | The image is still too large');
            return b;
          }
          return attempt(i + 1);
        });
      }
      return attempt(0);
    });
  }

  var DRAFT = 'blog-draft';
  var local = {};   // image id → a preview address for images uploaded on this page

  function editor() {
    if (MODE !== 'blog') { location.href = BLOG + '?write=1'; return; }
    clear(app); intro(false);
    document.title = '写博客 | Write a post · XMUM SAIR 生存指南';
    var back = mk('a', 'forum-back', '← 返回博客 | All posts'); back.href = BLOG;
    back.addEventListener('click', function (e) { e.preventDefault(); go(); renderBlog(); });
    app.appendChild(back);
    app.appendChild(mk('h2', '', '写一篇博客 | Write a post'));
    app.appendChild(mk('p', 'muted', '写你自己的经历：科研、实习、求职面经、升学申请、比赛、校园生活。可以用简单的格式，最多放 6 张图。不用登录；草稿自动保存在这个浏览器里；发出前会先审核，图片也会被检查。'
      + '| Your own experience: research, internships, job hunting, grad school, competitions, student life. Simple formatting and up to 6 images. No login; the draft is saved in this browser; every post and image is checked first.'));
    var f = mk('form', 'board-form blog-form'); f.dataset.n = String(++formN);
    var sel = mk('select');
    CATS.forEach(function (c) { var o = mk('option', '', c.icon + ' ' + c.zh + ' | ' + c.en); o.value = c.key; sel.appendChild(o); });
    field(f, 'cat', '分类 | Category *', sel);
    var cin = courseInput(f, '');
    var title = input(100, '例如：大三暑假在 XX 实习的全过程 | e.g. How I got my Year 3 internship');
    field(f, 'title', '标题 | Title *', title);
    // toolbar
    var tools = mk('div', 'md-tools'); tools.setAttribute('role', 'toolbar'); tools.setAttribute('aria-label', '格式 | Formatting');
    var ta = mk('textarea', 'md-text'); ta.rows = 18; ta.maxLength = LIMIT.body;
    ta.placeholder = '## 小标题\n正文可以分段写。**加粗**、- 列表、> 引用、[链接](https://…)。\n\n不要写别人的姓名、学号、电话；不要贴考试答案和评分标准。\n'
      + '## A heading\nParagraphs, **bold**, - lists, > quotes, [links](https://…). No one else\'s personal data; no answers or marking schemes.';
    function wrap(before, after, sample) {
      var s = ta.selectionStart, e = ta.selectionEnd, picked = ta.value.slice(s, e) || sample;
      ta.setRangeText(before + picked + after, s, e, 'end'); ta.focus(); changed();
    }
    function linePrefix(prefix) {
      var s = ta.selectionStart, start = ta.value.lastIndexOf('\n', s - 1) + 1;
      ta.setRangeText(prefix, start, start, 'end'); ta.focus(); changed();
    }
    function insertBlock(text) {
      var s = ta.selectionStart, before = ta.value.slice(0, s);
      var lead = !before || /\n\n$/.test(before) ? '' : (/\n$/.test(before) ? '\n' : '\n\n');
      ta.setRangeText(lead + text + '\n\n', s, ta.selectionEnd, 'end'); ta.focus(); changed();
    }
    [['B', '加粗 | Bold', function () { wrap('**', '**', '加粗的字'); }],
     ['H', '小标题 | Heading', function () { linePrefix('## '); }],
     ['•', '列表 | List', function () { linePrefix('- '); }],
     ['❝', '引用 | Quote', function () { linePrefix('> '); }],
     ['🔗', '链接 | Link', function () { var u = prompt('链接地址 | Link address', 'https://'); if (u && /^https?:\/\/\S+$/.test(u)) wrap('[', '](' + u + ')', '链接文字'); }]
    ].forEach(function (t) {
      var b = mk('button', 'md-btn', t[0]); b.type = 'button'; b.title = t[1]; b.setAttribute('aria-label', t[1]);
      b.addEventListener('click', t[2]); tools.appendChild(b);
    });
    var pick = mk('input'); pick.type = 'file'; pick.accept = 'image/jpeg,image/png,image/webp'; pick.multiple = true; pick.hidden = true;
    var imgBtn = mk('button', 'md-btn md-img', '🖼️ 图片 | Image'); imgBtn.type = 'button';
    imgBtn.addEventListener('click', function () { pick.click(); });
    tools.appendChild(imgBtn); tools.appendChild(pick);
    var view = mk('button', 'md-btn md-view', '👁 预览 | Preview'); view.type = 'button';
    tools.appendChild(view);
    var wrapEl = field(f, 'body', '正文 | Text *', ta, ' ');   // the hint line becomes the character and image counter
    wrapEl.insertBefore(tools, ta);
    var preview = mk('div', 'blog-body md-preview'); preview.hidden = true; wrapEl.insertBefore(preview, ta.nextSibling);
    var count = wrapEl.querySelector('small');
    var upNote = mk('p', 'muted md-upload'); upNote.setAttribute('aria-live', 'polite'); wrapEl.appendChild(upNote);
    function imageCount() { return (ta.value.match(/!\[[^\]\n]{0,120}\]\(img:[a-f0-9]{16}\)/g) || []).length; }
    function refreshCount() { count.textContent = ta.value.length + ' / ' + LIMIT.body + ' 字 · 图片 ' + imageCount() + ' / ' + LIMIT.images + ' | characters · images'; }
    view.addEventListener('click', function () {
      var on = preview.hidden;
      preview.hidden = !on; ta.hidden = on;
      view.textContent = on ? '✏️ 继续写 | Edit' : '👁 预览 | Preview';
      if (on) { clear(preview); markdown(preview, ta.value, function (id) { return local[id] || ''; }); }
    });
    // the draft, saved in this browser as you type
    var saving = null;
    function changed() {
      refreshCount();
      clearTimeout(saving);
      saving = setTimeout(function () {
        set('localStorage', DRAFT, JSON.stringify({ cat: sel.value, course: cin.value, title: title.value, body: ta.value, author: f.elements.author ? f.elements.author.value : '' }));
      }, 400);
    }
    [sel, cin, title, ta].forEach(function (el) { el.addEventListener('input', changed); el.addEventListener('change', changed); });
    var h = tail(f, '发布 | Publish', function (r) {
      if (r.status === 'rejected') return;
      set('localStorage', DRAFT, '');
      if (r.status === 'live') { go('?p=' + encodeURIComponent(r.id)); openPost(r.id, false); refresh(); }
    }, function () {
      if (imageCount() > LIMIT.images) { h.err.textContent = '图片最多 ' + LIMIT.images + ' 张 | At most ' + LIMIT.images + ' images'; return null; }
      return { kind: 'post', cat: sel.value, course: cin.value.trim(), title: title.value.trim(), body: ta.value.trim() };
    });
    f.elements.author.addEventListener('input', changed);
    var clearDraft = mk('button', 'linkish', '清空草稿 | Clear draft'); clearDraft.type = 'button';
    clearDraft.addEventListener('click', function () {
      if (!confirm('清空这篇草稿？| Clear this draft?')) return;
      f.reset(); set('localStorage', DRAFT, ''); refreshCount();
    });
    f.appendChild(clearDraft);
    // images: shrink, upload, then put a reference where the cursor is
    pick.addEventListener('change', function () {
      var files = Array.prototype.slice.call(pick.files || []);
      pick.value = '';
      var room = LIMIT.images - imageCount();
      if (files.length > room) { upNote.textContent = '最多 ' + LIMIT.images + ' 张，这次只传前 ' + Math.max(0, room) + ' 张 | At most ' + LIMIT.images + ' images'; files = files.slice(0, Math.max(0, room)); }
      if (!files.length) return;
      if (!session() && !h.token) { h.err.textContent = '上传图片前请先完成下面的人机验证 | Complete the human check below before adding images'; h.need(); return; }
      (function next(i) {
        if (i >= files.length) { upNote.textContent = files.length + ' 张图片已加入 ✓ | images added'; return; }
        upNote.textContent = '正在处理第 ' + (i + 1) + ' / ' + files.length + ' 张… | Processing image ' + (i + 1) + '…';
        shrink(files[i]).then(function (blob) {
          var headers = { 'Content-Type': blob.type, 'X-Forum-Device': device() };
          if (session()) headers['X-Forum-Session'] = session(); else headers['X-Forum-Turnstile'] = h.token;
          return fetch(API + '/img', { method: 'POST', headers: headers, body: blob })
            .then(function (r) { return r.json().then(function (j) { return { status: r.status, data: j, blob: blob }; }); });
        }).then(function (r) {
          if (r.data.session) { keepSession(r.data.session); h.token = ''; }
          if (r.status === 401) { keepSession(''); h.token = ''; h.need(); throw new Error(r.data.message); }
          if (r.status !== 200) throw new Error(r.data.message || '上传失败 | Upload failed');
          local[r.data.id] = URL.createObjectURL(r.blob);
          var alt = files[i].name.replace(/\.[^.]+$/, '').replace(/[\[\]\n]/g, '').slice(0, 40);
          insertBlock('![' + alt + '](img:' + r.data.id + ')');
          next(i + 1);
        }).catch(function (e) { upNote.textContent = '第 ' + (i + 1) + ' 张没有加入：' + e.message; });
      })(0);
    });
    app.appendChild(f);
    // bring the draft back
    try {
      var d = JSON.parse(get('localStorage', DRAFT) || 'null');
      if (d) { sel.value = d.cat || sel.value; cin.value = d.course || ''; title.value = d.title || ''; ta.value = d.body || ''; f.elements.author.value = d.author || ''; }
      if (d && (d.title || d.body)) upNote.textContent = '已恢复上次的草稿 | Your draft is back';
    } catch (e) { /* a broken draft: start fresh */ }
    refreshCount();
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
    else app.appendChild(list(ts.slice(0, 15), false));
  }

  function renderPreview() {
    clear(app);
    if (threads === null) return;
    var ts = onlyThreads();
    if (!ts.length) { app.appendChild(empty('还没有帖子，来发第一帖 | No threads yet: start one')); return; }
    app.appendChild(list(ts.slice(0, Number(app.dataset.preview || 5)), false));
  }

  function renderRequests() {
    clear(app);
    var rs = onlyThreads().filter(function (t) { return t.board === 'requests'; });
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

  // ------------------------------------------------------------ start

  var RENDER = { full: renderFull, blog: renderBlog, course: renderCourse, preview: renderPreview, requests: renderRequests };
  function route() {   // what the address asks for: a thread, a post, the editor, or the list
    var p = readQuery();
    if (MODE === 'full' && p.get('t')) { openThread(p.get('t'), false); return true; }
    if (MODE === 'blog' && p.get('p')) { openPost(p.get('p'), false); return true; }
    if (MODE === 'blog' && p.get('write')) { editor(); return true; }
    (RENDER[MODE] || renderFull)();
    return false;
  }
  function refresh() {
    return load('').then(function (d) {
      threads = d.threads || [];
      var p = new URLSearchParams(location.search);
      if (!(p.get('t') || p.get('p') || p.get('write'))) (RENDER[MODE] || renderFull)();
    });
  }
  route();
  window.addEventListener('popstate', function () { if (MODE === 'full' || MODE === 'blog') route(); });
  refresh().catch(function () {
    threads = [];
    if (MODE === 'requests' || MODE === 'preview') { clear(app); if (MODE === 'preview') app.appendChild(empty('帖子暂时读不到 | Posts are not available right now')); return; }
    var p = new URLSearchParams(location.search);
    if (!(p.get('t') || p.get('p') || p.get('write'))) { route(); app.insertBefore(empty('帖子暂时读不到，稍后再来 | Posts are not available right now; try again later'), app.firstChild); }
  });
})();

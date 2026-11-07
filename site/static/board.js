/* XMUM SAIR 生存指南 — the opportunity wall and experience posts (/opportunities/, and three notes on the home page).
   Posts come from the site's Worker (assistant/src/board.js) plus the maintainers' notes in Research-Opportunities.md,
   which build.py puts in the page. Posting needs no account: one human check (Turnstile) per post, then an automatic
   first check decides "live", "held for a maintainer" or "sent back with a reason". Everything is drawn with
   textContent: post text never becomes HTML. */
(function () {
  'use strict';
  var app = document.querySelector('.board-app');
  var dataEl = document.querySelector('.board-data');
  if (!app || !dataEl) return;
  var base = document.body.dataset.base || '/';
  var DATA = JSON.parse(dataEl.textContent);
  var CATS = DATA.cats;
  var preview = Number(app.dataset.preview || 0);
  var today = new Date().toISOString().slice(0, 10);
  var posts = [];

  function mk(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function cat(kind, key) { return (CATS[kind] || []).filter(function (c) { return c.key === key; })[0] || { key: key, zh: key, en: '', icon: '📌' }; }
  function closed(p) { return p.closed || (p.fields && p.fields.deadline && p.fields.deadline < today); }
  function when(at) {
    if (!at) return '';
    if (/^\d{4}-\d{2}$/.test(at)) return at;
    var days = Math.floor((Date.now() - Date.parse(at)) / 86400000);
    if (isNaN(days)) return '';
    if (days < 1) return '今天 | today';
    if (days < 30) return days + ' 天前 | ' + days + 'd ago';
    return at.slice(0, 10);
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
  function device() {
    try {
      var d = localStorage.getItem('rate-device');
      if (!d) { d = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now(); localStorage.setItem('rate-device', d); }
      return d;
    } catch (e) { return ''; }
  }

  // ------------------------------------------------------------ notes and post cards

  function note(p, asLink) {
    var c = cat(p.kind, p.cat);
    var el = mk(asLink ? 'a' : 'button', 'note note-' + p.cat + (closed(p) ? ' is-closed' : ''));
    if (asLink) el.href = base + 'opportunities/?p=' + encodeURIComponent(p.id); else { el.type = 'button'; el.addEventListener('click', function () { openPost(p); }); }
    var top = mk('span', 'note-top');
    top.appendChild(mk('span', 'note-cat', c.icon + ' ' + c.zh));
    if (p.pinned) top.appendChild(mk('span', 'note-pin', '📌'));
    el.appendChild(top);
    el.appendChild(mk('span', 'note-title', p.title));
    if (p.fields.org) el.appendChild(mk('span', 'note-org', p.fields.org));
    var meta = mk('span', 'note-meta');
    if (p.fields.code) meta.appendChild(mk('span', 'note-code', '🎟️ ' + p.fields.code));
    if (p.fields.deadline) meta.appendChild(mk('span', '', (closed(p) ? '已截止 ' : '截止 ') + p.fields.deadline.slice(5)));
    if (p.fields.location) meta.appendChild(mk('span', '', '📍 ' + p.fields.location));
    if (!meta.childNodes.length) meta.appendChild(mk('span', '', when(p.at)));
    el.appendChild(meta);
    return el;
  }

  function storyCard(p) {
    var c = cat('story', p.cat);
    var el = mk('button', 'story' + (p.pinned ? ' is-pinned' : ''));
    el.type = 'button';
    el.addEventListener('click', function () { openPost(p); });
    el.appendChild(mk('span', 'story-cat', (p.pinned ? '📌 ' : '') + c.icon + ' ' + c.zh));
    el.appendChild(mk('span', 'story-title', p.title));
    el.appendChild(mk('span', 'story-excerpt', p.body.replace(/\s+/g, ' ').slice(0, 140)));
    el.appendChild(mk('span', 'story-meta', [p.author || '匿名 | anonymous', when(p.at)].filter(Boolean).join(' · ')));
    return el;
  }

  function chips(kind, onPick) {
    var row = mk('div', 'board-filters');
    row.setAttribute('role', 'group');
    [{ key: '', zh: '全部', en: 'All', icon: '' }].concat(CATS[kind]).forEach(function (c, i) {
      var b = mk('button', 'chip' + (i === 0 ? ' on' : ''), (c.icon ? c.icon + ' ' : '') + c.zh);
      b.type = 'button';
      b.setAttribute('aria-pressed', i === 0 ? 'true' : 'false');
      b.title = c.en;
      b.addEventListener('click', function () {
        row.querySelectorAll('.chip').forEach(function (x) { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
        b.classList.add('on'); b.setAttribute('aria-pressed', 'true');
        onPick(c.key);
      });
      row.appendChild(b);
    });
    return row;
  }

  function sortPosts(list) {
    return list.slice().sort(function (a, b) { return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || String(b.at).localeCompare(String(a.at)); });
  }

  function render() {
    while (app.firstChild) app.removeChild(app.firstChild);
    var opps = sortPosts(posts.filter(function (p) { return p.kind === 'opp'; }));
    var open = opps.filter(function (p) { return !closed(p); });
    if (preview) {
      var latest = open.slice().sort(function (a, b) { return String(b.at).localeCompare(String(a.at)); }).slice(0, preview);
      if (!latest.length) { app.appendChild(mk('p', 'muted', '还没有新机会，来贴第一张 | Nothing yet: pin the first one')); return; }
      var row = mk('div', 'notes notes-mini');
      latest.forEach(function (p) { row.appendChild(note(p, true)); });
      app.appendChild(row);
      return;
    }
    // the wall
    var wall = mk('section', 'wall');
    wall.id = 'wall';
    wall.appendChild(mk('h2', '', '机会墙 | Opportunity wall'));
    var grid = mk('div', 'notes');
    function fillWall(key) {
      while (grid.firstChild) grid.removeChild(grid.firstChild);
      var list = open.filter(function (p) { return !key || p.cat === key; });
      if (!list.length) grid.appendChild(mk('p', 'muted', '这一类还没有，欢迎发布 | Nothing here yet: post one'));
      list.forEach(function (p) { grid.appendChild(note(p)); });
    }
    wall.appendChild(chips('opp', fillWall));
    wall.appendChild(grid);
    fillWall('');
    var old = opps.filter(closed);
    if (old.length) {
      var d = mk('details', 'board-closed');
      d.appendChild(mk('summary', '', '已截止或已关闭（' + old.length + '）| Closed (' + old.length + ')'));
      var g2 = mk('div', 'notes');
      old.forEach(function (p) { g2.appendChild(note(p)); });
      d.appendChild(g2);
      wall.appendChild(d);
    }
    app.appendChild(wall);
    // experience posts
    var sec = mk('section', 'stories-sec');
    sec.id = 'stories';
    sec.appendChild(mk('h2', '', '经验分享 | Experience posts'));
    var list = mk('div', 'stories');
    var stories = sortPosts(posts.filter(function (p) { return p.kind === 'story'; }));
    function fillStories(key) {
      while (list.firstChild) list.removeChild(list.firstChild);
      var l = stories.filter(function (p) { return !key || p.cat === key; });
      if (!l.length) list.appendChild(mk('p', 'muted', '这一类还没有人写，来写第一篇 | Nobody has written here yet'));
      l.forEach(function (p) { list.appendChild(storyCard(p)); });
    }
    sec.appendChild(chips('story', fillStories));
    sec.appendChild(list);
    fillStories('');
    app.appendChild(sec);
  }

  // ------------------------------------------------------------ the detail dialog

  var dlg = null;
  function dialog() {
    if (dlg) return dlg;
    dlg = mk('dialog', 'board-dialog');
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });   // a click on the backdrop closes it
    document.body.appendChild(dlg);
    return dlg;
  }
  function closeBtn(d) {
    var x = mk('button', 'dlg-close', '×'); x.type = 'button'; x.setAttribute('aria-label', '关闭 | Close');
    x.addEventListener('click', function () { d.close(); });
    return x;
  }

  var LABELS = { org: '机构或老师 | Organisation', location: '地点 | Location', mode: '形式 | Form', pay: '待遇 | Pay',
                 deadline: '截止 | Deadline', contact: '联系 | Contact', link: '链接 | Link', code: '内推码 | Referral code' };

  function openPost(p) {
    var d = dialog(), c = cat(p.kind, p.cat);
    while (d.firstChild) d.removeChild(d.firstChild);
    d.className = 'board-dialog dlg-' + p.cat;
    d.appendChild(closeBtn(d));
    d.appendChild(mk('p', 'dlg-cat', c.icon + ' ' + c.zh + ' · ' + c.en + (closed(p) ? ' · 已截止 | closed' : '')));
    d.appendChild(mk('h2', '', p.title));
    var dl = mk('dl', 'dlg-fields');
    ['org', 'location', 'mode', 'pay', 'deadline', 'contact', 'link', 'code'].forEach(function (k) {
      var v = p.fields[k];
      if (!v) return;
      dl.appendChild(mk('dt', '', LABELS[k]));
      var dd = mk('dd');
      if (k === 'link') { var a = mk('a', '', v); a.href = v; a.target = '_blank'; a.rel = 'noopener nofollow ugc'; dd.appendChild(a); }
      else if (k === 'code') {
        dd.appendChild(mk('code', 'refcode', v));
        var cp = mk('button', 'btn', '复制 | Copy'); cp.type = 'button';
        cp.addEventListener('click', function () {
          (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(function () { cp.textContent = '已复制 ✓ | Copied'; })
            .catch(function () { cp.textContent = '请手动复制 | Copy by hand'; });
        });
        dd.appendChild(document.createTextNode(' ')); dd.appendChild(cp);
      } else linkify(dd, v);
      dl.appendChild(dd);
    });
    if (dl.childNodes.length) d.appendChild(dl);
    var body = mk('div', 'dlg-body'); linkify(body, p.body); d.appendChild(body);
    var foot = mk('p', 'dlg-foot', [p.author || '匿名 | anonymous', when(p.at)].filter(Boolean).join(' · '));
    if (!p.pinned) {
      var rep = mk('button', 'linkish', '举报 | Report'); rep.type = 'button';
      rep.addEventListener('click', function () { report(p, rep); });
      foot.appendChild(document.createTextNode(' · ')); foot.appendChild(rep);
    }
    d.appendChild(foot);
    if (p.kind === 'opp') d.appendChild(mk('p', 'dlg-note', '信息由发布者提供，申请前请自行核实；任何要你先交钱的都是骗局。| Posted by students: check before you apply. Anything that asks you to pay first is a scam.'));
    if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', '');
    try { history.replaceState(null, '', '?p=' + encodeURIComponent(p.id)); } catch (e) { /* file:// */ }
    d.addEventListener('close', function () { try { history.replaceState(null, '', location.pathname); } catch (e) { /* ignore */ } }, { once: true });
  }

  function report(p, btn) {
    if (!confirm('举报这条帖子？被 3 个人举报后会先隐藏，等维护者处理。\nReport this post? After three reports it is hidden until a maintainer looks.')) return;
    fetch(app.dataset.board + '/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: p.id, device: device() }) })
      .then(function (r) { return r.json(); })
      .then(function (d) { btn.textContent = d.counted === false ? '你已举报过 | Already reported' : '已举报，谢谢 | Reported, thanks'; btn.disabled = true; })
      .catch(function () { btn.textContent = '举报失败，请稍后再试 | Failed, try later'; });
  }

  // ------------------------------------------------------------ the posting form

  var widget = null, token = '';
  function human(box) {
    token = '';
    if (widget !== null && window.turnstile) { window.turnstile.remove(widget); widget = null; }
    function draw() {
      widget = window.turnstile.render(box, { sitekey: app.dataset.sitekey, callback: function (t) { token = t; }, 'expired-callback': function () { token = ''; } });
    }
    if (window.turnstile) { draw(); return; }
    var s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true; s.onload = draw;
    s.onerror = function () { box.textContent = '人机验证加载失败，请刷新 | The human check failed to load; please refresh'; };
    document.head.appendChild(s);
  }

  function field(form, id, label, el, hint) {
    var wrap = mk('div', 'f f-' + id);
    var l = mk('label', '', label); l.htmlFor = 'bf-' + id;
    el.id = 'bf-' + id; el.name = id;
    wrap.appendChild(l); wrap.appendChild(el);
    if (hint) wrap.appendChild(mk('small', '', hint));
    form.appendChild(wrap);
    return wrap;
  }
  function input(type, max, ph) { var i = mk('input'); i.type = type; if (max) i.maxLength = max; if (ph) i.placeholder = ph; return i; }

  function compose(kind) {
    var d = dialog();
    while (d.firstChild) d.removeChild(d.firstChild);
    d.className = 'board-dialog dlg-form';
    d.appendChild(closeBtn(d));
    d.appendChild(mk('h2', '', kind === 'opp' ? '发布机会 | Post an opportunity' : '分享经验 | Share an experience'));
    d.appendChild(mk('p', 'muted', kind === 'opp'
      ? '不用登录。提交后自动初审：没问题直接上墙，拿不准的等维护者看。| No login. An automatic check reads it first: fine posts go up at once, unsure ones wait for a maintainer.'
      : '写你自己的经历：怎么找到的、准备了什么、过程和建议。不用登录，提交后自动初审。| Your own experience: how you found it, how you prepared, what happened, your advice. No login; checked automatically first.'));
    var form = mk('form', 'board-form');
    var sel = mk('select');
    CATS[kind].forEach(function (c) { var o = mk('option', '', c.icon + ' ' + c.zh + ' | ' + c.en); o.value = c.key; sel.appendChild(o); });
    field(form, 'cat', '分类 | Category *', sel);
    field(form, 'title', '标题 | Title *', input('text', 80, kind === 'opp' ? '例如：ACME 机器人 2027 暑期实习 | e.g. ACME Robotics summer intern 2027' : '例如：大三拿到 XX 实习的全过程 | e.g. How I got my Year 3 internship'));
    var extra = {};
    if (kind === 'opp') {
      extra.org = field(form, 'org', '机构或老师 | Organisation or lecturer', input('text', 200));
      extra.code = field(form, 'code', '内推码 | Referral code', input('text', 200, '有就填，卡片上会有复制按钮 | if any: the card gets a copy button'));
      extra.deadline = field(form, 'deadline', '截止日期 | Deadline', input('date'), '过期后自动收进「已截止」| moves to Closed after this date');
      extra.location = field(form, 'location', '地点 | Location', input('text', 200, '例如：吉隆坡 / 远程 | e.g. Kuala Lumpur / remote'));
      extra.link = field(form, 'link', '申请链接 | Application link', input('url', 200, 'https://'));
      extra.contact = field(form, 'contact', '联系方式 | Contact', input('text', 200, 'HR 或老师的工作邮箱 | a work email'), '只写公开的工作联系方式，不要写别人的私人电话 | work contacts only');
      var syncRef = function () { extra.code.classList.toggle('want', sel.value === 'referral'); };
      sel.addEventListener('change', syncRef); syncRef();
    }
    var ta = mk('textarea'); ta.rows = kind === 'opp' ? 6 : 12; ta.maxLength = 4000;
    ta.placeholder = kind === 'opp' ? '做什么、对谁开放、要求、待遇、怎么申请 | what it is, who can apply, requirements, pay, how to apply'
                                    : '可以分段写。不要写别人的姓名、学号、电话 | Paragraphs welcome. No other people\'s names, IDs or phone numbers';
    field(form, 'body', '正文 | Text *', ta);
    field(form, 'author', '署名（可不填）| Name to show (optional)', input('text', 30, '昵称或留空匿名 | a nickname, or blank for anonymous'));
    var ok = mk('label', 'confirm'); var cb = mk('input'); cb.type = 'checkbox';
    ok.appendChild(cb); ok.appendChild(document.createTextNode(' 内容真实，我有权公开，没有他人隐私 | It is accurate, mine to share, and has no one else\'s personal data'));
    form.appendChild(ok);
    var box = mk('div', 'verify'); form.appendChild(box);
    var err = mk('p', 'error'); err.setAttribute('role', 'alert'); form.appendChild(err);
    var go = mk('button', 'btn big', '提交 | Submit'); go.type = 'submit';
    var row = mk('p'); row.appendChild(go); form.appendChild(row);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      err.textContent = '';
      if (!token) { err.textContent = '请先完成人机验证 | Please complete the human check'; return; }
      var fields = {};
      Object.keys(extra).forEach(function (k) { var v = form.elements[k].value.trim(); if (v) fields[k] = v; });
      var body = { kind: kind, cat: sel.value, title: form.elements.title.value.trim(), body: ta.value.trim(), fields: fields,
                   author: form.elements.author.value.trim(), confirm: cb.checked, turnstile: token, device: device() };
      go.disabled = true; go.textContent = '初审中… | Checking…';
      fetch(app.dataset.board + '/post', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (j) { return { status: r.status, data: j }; }); })
        .then(function (r) {
          go.disabled = false; go.textContent = '提交 | Submit';
          if (r.status !== 200) { err.textContent = r.data.message || '提交失败 | Failed'; human(box); return; }
          done(d, r.data);
        })
        .catch(function () { go.disabled = false; go.textContent = '提交 | Submit'; err.textContent = '网络出错，请稍后再试 | Network error; try again later'; human(box); });
    });
    d.appendChild(form);
    if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', '');
    human(box);
  }

  function done(d, r) {
    while (d.firstChild) d.removeChild(d.firstChild);
    d.className = 'board-dialog dlg-form';
    d.appendChild(closeBtn(d));
    var reason = [r.reason_zh, r.reason_en].filter(Boolean).join(' | ');
    if (r.status === 'live') {
      d.appendChild(mk('h2', '', '已发布 🎉 | Posted'));
      d.appendChild(mk('p', '', '谢谢分享！你的帖子已经出现在页面上。| Thanks! Your post is on the page now.'));
      posts.unshift(r.post); render();
    } else if (r.status === 'pending') {
      d.appendChild(mk('h2', '', '已提交，等维护者看一眼 | Submitted, waiting for a maintainer'));
      d.appendChild(mk('p', '', '初审没能直接通过，维护者看过后就会发布，通常一两天。| The automatic check could not pass it outright; a maintainer will publish it, usually within a day or two.'));
      if (reason) d.appendChild(mk('p', 'muted', reason));
    } else {
      d.appendChild(mk('h2', '', '这一帖没有通过 | Not posted'));
      d.appendChild(mk('p', '', reason || '内容不符合发布规则。| The post does not fit the rules.'));
      d.appendChild(mk('p', 'muted', '改一下再发就可以；觉得判断错了，发邮件到 xieqiyi@ieee.org。| Edit and post again; if you think this is wrong, email xieqiyi@ieee.org.'));
    }
  }

  // ------------------------------------------------------------ start

  document.querySelectorAll('[data-compose]').forEach(function (b) {
    b.addEventListener('click', function () { compose(b.dataset.compose); });
  });
  posts = DATA.curated.slice();
  render();
  fetch(app.dataset.board, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) { posts = DATA.curated.concat((d.posts || []).map(function (p) { p.fields = p.fields || {}; return p; })); render(); })
    .catch(function () { if (!preview) app.insertBefore(mk('p', 'muted', '同学发的帖子暂时读不到，稍后再来 | Students\' posts are not available right now'), app.firstChild); })
    .then(function () {
      var id = new URLSearchParams(location.search).get('p');
      var hit = id && posts.filter(function (p) { return p.id === id; })[0];
      if (hit && !preview) openPost(hit);
    });
})();

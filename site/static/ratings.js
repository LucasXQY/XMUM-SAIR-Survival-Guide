/* XMUM SAIR 生存指南 — course ratings: fills .ratings containers from ratings.json (written by reviews.yml to the data branch).
   On /reviews/ it also runs the course search and the course panel (overall tiles + per-lecturer table). */
(function () {
  'use strict';
  var boxes = Array.prototype.slice.call(document.querySelectorAll('.ratings[data-src]'));
  if (!boxes.length) return;
  var base = document.body.dataset.base || '/';
  var LABELS = {
    course: '课程质量 Course', instructor: '老师质量 Instructor', difficulty: '难度 Difficulty', work: '作业量 Work',
    learned: '学到多少 Learned', communication: '沟通 Communication', access: '找得到老师 Access', recommend: '是否推荐 Recommend'
  };
  var SHORT = { course: '课程 Course', instructor: '老师 Instructor', difficulty: '难度 Difficulty', work: '作业 Work' };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function score(v) {
    var s = el('span', 'score');
    if (v === null || v === undefined) { s.textContent = '—'; return s; }
    var bar = el('span', 'bar');
    bar.style.setProperty('--v', (v / 5).toFixed(2));
    s.appendChild(bar);
    s.appendChild(el('span', null, v.toFixed(1)));
    return s;
  }
  function tiles(data, entry) {   // the four main dimensions as big tiles; darker = higher
    var wrap = el('div', 'tiles');
    data.main.forEach(function (d) {
      var t = el('div', 'tile'), v = entry ? entry[d] : null;
      if (v === null || v === undefined) { t.classList.add('empty'); t.appendChild(el('b', null, '—')); }
      else { t.style.setProperty('--v', ((v - 1) / 4).toFixed(2)); t.appendChild(el('b', null, v.toFixed(1))); }
      t.appendChild(el('span', null, SHORT[d] || d));
      wrap.appendChild(t);
    });
    return wrap;
  }
  function rows(data, courses, filter) {
    var out = [];
    Object.keys(data.courses).sort().forEach(function (code) {
      var lects = data.courses[code].lecturers || {};
      Object.keys(lects).forEach(function (key) {
        var r = { code: code, key: key, e: lects[key], name: (courses[code] || {}).name || '' };
        if (filter(r)) out.push(r);
      });
    });
    return out;
  }
  function table(data, list, withCourse, onCourse) {
    var dims = data.main.concat(data.dims.filter(function (d) { return data.main.indexOf(d) < 0; }));
    var t = el('table'), thead = el('thead'), tr = el('tr'), tbody = el('tbody');
    var cols = [];
    if (withCourse) cols.push({ key: 'code', label: '课程 Course' });
    cols.push({ key: 'name', label: '老师 Lecturer' });
    cols.push({ key: 'n', label: '人数 Voters' });
    dims.forEach(function (d) { cols.push({ key: d, label: LABELS[d] || d }); });
    cols.forEach(function (c) {
      var th = el('th', null, c.label);
      th.setAttribute('data-sort', c.key);
      th.addEventListener('click', function () { render(c.key); });
      tr.appendChild(th);
    });
    thead.appendChild(tr); t.appendChild(thead); t.appendChild(tbody);
    var dir = 1;
    function value(r, k) { return k === 'code' ? r.code : k === 'name' ? r.e.name : k === 'n' ? r.e.n : (r.e[k] === undefined || r.e[k] === null ? -1 : r.e[k]); }
    function render(sortKey) {
      if (sortKey) { list.sort(function (a, b) { var x = value(a, sortKey), y = value(b, sortKey); return (x < y ? -1 : x > y ? 1 : 0) * dir; }); dir = -dir; }
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      list.forEach(function (r) {
        var row = el('tr');
        if (withCourse) {
          var td = el('td'); var a = el('a', null, r.code + (r.name ? ' ' + r.name : ''));
          a.href = base + 'reviews/?c=' + encodeURIComponent(r.code);
          if (onCourse) a.addEventListener('click', function (ev) { ev.preventDefault(); onCourse(r.code); });
          td.appendChild(a); row.appendChild(td);
        }
        var td2 = el('td'); var a2 = el('a', null, r.e.name); a2.href = base + 'lecturers/' + r.key + '/'; td2.appendChild(a2); row.appendChild(td2);
        row.appendChild(el('td', 'n', r.e.n));
        dims.forEach(function (d) {
          var td3 = el('td');
          if (r.e.n < data.min_n) td3.textContent = d === dims[0] ? ('满 ' + data.min_n + ' 人显示 | shown at ' + data.min_n) : '';
          else td3.appendChild(score(r.e[d]));
          row.appendChild(td3);
        });
        tbody.appendChild(row);
      });
    }
    render();
    var wrap = el('div', 'table-wrap'); wrap.appendChild(t);
    return wrap;
  }
  function updated(data) { return el('p', 'muted', '数据更新于 | Updated ' + (data.generated || '').replace('T', ' ').replace('Z', ' UTC')); }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // a course page: overall tiles, then the lecturers of that course
  function fillCourse(box, data, courses) {
    var code = box.dataset.code, entry = data.courses[code];
    clear(box);
    if (!entry) { box.appendChild(el('p', 'muted', '还没有人评价，来做第一个 | No ratings yet; be the first.')); return; }
    box.appendChild(tiles(data, entry.all));
    if (entry.all && entry.all.n < data.min_n) box.appendChild(el('p', 'muted', entry.all.n + ' 人评价，满 ' + data.min_n + ' 人显示平均分 | ' + entry.all.n + ' rated; averages appear at ' + data.min_n));
    box.appendChild(table(data, rows(data, courses, function (r) { return r.code === code; }), false));
    box.appendChild(updated(data));
  }

  // /reviews/: search box (courses and lecturers), course panel, global table
  function setupReviews(box, data, courses, people) {
    var q = document.getElementById('rv-q'), list = document.getElementById('rv-list'), panel = document.getElementById('rv-panel');
    var codes = Object.keys(courses).sort();
    var all = document.getElementById('rv-all') || box;   // the table and its heading step aside while a course is open
    function renderTable(filter) {
      clear(box);
      var l = rows(data, courses, function (r) { return !filter || (r.code + ' ' + r.name + ' ' + r.e.name).toLowerCase().indexOf(filter) >= 0; });
      if (!l.length) { box.appendChild(el('p', 'muted', filter ? '总表里没有匹配的行 | Nothing in the table matches.' : '还没有人评价，来做第一个 | No ratings yet; be the first.')); return; }
      box.appendChild(table(data, l, true, showCourse));
      box.appendChild(updated(data));
    }
    function renderList(filter) {
      clear(list);
      if (!filter) return;
      var hits = codes.filter(function (c) { return (c + ' ' + courses[c].name + ' ' + (courses[c].lecturers || []).join(' ')).toLowerCase().indexOf(filter) >= 0; }).slice(0, 12);
      var who = people.filter(function (l) { return (l.name + ' ' + l.codes.join(' ')).toLowerCase().indexOf(filter) >= 0; }).slice(0, 8);
      if (!hits.length && !who.length) { list.appendChild(el('p', 'muted', '没有匹配的课程或老师 | No course or lecturer matches.')); return; }
      if (hits.length) {
        list.appendChild(el('p', 'rv-group', '课程 | Courses'));
        var ul = el('ul', 'rv-list');
        hits.forEach(function (c) {
          var li = el('li'), a = el('a', null, c + ' ' + courses[c].name);
          a.href = base + 'reviews/?c=' + encodeURIComponent(c);
          a.addEventListener('click', function (ev) { ev.preventDefault(); showCourse(c); });
          var e = data.courses[c];
          li.appendChild(a);
          li.appendChild(el('small', null, e && e.all ? ' · ' + e.all.n + ' 人评价 | voters' : ' · 还没有评价 | no ratings yet'));
          ul.appendChild(li);
        });
        list.appendChild(ul);
      }
      if (who.length) {   // a lecturer opens their directory page: the courses they taught, each with its review section
        list.appendChild(el('p', 'rv-group', '老师 | Lecturers'));
        var ul2 = el('ul', 'rv-list');
        who.forEach(function (l) {
          var li = el('li'), a = el('a', null, l.name);
          a.href = base + 'lecturers/' + l.slug + '/';
          li.appendChild(a);
          li.appendChild(el('small', null, ' · ' + l.codes.join(' ')));
          ul2.appendChild(li);
        });
        list.appendChild(ul2);
      }
    }
    function showCourse(code) {
      var c = courses[code] || { name: '', url: '' }, entry = data.courses[code];
      clear(panel);
      var back = el('a', 'rv-back', '← 全部课程 | All courses'); back.href = base + 'reviews/';
      back.addEventListener('click', function (ev) { ev.preventDefault(); hideCourse(); });
      panel.appendChild(back);
      var head = el('div', 'rv-head');
      var title = el('div');
      title.appendChild(el('p', 'rv-code', code));
      title.appendChild(el('p', 'rv-name', c.name || ''));
      var links = el('p', 'rv-links');
      if (c.url) { var a = el('a', 'btn', '课程页 | Course page'); a.href = c.url; links.appendChild(a); links.appendChild(document.createTextNode(' ')); }
      var rate = el('a', 'btn', '打分 | Rate'); rate.href = box.dataset.form + '&code=' + encodeURIComponent(code); links.appendChild(rate);
      title.appendChild(links);
      head.appendChild(title);
      var avg = el('div');
      avg.appendChild(el('p', 'rv-label', entry && entry.all ? '总平均 | Overall · ' + entry.all.n + ' 人 | voters' : '还没有人评价 | No ratings yet'));
      avg.appendChild(tiles(data, entry && entry.all));
      if (entry && entry.all && entry.all.n < data.min_n) avg.appendChild(el('p', 'muted', '满 ' + data.min_n + ' 人显示平均分 | averages appear at ' + data.min_n + ' voters'));
      head.appendChild(avg);
      panel.appendChild(head);
      if (entry) {
        panel.appendChild(el('h3', null, '按老师 | By lecturer'));
        panel.appendChild(table(data, rows(data, courses, function (r) { return r.code === code; }), false));
      }
      panel.hidden = false; all.hidden = true; list.hidden = true;
      var url = new URL(location.href); url.searchParams.set('c', code); history.replaceState(null, '', url);
    }
    function hideCourse() {
      panel.hidden = true; all.hidden = false; list.hidden = false;
      var url = new URL(location.href); url.searchParams.delete('c'); history.replaceState(null, '', url);
    }
    function onInput() { var s = q.value.trim().toLowerCase(); if (!panel.hidden) hideCourse(); renderList(s); renderTable(s); }
    q.addEventListener('input', onInput);
    if (q.form) q.form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var s = q.value.trim().toLowerCase();
      var exact = codes.filter(function (c) { return c.toLowerCase() === s; })[0];
      var first = exact || codes.filter(function (c) { return (c + ' ' + courses[c].name + ' ' + (courses[c].lecturers || []).join(' ')).toLowerCase().indexOf(s) >= 0; })[0];
      if (first) showCourse(first);
    });
    renderTable('');
    var want = new URLSearchParams(location.search).get('c');
    if (want && courses[want.toUpperCase()]) showCourse(want.toUpperCase());
  }

  function fail(box) { clear(box); box.appendChild(el('p', 'muted', '还没有评价数据 | No rating data yet.')); }
  var wantCourses = boxes.some(function (b) { return b.dataset.courses; });
  var coursesP = wantCourses ? fetch(boxes.filter(function (b) { return b.dataset.courses; })[0].dataset.courses).then(function (r) { return r.json(); })
    .then(function (d) { var m = {}; d.courses.forEach(function (c) { m[c.code] = c; }); return { courses: m, people: d.lecturers || [] }; })
    .catch(function () { return { courses: {}, people: [] }; }) : Promise.resolve({ courses: {}, people: [] });
  var ratingsP = fetch(boxes[0].dataset.src).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  Promise.all([ratingsP, coursesP]).then(function (res) {
    var data = res[0], idx = res[1];
    boxes.forEach(function (b) {
      if (b.hasAttribute('data-all')) setupReviews(b, data, idx.courses, idx.people);
      else if (b.dataset.code) fillCourse(b, data, idx.courses);
    });
  }).catch(function () { boxes.forEach(fail); });
})();

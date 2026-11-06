/* XMUM SAIR 生存指南 — course ratings: fills .ratings containers from ratings.json (written by reviews.yml to the data branch).
   A course page gets its overall tiles and one score card per lecturer. /reviews/ gets the search (courses and lecturers),
   the rated courses as chips, and a course panel that opens when one is picked. */
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
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function tiles(data, entry, cls) {   // the four main dimensions as tiles; darker = higher
    var wrap = el('div', 'tiles' + (cls ? ' ' + cls : ''));
    data.main.forEach(function (d) {
      var t = el('div', 'tile'), v = entry ? entry[d] : null;
      if (v === null || v === undefined) { t.classList.add('empty'); t.appendChild(el('b', null, '—')); }
      else { t.style.setProperty('--v', ((v - 1) / 4).toFixed(2)); t.appendChild(el('b', null, v.toFixed(1))); }
      t.appendChild(el('span', null, SHORT[d] || d));
      wrap.appendChild(t);
    });
    return wrap;
  }
  function lecturersOf(data, code) {
    var lects = (data.courses[code] || {}).lecturers || {};
    return Object.keys(lects).map(function (key) { return { key: key, e: lects[key] }; })
      .sort(function (a, b) { return b.e.n - a.e.n || a.e.name.localeCompare(b.e.name); });
  }
  function cards(data, list) {   // one card per lecturer: name, voters, the four main tiles, the extra dimensions in a line
    var wrap = el('div', 'lcards');
    list.forEach(function (r) {
      var c = el('div', 'lcard'), top = el('div', 'lcard-top');
      var a = el('a', 'lcard-name', r.e.name); a.href = base + 'lecturers/' + r.key + '/';
      top.appendChild(a);
      top.appendChild(el('small', null, r.e.n + ' 人评价 | voters'));
      c.appendChild(top);
      var shown = r.e.n >= data.min_n;
      c.appendChild(tiles(data, shown ? r.e : null, 'mini'));
      if (shown) {
        var extra = data.dims.filter(function (d) { return data.main.indexOf(d) < 0; }).map(function (d) {
          var v = r.e[d];
          return (LABELS[d] || d) + ' ' + (v === null || v === undefined ? '—' : v.toFixed(1));
        });
        if (extra.length) c.appendChild(el('p', 'extras', extra.join(' · ')));
      } else {
        c.appendChild(el('p', 'extras', '满 ' + data.min_n + ' 人显示分数 | scores appear at ' + data.min_n + ' voters'));
      }
      wrap.appendChild(c);
    });
    return wrap;
  }
  function updated(data) { return el('p', 'muted', '数据更新于 | Updated ' + (data.generated || '').replace('T', ' ').replace('Z', ' UTC')); }
  function belowMin(data, all) {
    return all && all.n < data.min_n ? el('p', 'muted', all.n + ' 人评价，满 ' + data.min_n + ' 人显示平均分 | ' + all.n + ' rated; averages appear at ' + data.min_n) : null;
  }

  // a course page: overall tiles, then a card per lecturer
  function fillCourse(box, data) {
    var code = box.dataset.code, entry = data.courses[code];
    clear(box);
    if (!entry) { box.appendChild(el('p', 'muted', '还没有人评价，来做第一个 | No ratings yet; be the first.')); return; }
    box.appendChild(tiles(data, entry.all));
    var note = belowMin(data, entry.all);
    if (note) box.appendChild(note);
    box.appendChild(cards(data, lecturersOf(data, code)));
    box.appendChild(updated(data));
  }

  // /reviews/: search box (courses and lecturers), rated courses as chips, course panel
  function setupReviews(box, data, courses, people) {
    var q = document.getElementById('rv-q'), list = document.getElementById('rv-list'), panel = document.getElementById('rv-panel');
    var codes = Object.keys(courses).sort();
    var all = document.getElementById('rv-all') || box;   // the chips and their heading step aside while a course is open
    var rated = Object.keys(data.courses).sort(function (a, b) {
      var x = (data.courses[a].all || {}).n || 0, y = (data.courses[b].all || {}).n || 0;
      return y - x || (a < b ? -1 : 1);
    });
    function courseLink(code, cls, label) {
      var a = el('a', cls, label);
      a.href = base + 'reviews/?c=' + encodeURIComponent(code);
      a.addEventListener('click', function (ev) { ev.preventDefault(); showCourse(code); });
      return a;
    }
    function renderChips(filter) {
      clear(box);
      var hits = rated.filter(function (c) { return !filter || (c + ' ' + ((courses[c] || {}).name || '')).toLowerCase().indexOf(filter) >= 0; });
      if (!hits.length) { box.appendChild(el('p', 'muted', filter ? '没有匹配的已评价课程 | No rated course matches.' : '还没有人评价，来做第一个 | No ratings yet; be the first.')); return; }
      var wrap = el('div', 'chips');
      hits.forEach(function (c) {
        var a = courseLink(c, 'chip', c + ' ' + ((courses[c] || {}).name || ''));
        a.appendChild(el('small', null, ((data.courses[c].all || {}).n || 0) + ' 人'));
        wrap.appendChild(a);
      });
      box.appendChild(wrap);
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
          var li = el('li'), e = data.courses[c];
          li.appendChild(courseLink(c, null, c + ' ' + courses[c].name));
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
      var note = belowMin(data, entry && entry.all);
      if (note) avg.appendChild(note);
      head.appendChild(avg);
      panel.appendChild(head);
      if (entry) {
        panel.appendChild(el('h3', null, '按老师 | By lecturer'));
        panel.appendChild(cards(data, lecturersOf(data, code)));
      }
      panel.hidden = false; all.hidden = true; list.hidden = true;
      var url = new URL(location.href); url.searchParams.set('c', code); history.replaceState(null, '', url);
    }
    function hideCourse() {
      panel.hidden = true; all.hidden = false; list.hidden = false;
      var url = new URL(location.href); url.searchParams.delete('c'); history.replaceState(null, '', url);
    }
    function onInput() { var s = q.value.trim().toLowerCase(); if (!panel.hidden) hideCourse(); renderList(s); renderChips(s); }
    q.addEventListener('input', onInput);
    if (q.form) q.form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var s = q.value.trim().toLowerCase();
      var exact = codes.filter(function (c) { return c.toLowerCase() === s; })[0];
      var first = exact || codes.filter(function (c) { return (c + ' ' + courses[c].name + ' ' + (courses[c].lecturers || []).join(' ')).toLowerCase().indexOf(s) >= 0; })[0];
      if (first) showCourse(first);
    });
    renderChips('');
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
      else if (b.dataset.code) fillCourse(b, data);
    });
  }).catch(function () { boxes.forEach(fail); });
})();

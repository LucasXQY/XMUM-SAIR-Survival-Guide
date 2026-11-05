/* XMUM SAIR 生存指南 — course ratings: fills .ratings containers from ratings.json (written by reviews.yml to the data branch). */
(function () {
  'use strict';
  var boxes = document.querySelectorAll('.ratings[data-src]');
  var grid = document.querySelector('.lect-grid[data-ratings-src]');
  if (!boxes.length && !grid) return;

  var LABELS = {
    course: '课程质量 Course', instructor: '老师质量 Instructor', difficulty: '难度 Difficulty', work: '作业量 Work',
    learned: '学到多少 Learned', communication: '沟通 Communication', access: '找得到老师 Access', recommend: '是否推荐 Recommend'
  };

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
  function rows(data, filter) {
    var out = [];
    Object.keys(data.courses).sort().forEach(function (code) {
      var lects = data.courses[code].lecturers;
      Object.keys(lects).forEach(function (key) {
        if (filter(code, key)) out.push({ code: code, key: key, e: lects[key] });
      });
    });
    return out;
  }
  function table(data, list, withCourse, withLecturer) {
    var dims = data.main.concat(data.dims.filter(function (d) { return data.main.indexOf(d) < 0; }));
    var t = el('table'), thead = el('thead'), tr = el('tr'), tbody = el('tbody');
    var cols = [];
    if (withCourse) cols.push({ key: 'code', label: '课程 Course' });
    if (withLecturer) cols.push({ key: 'name', label: '老师 Lecturer' });
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
        if (withCourse) { var td = el('td'); var a = el('a', null, r.code); a.href = (document.body.dataset.base || '/') + '?q=' + encodeURIComponent(r.code); td.appendChild(a); row.appendChild(td); }
        if (withLecturer) { var td2 = el('td'); var a2 = el('a', null, r.e.name); a2.href = (document.body.dataset.base || '/') + 'lecturers/' + r.key + '/'; td2.appendChild(a2); row.appendChild(td2); }
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
  function fill(box, data) {
    var list, node;
    if (box.hasAttribute('data-all')) {
      list = rows(data, function () { return true; });
      node = table(data, list, true, true);
    } else if (box.dataset.code) {
      list = rows(data, function (code) { return code === box.dataset.code; });
      node = table(data, list, false, true);
    } else {
      list = rows(data, function (code, key) { return key === box.dataset.lecturer; });
      node = table(data, list, true, false);
    }
    while (box.firstChild) box.removeChild(box.firstChild);
    if (!list.length) { box.appendChild(el('p', 'muted', '还没有人评价，来做第一个 | No ratings yet; be the first.')); return; }
    box.appendChild(node);
    var gen = el('p', 'muted', '数据更新于 | Updated ' + (data.generated || '').replace('T', ' ').replace('Z', ' UTC'));
    box.appendChild(gen);
  }

  var src = boxes.length ? boxes[0].dataset.src : grid.dataset.ratingsSrc;
  fetch(src).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      boxes.forEach(function (b) { fill(b, data); });
      document.dispatchEvent(new CustomEvent('ratings-loaded', { detail: data }));   // the lecturers page merges the counts
    })
    .catch(function () {
      document.dispatchEvent(new CustomEvent('ratings-loaded', { detail: null }));
      boxes.forEach(function (b) {
        while (b.firstChild) b.removeChild(b.firstChild);
        b.appendChild(el('p', 'muted', '还没有评价数据 | No rating data yet.'));
      });
    });
})();

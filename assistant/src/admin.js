// 评价管理页（/admin）：输入口令后列出标记待审的票，按课程和老师分组，可以「保留」或「丢弃」；口令只存在这个标签页里。
// The review admin page (/admin): after the token, flagged votes grouped by course and lecturer, each kept or dropped.
// The token stays in this tab (sessionStorage) and goes only to /admin/api on this Worker.
export const ADMIN_HTML = `<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>评价审核 | Review queue</title>
<style>
:root { color-scheme: light dark; --line: #d0d7de; --muted: #59636e; --accent: #0969da; }
@media (prefers-color-scheme: dark) { :root { --line: #3d444d; --muted: #9198a1; --accent: #4493f8; } }
body { font: 15px/1.5 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 960px; margin: 0 auto; padding: 16px; }
h1 { font-size: 1.3rem; } .muted { color: var(--muted); } input { font: inherit; padding: 6px 8px; width: 22em; max-width: 100%; }
button { font: inherit; padding: 4px 10px; border: 1px solid var(--accent); border-radius: 999px; background: none; color: var(--accent); cursor: pointer; }
button.drop { border-color: #cf222e; color: #cf222e; }
section { border: 1px solid var(--line); border-radius: 10px; padding: 8px 12px; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; } td, th { border-top: 1px solid var(--line); padding: 4px 6px; text-align: left; vertical-align: top; }
.flag { font-size: .78rem; padding: 0 6px; border-radius: 999px; border: 1px solid var(--line); margin-right: 4px; white-space: nowrap; }
</style></head><body>
<h1>评价审核 | Review queue</h1>
<p class="muted">被标记的票已经计入平均分；这里决定保留（标为已审）还是丢弃（从平均分里去掉）。名单外的老师或课程在保留之前，网站上只显示「待确认」。
<br>Flagged votes already count; keep marks them reviewed, drop removes them from the averages. Unlisted lecturers or courses show as "unconfirmed" until kept.</p>
<form id="login"><input id="token" type="password" placeholder="口令 | admin token" autocomplete="current-password"> <button>进入 | Open</button></form>
<p id="summary" class="muted"></p><div id="queue"></div>
<script>
(function () {
  var token = sessionStorage.getItem('reviews-admin') || '';
  var NAMES = { burst: '一小时内突增 | burst', new_name: '名单外的老师或课程 | not on the site list' };
  function api(op, extra) {
    return fetch('/admin/api', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ token: token, op: op }, extra || {})) })
      .then(function (r) { if (r.status === 401) { sessionStorage.removeItem('reviews-admin'); throw new Error('口令不对 | wrong token'); } return r.json(); });
  }
  function el(tag, text) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; }
  function act(op, keys) { api(op, { keys: keys }).then(load).catch(function (e) { alert(e.message); }); }
  function load() {
    api('summary').then(function (s) {
      document.getElementById('summary').textContent = '共 ' + s.total + ' 票 · 待审 ' + s.unreviewed + ' · 已丢弃 ' + s.dropped + ' | ' + s.total + ' votes · ' + s.unreviewed + ' to check · ' + s.dropped + ' dropped';
      return api('list');
    }).then(function (d) {
      var q = document.getElementById('queue'); q.innerHTML = '';
      if (!d.votes.length) { q.appendChild(el('p', '没有待审的票 | Nothing to check')); return; }
      var groups = {};
      d.votes.forEach(function (v) { var g = v.code + ' · ' + v.lecturer; (groups[g] = groups[g] || []).push(v); });
      Object.keys(groups).forEach(function (g) {
        var vs = groups[g], sec = el('section'), head = el('p');
        head.appendChild(el('strong', g + '（' + vs.length + '）'));
        var keep = el('button', '全部保留 | Keep all'), drop = el('button', '全部丢弃 | Drop all'); drop.className = 'drop';
        keep.onclick = function () { act('keep', vs.map(function (v) { return v.key; })); };
        drop.onclick = function () { if (confirm('丢弃这 ' + vs.length + ' 票？')) act('drop', vs.map(function (v) { return v.key; })); };
        head.appendChild(document.createTextNode(' ')); head.appendChild(keep); head.appendChild(document.createTextNode(' ')); head.appendChild(drop);
        sec.appendChild(head);
        var t = el('table'), hr = el('tr');
        ['时间 Time', '学期 Session', '分数 Scores', '标记 Flags', 'IP', '浏览器 Browser', ''].forEach(function (h) { hr.appendChild(el('th', h)); });
        t.appendChild(hr);
        vs.forEach(function (v) {
          var tr = el('tr');
          tr.appendChild(el('td', v.at.replace('T', ' ').slice(0, 16)));
          tr.appendChild(el('td', v.session || '—'));
          tr.appendChild(el('td', Object.keys(v.scores).map(function (k) { return k + ' ' + v.scores[k]; }).join(', ')));
          var f = el('td'); v.flags.forEach(function (x) { var s = el('span', NAMES[x] || x); s.className = 'flag'; f.appendChild(s); }); tr.appendChild(f);
          tr.appendChild(el('td', v.ip)); tr.appendChild(el('td', v.voter));
          var b = el('td'), k = el('button', '保留'), x = el('button', '丢弃'); x.className = 'drop';
          k.onclick = function () { act('keep', [v.key]); }; x.onclick = function () { act('drop', [v.key]); };
          b.appendChild(k); b.appendChild(document.createTextNode(' ')); b.appendChild(x); tr.appendChild(b);
          t.appendChild(tr);
        });
        sec.appendChild(t); q.appendChild(sec);
      });
    }).catch(function (e) { document.getElementById('summary').textContent = e.message; });
  }
  document.getElementById('login').onsubmit = function (e) {
    e.preventDefault(); token = document.getElementById('token').value.trim(); sessionStorage.setItem('reviews-admin', token); load();
  };
  if (token) load();
})();
</script></body></html>`;

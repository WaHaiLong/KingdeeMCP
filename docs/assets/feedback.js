/* ============================================================
   Kingdee MCP 官网 - 留言板逻辑
   留言 → 生成结构化 Markdown → 打开 GitHub 预填 Issue 页面
   纯静态、无需 token；不自动提交，由留言者点 GitHub 的 Submit。
   ============================================================ */
(function () {
  'use strict';

  var REPO = 'WaHaiLong/KingdeeMCP';
  var NEW_ISSUE = 'https://github.com/' + REPO + '/issues/new';
  var SITE = 'https://wahailong.github.io/KingdeeMCP/feedback.html';

  var form = document.getElementById('feedbackForm');
  if (!form) return;

  var overlay = document.getElementById('previewOverlay');
  var pvTitle = document.getElementById('pvTitle');
  var pvBody = document.getElementById('pvBody');
  var toast = document.getElementById('fbToast');

  function field(id) { return document.getElementById(id); }
  function val(id) { var el = field(id); return el ? el.value.trim() : ''; }

  function selectedType() {
    var checked = form.querySelector('input[name="fbType"]:checked');
    return checked ? checked.value : '';
  }

  function showToast(msg, kind) {
    if (!toast) return;
    toast.textContent = msg;
    toast.className = 'toast show' + (kind ? ' ' + kind : '');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () { toast.className = 'toast'; }, 3200);
  }

  function build() {
    var type = selectedType();
    var title = val('fbTitle');
    var content = val('fbContent');
    var name = val('fbName');
    var contact = val('fbContact');
    var expect = val('fbExpect');

    if (!type) { showToast('请选择留言类型', 'err'); return null; }
    if (!title) { showToast('请填写标题', 'err'); field('fbTitle').focus(); return null; }
    if (!content) { showToast('请填写详细内容', 'err'); field('fbContent').focus(); return null; }

    var issueTitle = '[' + type + '] ' + title;

    var lines = [];
    lines.push('> 本 Issue 由 Kingdee MCP 官网留言板生成：' + SITE);
    lines.push('');
    lines.push('## 留言类型');
    lines.push(type);
    lines.push('');
    lines.push('## 详细内容');
    lines.push(content);
    if (expect) {
      lines.push('');
      lines.push('## 期望结果');
      lines.push(expect);
    }
    lines.push('');
    lines.push('## 留言人');
    lines.push('- 称呼：' + (name || '未填写'));
    lines.push('- 联系方式：' + (contact || '未填写'));
    lines.push('');
    lines.push('---');
    lines.push('提交时间：' + new Date().toLocaleString('zh-CN', { hour12: false }));

    return { title: issueTitle, body: lines.join('\n') };
  }

  function issueUrl(data) {
    return NEW_ISSUE + '?title=' + encodeURIComponent(data.title) + '&body=' + encodeURIComponent(data.body);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
    }
    fallbackCopy(text);
    return Promise.resolve();
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var data = build();
    if (!data) return;
    pvTitle.textContent = data.title;
    pvBody.textContent = data.body;
    overlay.classList.add('show');
    overlay._issueUrl = issueUrl(data);
    overlay._issueBody = data.body;
  });

  ['pvCancel', 'pvCancel2'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', function () { overlay.classList.remove('show'); });
  });
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) overlay.classList.remove('show');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') overlay.classList.remove('show');
  });

  document.getElementById('pvOpen').addEventListener('click', function () {
    var url = overlay._issueUrl;
    if (!url) return;
    window.open(url, '_blank', 'noopener,noreferrer');
    showToast('已打开 GitHub，请点页面底部 Submit new issue 完成发布', 'ok');
    overlay.classList.remove('show');
  });

  document.getElementById('pvCopy').addEventListener('click', function () {
    var text = overlay._issueBody || '';
    var data = { title: pvTitle.textContent, body: text };
    copyText('标题：' + data.title + '\n\n' + data.body).then(function () {
      showToast('已复制，可粘贴到 QQ / 邮箱 / GitHub', 'ok');
    });
  });

  // 直接复制按钮（表单区）
  var quickCopy = document.getElementById('fbQuickCopy');
  if (quickCopy) {
    quickCopy.addEventListener('click', function () {
      var data = build();
      if (!data) return;
      copyText('标题：' + data.title + '\n\n' + data.body).then(function () {
        showToast('留言内容已复制', 'ok');
      });
    });
  }
})();

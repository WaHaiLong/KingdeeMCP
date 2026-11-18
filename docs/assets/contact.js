/* ============================================================
   Kingdee MCP 官网 - 统一"联系作者"组件逻辑
   在所有页面 </body> 前引入本文件即可，样式见 contact.css
   QQ / 邮箱改这里一处，全站四个页面同步生效
   ============================================================ */
(function () {
  'use strict';

  var QQ_NUMBER = '1724349716';
  var EMAIL = '1724349716@qq.com';
  var QQ_URL = 'https://wpa.qq.com/msgrd?v=3&uin=' + QQ_NUMBER + '&site=qq&menu=yes';

  // 避免重复注入（防止引入两次）
  if (document.getElementById('contactFab')) return;

  var svgChat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
  var svgQQ = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C7.3 2 4 5.3 4 9.6c0 1.6.5 3 1.4 4.3L4 18l3.5-1.2c1.4.9 3 1.4 4.5 1.4s3.1-.5 4.5-1.4L20 18l-1.4-4.1c.9-1.3 1.4-2.7 1.4-4.3C20 5.3 16.7 2 12 2z"/></svg>';
  var svgMail = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 7l10 6 10-6"/></svg>';
  var svgCopy = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

  function createNavContactBtn() {
    // 1) 顶部导航注入「留言板」入口（反馈页自身有 active 链接，跳过避免重复）
    var navLinks = document.querySelector('.nav-links');
    if (navLinks && !navLinks.querySelector('a[href="feedback.html"]')) {
      var li = document.createElement('li');
      var link = document.createElement('a');
      link.href = 'feedback.html';
      link.textContent = '留言板';
      li.appendChild(link);
      navLinks.appendChild(li);
    }

    // 2) GitHub 按钮前注入醒目「联系作者」按钮
    var githubBtn = document.querySelector('.github-btn');
    if (!githubBtn) return;
    var a = document.createElement('a');
    a.href = '#' ;
    a.className = 'nav-contact-btn';
    a.id = 'navContactBtn';
    a.setAttribute('aria-label', '联系作者');
    a.innerHTML = svgChat + '<span>联系作者</span>';
    a.addEventListener('click', function (e) {
      e.preventDefault();
      togglePanel(true);
    });
    githubBtn.parentNode.insertBefore(a, githubBtn);
  }

  function createWidget() {
    var fab = document.createElement('button');
    fab.type = 'button';
    fab.id = 'contactFab';
    fab.className = 'contact-fab';
    fab.setAttribute('aria-label', '联系作者');
    fab.innerHTML = svgChat + '<span>联系作者</span><span class="fab-pulse"></span>';

    var panel = document.createElement('div');
    panel.id = 'contactPanel';
    panel.className = 'contact-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', '联系方式');
    panel.innerHTML =
      '<div class="cp-head">' +
        '<div>' +
          '<div class="cp-title">联系作者</div>' +
          '<div class="cp-subtitle">技术咨询 · 定制开发 · 商务合作</div>' +
        '</div>' +
        '<button type="button" class="cp-close" id="cpClose" aria-label="关闭">&times;</button>' +
      '</div>' +

      '<div class="cp-row">' +
        '<div class="cp-row-icon">' + svgQQ + '</div>' +
        '<div class="cp-row-body">' +
          '<div class="cp-row-label">QQ</div>' +
          '<div class="cp-row-value">' + QQ_NUMBER + '</div>' +
        '</div>' +
        '<button type="button" class="cp-copy" data-copy="' + QQ_NUMBER + '" aria-label="复制QQ">' + svgCopy + '</button>' +
      '</div>' +

      '<div class="cp-row">' +
        '<div class="cp-row-icon mail">' + svgMail + '</div>' +
        '<div class="cp-row-body">' +
          '<div class="cp-row-label">邮箱</div>' +
          '<div class="cp-row-value">' + EMAIL + '</div>' +
        '</div>' +
        '<button type="button" class="cp-copy" data-copy="' + EMAIL + '" aria-label="复制邮箱">' + svgCopy + '</button>' +
      '</div>' +

      '<div class="cp-actions">' +
        '<a class="cp-action primary" href="' + QQ_URL + '" target="_blank" rel="noopener">' + svgQQ + 'QQ交谈</a>' +
        '<a class="cp-action ghost" href="mailto:' + EMAIL + '">' + svgMail + '发邮件</a>' +
      '</div>' +

      '<a class="cp-feedback" href="feedback.html">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' +
        '有想法？去留言板提需求 / 报 Bug →' +
      '</a>' +

      '<div class="cp-foot">点击复制按钮可直接复制号码 / 邮箱</div>';

    document.body.appendChild(panel);
    document.body.appendChild(fab);

    fab.addEventListener('click', function (e) {
      e.stopPropagation();
      togglePanel();
    });
    document.getElementById('cpClose').addEventListener('click', function (e) {
      e.stopPropagation();
      togglePanel(false);
    });
    panel.addEventListener('click', function (e) { e.stopPropagation(); });

    // 点击其它区域 / 按 ESC 关闭
    document.addEventListener('click', function () { togglePanel(false); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') togglePanel(false);
    });

    // 复制按钮
    panel.querySelectorAll('.cp-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var text = btn.getAttribute('data-copy');
        copyText(text).then(function () {
          btn.classList.add('copied');
          btn.setAttribute('title', '已复制');
          btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg>';
          setTimeout(function () {
            btn.classList.remove('copied');
            btn.removeAttribute('title');
            btn.innerHTML = svgCopy;
          }, 1800);
        });
      });
    });
  }

  function togglePanel(force) {
    var panel = document.getElementById('contactPanel');
    if (!panel) return;
    var willOpen = typeof force === 'boolean' ? force : !panel.classList.contains('open');
    panel.classList.toggle('open', willOpen);
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

  function init() {
    createNavContactBtn();
    createWidget();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

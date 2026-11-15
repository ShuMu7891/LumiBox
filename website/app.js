/* ============================================================
   LumiBox 官网 · 交互脚本
   hash 路由 / GitHub 超链接重定向 / 灯箱 / 主题 / 入场动画
   ============================================================ */
(function () {
  'use strict';

  var GH = 'https://github.com/ShuMu7891/LumiBox';
  var SITE = 'http://lumibox.jhhcn.icu/';

  /* GitHub 目标映射：所有外链都保留真实 href（无 JS 亦可直达），
     带 data-go 的链接会被接管到 #/go?to=xxx 中转页做统一重定向动画。*/
  var TARGETS = {
    repo:     { url: GH,                                            label: 'LumiBox 仓库',            desc: '即将打开 LumiBox 源码仓库…' },
    release:  { url: GH + '/releases/download/v1.2.0/LumiBox_win-toolbox.zip', label: 'LumiBox v1.2.0 安装包', desc: '即将开始下载 Windows 版压缩包…', download: true },
    releases: { url: GH + '/releases',                             label: 'Releases 页面',           desc: '即将打开版本发布页…' },
    issues:   { url: GH + '/issues',                              label: 'Issues 反馈区',           desc: '即将打开问题反馈页…' },
    preview:  { url: GH + '/tree/main/preview',                   label: 'preview 截图目录',        desc: '即将打开全部 32 张界面截图…' },
    readme:   { url: GH + '#readme',                             label: 'README 完整文档',         desc: '即将打开项目文档…' }
  };

  /* ---------------- 工具 ---------------- */
  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function parseHash() {
    var raw = location.hash.replace(/^#\/?/, '') || 'home';
    var parts = raw.split('?');
    return { page: parts[0] || 'home', params: new URLSearchParams(parts[1] || '') };
  }

  /* ---------------- 主题 ---------------- */
  var themeBtn = $('#themeBtn');
  themeBtn.addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('lumibox-theme', next); } catch (e) {}
    var meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', next === 'dark' ? '#0c1220' : '#eef2fb');
  });

  /* ---------------- 移动端菜单 ---------------- */
  var menuBtn = $('#menuBtn'), dockLinks = $('#dockLinks');
  menuBtn.addEventListener('click', function () {
    var open = dockLinks.classList.toggle('open');
    menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  dockLinks.addEventListener('click', function (e) {
    if (e.target.closest('a')) {
      dockLinks.classList.remove('open');
      menuBtn.setAttribute('aria-expanded', 'false');
    }
  });

  /* ---------------- GitHub 超链接 → 重定向中转页 ---------------- */
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-go]');
    if (!a) return;
    // 按住修饰键 / 中键时保留浏览器原生行为（新标签打开等）
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    var key = a.getAttribute('data-go');
    if (!TARGETS[key]) return;
    e.preventDefault();
    location.hash = '#/go?to=' + encodeURIComponent(key);
  });

  var redirectTimer = null, redirectRAF = null;

  function stopRedirect() {
    if (redirectTimer) { clearTimeout(redirectTimer); redirectTimer = null; }
    if (redirectRAF) { cancelAnimationFrame(redirectRAF); redirectRAF = null; }
  }

  function startRedirect(to) {
    stopRedirect();
    var t = TARGETS[to] || TARGETS.repo;
    var desc = $('#goDesc'), urlEl = $('#goUrl'), bar = $('#goBar'), now = $('#goNow');
    var title = $('.go-card h1'), tip = $('.go-tip');

    desc.textContent = t.desc;
    urlEl.textContent = t.url.replace(/^https?:\/\//, '');
    now.href = t.url;
    now.textContent = t.download ? '立即下载' : '立即前往';
    now.setAttribute('target', t.download ? '_self' : '_blank');
    title.textContent = t.download ? '正在准备下载' : '正在前往 GitHub';
    tip.textContent = t.download ? '若下载没有自动开始，请点击「立即下载」。' : '若没有自动跳转，请点击「立即前往」。';
    bar.style.width = '0%';

    var DUR = 1700, start = null;
    function tick(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / DUR);
      bar.style.width = (p * 100).toFixed(1) + '%';
      if (p < 1) { redirectRAF = requestAnimationFrame(tick); return; }
      redirectRAF = null;
      if (t.download) {
        // 下载类：触发下载但停留在站内，并给出明确反馈
        var dl = document.createElement('a');
        dl.href = t.url; dl.style.display = 'none';
        document.body.appendChild(dl); dl.click();
        setTimeout(function () { dl.remove(); }, 1000);
        title.textContent = '下载已开始';
        desc.textContent = 'LumiBox_win-toolbox.zip 正在下载，完成后解压即可使用。';
        bar.style.width = '100%';
        now.href = GH + '/releases';
        now.textContent = '查看 Releases';
        now.setAttribute('target', '_blank');
        tip.textContent = '需要历史版本？可在 Releases 页面找到。';
      } else {
        location.replace(t.url);   // 真正的重定向跳转
      }
    }
    redirectRAF = requestAnimationFrame(tick);
  }

  /* ---------------- 功能页 Tabs ---------------- */
  $('#featureTabs').addEventListener('click', function (e) {
    var btn = e.target.closest('.tab');
    if (!btn) return;
    var cat = btn.dataset.cat;
    $$('#featureTabs .tab').forEach(function (b) { b.classList.toggle('active', b === btn); });
    $$('#featurePanels .panel').forEach(function (p) { p.classList.toggle('active', p.dataset.cat === cat); });
    revealIn($('.page.active'));
  });

  /* ---------------- 界面预览：数据 / 筛选 / 灯箱 ---------------- */
  var SHOTS = [
    ['01_overview', '总览', 'light', 'OVERVIEW'],
    ['02_system_monitor', '系统监控', 'light', 'SYSTEM'],
    ['03_text_tools', '文本与哈希', 'light', 'TEXT'],
    ['04_image_color', '图片与颜色', 'light', 'IMAGE'],
    ['05_network_tools', '网络与效率', 'light', 'NETWORK'],
    ['06_dev_base_random', '进制与随机数', 'light', 'DEVELOPER'],
    ['09_qrcode_wheel', '二维码与转盘', 'light', 'TOOLS'],
    ['12_calculator', '计算器', 'light', 'CALCULATOR'],
    ['13_calculator_programmer', '程序员模式', 'light', 'PROGRAMMER'],
    ['14_dark_developer', '暗色开发者工具', 'dark', 'DARK'],
    ['15_files_duplicates', '重复文件清理', 'light', 'FILES'],
    ['23_doc_convert', '格式互转', 'light', 'DOCUMENTS'],
    ['25_doc_ocr', '文字识别', 'light', 'OCR'],
    ['26_doc_vault', '密码保险箱', 'light', 'VAULT'],
    ['27_focus_screenshot', '截图贴图', 'light', 'FOCUS'],
    ['28_focus_pomodoro', '番茄钟', 'light', 'POMODORO'],
    ['30_about_v12', '关于 v1.2.0', 'light', 'ABOUT'],
    ['31_dark_doc_convert', '暗色文档工坊', 'dark', 'DARK']
  ];

  var grid = $('#galleryGrid');
  grid.innerHTML = SHOTS.map(function (s, i) {
    return '<figure class="gitem glass" data-idx="' + i + '" data-theme-shot="' + s[2] + '">' +
      '<img src="assets/preview/' + s[0] + '.webp" alt="LumiBox ' + s[1] + ' 界面截图" loading="lazy">' +
      '<figcaption class="gcap"><span>' + s[1] + '</span><small>' + s[3] + '</small></figcaption>' +
      '</figure>';
  }).join('');

  var visible = SHOTS.map(function (_, i) { return i; });

  $('#galleryFilters').addEventListener('click', function (e) {
    var b = e.target.closest('.gfilter');
    if (!b) return;
    $$('.gfilter').forEach(function (x) { x.classList.toggle('active', x === b); });
    var f = b.dataset.filter;
    visible = [];
    $$('.gitem').forEach(function (item) {
      var show = f === 'all' || item.dataset.themeShot === f;
      item.style.display = show ? '' : 'none';
      if (show) visible.push(Number(item.dataset.idx));
    });
  });

  var lb = $('#lightbox'), lbImg = $('#lbImg'), lbTitle = $('#lbTitle'), lbCount = $('#lbCount');
  var lbPos = 0;

  function lbShow(pos) {
    if (!visible.length) return;
    lbPos = (pos + visible.length) % visible.length;
    var idx = visible[lbPos], s = SHOTS[idx];
    lbImg.src = 'assets/preview/' + s[0] + '.webp';
    lbImg.alt = 'LumiBox ' + s[1] + ' 界面截图';
    lbTitle.textContent = s[1];
    lbCount.textContent = (lbPos + 1) + ' / ' + visible.length;
  }
  function lbOpen(idx) {
    lbShow(visible.indexOf(idx) === -1 ? 0 : visible.indexOf(idx));
    lb.classList.add('open'); document.body.style.overflow = 'hidden';
  }
  function lbClose() {
    lb.classList.remove('open'); document.body.style.overflow = '';
  }
  grid.addEventListener('click', function (e) {
    var item = e.target.closest('.gitem');
    if (item) lbOpen(Number(item.dataset.idx));
  });
  $('#lbClose').addEventListener('click', lbClose);
  $('#lbPrev').addEventListener('click', function () { lbShow(lbPos - 1); });
  $('#lbNext').addEventListener('click', function () { lbShow(lbPos + 1); });
  lb.addEventListener('click', function (e) { if (e.target === lb) lbClose(); });
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') lbClose();
    else if (e.key === 'ArrowLeft') lbShow(lbPos - 1);
    else if (e.key === 'ArrowRight') lbShow(lbPos + 1);
  });

  /* ---------------- 入场动画 ---------------- */
  var io = null;
  if ('IntersectionObserver' in window) {
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
  }

  var revealFallback = null;

  function revealIn(page) {
    if (!page) return;
    $$('.reveal', page).forEach(function (el, i) {
      if (!el.classList.contains('in')) {
        el.style.transitionDelay = Math.min(i, 8) * 45 + 'ms';
        if (io) io.observe(el); else el.classList.add('in');
      }
    });
    // 兜底：即使访客不滚动（打印、全页截图、键盘 Tab 到页尾、辅助技术），
    // 稍后也让当前页所有元素显现，避免内容永久隐藏。
    if (revealFallback) clearTimeout(revealFallback);
    revealFallback = setTimeout(function () {
      $$('.reveal', page).forEach(function (el) { el.classList.add('in'); });
    }, 1600);
  }

  /* ---------------- 数字滚动 ---------------- */
  var counted = false;
  function countUp(page) {
    if (counted || !page || page.dataset.page !== 'home') return;
    counted = true;
    $$('[data-count]', page).forEach(function (el) {
      var end = Number(el.dataset.count), suf = el.dataset.suffix || '', t0 = null, DUR = 1100;
      function step(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min(1, (ts - t0) / DUR);
        var e = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(end * e) + (p === 1 ? suf : '');
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  /* ---------------- 路由 ---------------- */
  var PAGES = ['home', 'features', 'gallery', 'download', 'about', 'go'];

  function render() {
    var r = parseHash();
    var page = PAGES.indexOf(r.page) === -1 ? 'home' : r.page;
    stopRedirect();

    var current = null;
    $$('.page').forEach(function (p) {
      var on = p.dataset.page === page;
      p.classList.toggle('active', on);
      if (on) current = p;
    });

    $$('#dockLinks a').forEach(function (a) {
      a.classList.toggle('active', a.dataset.nav === page);
    });

    document.title = ({
      home: 'LumiBox · Windows 综合工具箱',
      features: '功能 · LumiBox', gallery: '界面预览 · LumiBox',
      download: '下载 · LumiBox', about: '关于 · LumiBox', go: '正在跳转 · LumiBox'
    })[page];

    window.scrollTo(0, 0);
    revealIn(current);
    countUp(current);
    if (page === 'go') startRedirect(r.params.get('to') || 'repo');
    $('#year').textContent = new Date().getFullYear();
  }

  window.addEventListener('hashchange', render);
  render();

  // 暴露官网页址，方便在控制台或后续脚本中使用
  window.LUMIBOX = { site: SITE, github: GH, targets: TARGETS };
})();

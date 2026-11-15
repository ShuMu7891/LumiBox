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

  /* ============================================================
     留言板 · 真实服务端 API 客户端
     - 留言一律从服务端读取 / 提交，绝不写入 localStorage 假装成功
     - API 地址优先级：?api= 参数 > localStorage > 全局配置 > 同源
     - 所有用户内容用 textContent 渲染，杜绝 XSS
     ============================================================ */
  var GB = (function () {
    var PAGE_SIZE = 12;
    var adminToken = '';
    var offset = 0;
    var total = 0;
    var busy = false;
    var reqSeq = 0;                 // 防止旧请求覆盖新状态
    var inited = false;

    function apiBase() {
      var q = new URLSearchParams(location.search).get('api');
      if (q) return q.replace(/\/+$/, '');
      try {
        var saved = localStorage.getItem('lumibox-gb-api');
        if (saved) return saved.replace(/\/+$/, '');
      } catch (e) {}
      if (window.LUMIBOX_API_BASE) return String(window.LUMIBOX_API_BASE).replace(/\/+$/, '');
      return '';                    // 同源：由 server.py 一起托管，或反代 /api
    }

    /* 发布网关要求每个请求都带 sharecode 查询参数（hash 不会发给服务器，
       cookie 也可能在隐私模式/新标签里丢失）。这里统一给所有 API 请求补上，
       兼容三种来源：当前页面 ?sharecode=、误拼到 hash 里的、以及 api 配置里自带的。*/
    function shareCode() {
      var re = /(?:[?&])sharecode=([A-Za-z0-9_-]+)/;
      var m = re.exec(location.search) || re.exec(location.hash) || re.exec(apiBase());
      return m ? m[1] : '';
    }

    function url(path) {
      var base = apiBase();
      var u;
      if (!base) {
        u = path;
      } else {
        var qi = base.indexOf('?');
        if (qi >= 0) {
          // api 基址自带查询串时（如 https://host/?sharecode=XXX），
          // 路径要插在 ? 之前，并把基址的参数合并进路径已有的查询串，
          // 否则会拼出两个 ? 或 /?sharecode=XXX/api/messages 这样的坏地址
          var root = base.slice(0, qi).replace(/\/+$/, '');
          var bq = base.slice(qi + 1);
          u = root + path + (bq ? (path.indexOf('?') >= 0 ? '&' : '?') + bq : '');
        } else {
          u = base + path;
        }
      }
      var sc = shareCode();
      if (sc && !/(?:[?&])sharecode=/.test(u)) {
        u += (u.indexOf('?') >= 0 ? '&' : '?') + 'sharecode=' + encodeURIComponent(sc);
      }
      return u;
    }

    function status(kind, text) {
      var el = $('#gbStatus');
      if (!el) return;
      el.className = 'gb-status' + (kind ? ' ' + kind : '');
      el.innerHTML = '';
      var dot = document.createElement('i');
      el.appendChild(dot);
      el.appendChild(document.createTextNode(' ' + text));
    }

    function msg(kind, text) {
      var el = $('#gbMsg');
      if (!el) return;
      el.className = 'gb-msg show ' + kind;
      el.textContent = text;
      if (kind === 'ok') setTimeout(function () {
        if (el.textContent === text) el.className = 'gb-msg';
      }, 5000);
    }

    function escState(icon, title, sub, retry) {
      var box = $('#gbList');
      box.innerHTML = '';
      var st = document.createElement('div');
      st.className = 'gb-state';
      var ic = document.createElement('div');
      ic.className = 'gb-ico'; ic.textContent = icon;
      var p = document.createElement('p');
      p.textContent = title;
      var small = document.createElement('p');
      small.style.fontSize = '12px'; small.style.opacity = '.8';
      small.textContent = sub || '';
      st.appendChild(ic); st.appendChild(p);
      if (sub) st.appendChild(small);
      if (retry) {
        var btn = document.createElement('button');
        btn.className = 'gb-retry'; btn.type = 'button'; btn.textContent = '重试';
        btn.addEventListener('click', function () { load(true); });
        st.appendChild(btn);
        var cfg = document.createElement('button');
        cfg.className = 'gb-retry'; cfg.type = 'button'; cfg.textContent = '设置服务地址';
        cfg.style.marginLeft = '8px';
        cfg.addEventListener('click', function () {
          var panel = $('#gbAdminPanel'), toggle = $('#gbAdminToggle');
          panel.hidden = false; toggle.setAttribute('aria-expanded', 'true');
          panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setTimeout(function () { $('#gbApiUrl').focus(); }, 350);
        });
        st.appendChild(cfg);
      }
      box.appendChild(st);
    }

    function relTime(iso) {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      var diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
      if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' 天前';
      // 服务端时间为 UTC，转换成本地时间展示
      return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
             String(d.getDate()).padStart(2, '0') + ' ' +
             String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    }

    var AVATAR_COLORS = ['#3b7bf0', '#7a5cf0', '#e35f9b', '#1eab9c', '#e08b28', '#5a70d8', '#d4566b'];
    function avatarColor(name) {
      var h = 0;
      for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
      return AVATAR_COLORS[h % AVATAR_COLORS.length];
    }

    function cardNode(item) {
      var card = document.createElement('article');
      card.className = 'gb-card';
      card.dataset.id = item.id;

      var top = document.createElement('div'); top.className = 'gb-card-top';
      var av = document.createElement('div'); av.className = 'gb-avatar';
      av.style.background = avatarColor(item.name || '?');
      av.textContent = (item.name || '?').trim().charAt(0).toUpperCase();
      var who = document.createElement('div'); who.className = 'gb-card-who';
      var nm = document.createElement('div'); nm.className = 'gb-card-name'; nm.textContent = item.name;
      var tm = document.createElement('div'); tm.className = 'gb-card-time'; tm.textContent = relTime(item.created_at);
      who.appendChild(nm); who.appendChild(tm);
      var seq = document.createElement('span'); seq.className = 'gb-seq';
      seq.textContent = '#' + item.seq;
      top.appendChild(av); top.appendChild(who); top.appendChild(seq);

      var body = document.createElement('div'); body.className = 'gb-card-body';
      body.textContent = item.content;                 // 关键：纯文本，不解析 HTML

      var del = document.createElement('button');
      del.className = 'gb-card-del'; del.type = 'button';
      del.textContent = '✕'; del.title = '删除这条留言';
      del.hidden = !adminToken;
      del.addEventListener('click', function () { remove(item.id); });

      card.appendChild(top); card.appendChild(body); card.appendChild(del);
      return card;
    }

    function renderItems(items, append) {
      var box = $('#gbList');
      if (!append) box.innerHTML = '';
      // 首条为加载占位时清空
      var ph = box.querySelector('.gb-state');
      if (ph) ph.remove();
      items.forEach(function (it) { box.appendChild(cardNode(it)); });
      $('#gbTotal').textContent = total;
      $('#gbMoreWrap').hidden = !(offset < total);
      if (total === 0) escState('✎', '还没有人留言', '来当第一个吧，留言会保存到服务器上。', false);
    }

    async function load(reset) {
      if (busy) return;
      busy = true;
      var my = ++reqSeq;
      if (reset) { offset = 0; $('#gbList').innerHTML = '<div class="gb-state"><span class="gb-loader"></span><p>正在读取留言…</p></div>'; }
      var btn = $('#gbRefresh'); btn.classList.add('spin');
      try {
        var r = await fetch(url('/api/messages?offset=' + offset + '&limit=' + PAGE_SIZE),
                            { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        var d = await r.json();
        if (my !== reqSeq) return;                  // 已有更新的请求，丢弃旧结果
        if (!d.ok) throw new Error(d.error || '服务返回异常');
        total = d.total;
        offset += d.items.length;
        status('on', '已连接 · 共 ' + total + ' 条');
        renderItems(d.items, !reset);
      } catch (e) {
        if (my !== reqSeq) return;
        status('off', '未连接服务');
        escState('⚠', '读不到留言', '无法连接留言服务（' + e.message + '）。留言保存在服务端，请确认后端已启动。', true);
        $('#gbMoreWrap').hidden = true;
      } finally {
        if (my === reqSeq) btn.classList.remove('spin');
        busy = false;
      }
    }

    async function submit(e) {
      e.preventDefault();
      var nameEl = $('#gbName'), contentEl = $('#gbContent'), btn = $('#gbSubmit');
      var name = nameEl.value.trim(), content = contentEl.value.trim();
      if (!name) { msg('err', '请填写昵称'); nameEl.focus(); return; }
      if (!content) { msg('err', '留言内容不能为空'); contentEl.focus(); return; }
      if (name.length > 20 || content.length > 500) { msg('err', '内容超出字数限制'); return; }

      btn.disabled = true;
      var old = btn.innerHTML;
      btn.textContent = '发表中…';
      try {
        var r = await fetch(url('/api/messages'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name, content: content, website: $('#gbHp').value })
        });
        var d = await r.json();
        if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
        // 成功后重新从服务端读取（不本地追加），确认它真的落库
        contentEl.value = '';
        updateCount();
        try { localStorage.setItem('lumibox-gb-name', name); } catch (err) {}
        await load(true);
        msg('ok', '已保存到服务器！其他访客刷新页面就能看到这条留言。');
      } catch (err) {
        // 明确失败，绝不伪造一条本地留言
        status('off', '未连接服务');
        msg('err', '发表失败：' + err.message + '。内容未保存，请稍后重试。');
      } finally {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    }

    async function remove(id) {
      if (!adminToken) return;
      if (!window.confirm('确定删除这条留言？此操作不可撤销。')) return;
      try {
        var r = await fetch(url('/api/messages/' + encodeURIComponent(id)), {
          method: 'DELETE', headers: { 'X-Admin-Token': adminToken }
        });
        var d = await r.json();
        if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
        await load(true);
        msg('ok', '已删除。');
      } catch (e) { msg('err', '删除失败：' + e.message); }
    }

    function updateCount() {
      var n = $('#gbName'), c = $('#gbContent');
      var nc = $('#gbNameCount'), cc = $('#gbContentCount');
      nc.textContent = n.value.length + ' / 20';
      cc.textContent = c.value.length + ' / 500';
      nc.classList.toggle('warn', n.value.length >= 20);
      cc.classList.toggle('warn', c.value.length >= 480);
    }

    function initAdmin() {
      var toggle = $('#gbAdminToggle'), panel = $('#gbAdminPanel');
      toggle.addEventListener('click', function () {
        var open = panel.hidden;
        panel.hidden = !open;
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      $('#gbAdminLogin').addEventListener('click', async function () {
        var token = $('#gbAdminToken').value.trim();
        var hint = $('#gbAdminHint');
        if (!token) { hint.textContent = '请输入口令'; return; }
        try {
          var r = await fetch(url('/api/export'), { headers: { 'X-Admin-Token': token } });
          var d = await r.json();
          if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
          adminToken = token;
          $('#gbAdminExport').disabled = false;
          hint.textContent = '✓ 口令正确，共 ' + d.total + ' 条留言';
          $$('.gb-card-del').forEach(function (b) { b.hidden = false; });
          msg('ok', '管理权限已启用，可删除留言或导出备份。');
        } catch (e) { hint.textContent = '✗ ' + e.message; }
      });
      $('#gbAdminExport').addEventListener('click', async function () {
        if (!adminToken) return;
        try {
          var r = await fetch(url('/api/export'), { headers: { 'X-Admin-Token': adminToken } });
          var d = await r.json();
          var blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'lumibox-messages-' + new Date().toISOString().slice(0, 10) + '.json';
          a.click();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
        } catch (e) { msg('err', '导出失败：' + e.message); }
      });
      // 静态托管场景：把前端指向独立部署的留言后端
      var apiInput = $('#gbApiUrl'), apiHint = $('#gbApiHint');
      try { apiInput.value = localStorage.getItem('lumibox-gb-api') || ''; } catch (e) {}
      $('#gbApiSave').addEventListener('click', function () {
        var v = apiInput.value.trim().replace(/\/+$/, '');
        if (v && !/^https?:\/\//i.test(v)) {
          apiHint.textContent = '✗ 请填写完整地址，以 http:// 或 https:// 开头';
          return;
        }
        try {
          if (v) localStorage.setItem('lumibox-gb-api', v);
          else localStorage.removeItem('lumibox-gb-api');
        } catch (e) {}
        apiHint.textContent = v ? '✓ 已保存，正在重新连接…' : '✓ 已恢复同源，正在重新连接…';
        load(true);
      });
      $('#gbApiReset').addEventListener('click', function () {
        apiInput.value = '';
        try { localStorage.removeItem('lumibox-gb-api'); } catch (e) {}
        apiHint.textContent = '✓ 已恢复同源，正在重新连接…';
        load(true);
      });
    }

    function init() {
      if (inited) return;
      inited = true;
      $('#gbForm').addEventListener('submit', submit);
      $('#gbName').addEventListener('input', updateCount);
      $('#gbContent').addEventListener('input', updateCount);
      $('#gbRefresh').addEventListener('click', function () { load(true); });
      $('#gbMore').addEventListener('click', function () { load(false); });
      try {
        var saved = localStorage.getItem('lumibox-gb-name');
        if (saved) $('#gbName').value = saved;
      } catch (e) {}
      updateCount();
      initAdmin();
    }

    return {
      enter: function () {
        init();
        status('', '正在连接…');
        load(true);                                 // 每次进入都重新拉取，看到别人新发的
      }
    };
  })();

  /* ---------------- 路由 ---------------- */
  var PAGES = ['home', 'features', 'gallery', 'download', 'about', 'guestbook', 'go'];

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
      download: '下载 · LumiBox', about: '关于 · LumiBox',
      guestbook: '留言板 · LumiBox', go: '正在跳转 · LumiBox'
    })[page];

    window.scrollTo(0, 0);
    revealIn(current);
    countUp(current);
    if (page === 'go') startRedirect(r.params.get('to') || 'repo');
    if (page === 'guestbook') GB.enter();
    $('#year').textContent = new Date().getFullYear();
  }

  window.addEventListener('hashchange', render);
  render();

  // 暴露官网页址，方便在控制台或后续脚本中使用
  window.LUMIBOX = { site: SITE, github: GH, targets: TARGETS };
})();

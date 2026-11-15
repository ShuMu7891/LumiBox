# LumiBox 官网 · 留言板部署说明

## 为什么需要一个后端

留言必须**所有访客共享**：A 发表的留言，B 打开页面要能看到，站长也要能看到。
纯静态托管（GitHub Pages / 对象存储 / CDN）只能分发文件，无法保存数据，因此留言板必须配一个 HTTP 后端。

本项目自带一个**零依赖**后端 `server.py`（Python 3.8+ 标准库，不用装 Flask 等任何包）：
同时托管静态官网 + 提供留言 API，留言落盘到 `data/messages.json`。

> 留言**不会**存进浏览器 localStorage。前端只把昵称记在本地方便下次填写，
> 留言内容一律从服务端读取；提交失败会明确报错，绝不会伪造一条"看起来成功"的本地留言。

---

## 方式一：本地 / 自有服务器直接跑（推荐，最简单）

```bash
# Linux / macOS
LUMIBOX_ADMIN_TOKEN='换成你的复杂口令' python3 server.py

# Windows：双击 start_server.bat 即可（需已安装 Python 3.8+）
```

浏览器打开 `http://127.0.0.1:8080/` → 导航「留言」。

环境变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `PORT` / `LUMIBOX_PORT` | 监听端口 | `8080` |
| `LUMIBOX_ADMIN_TOKEN` | 站长口令（删除/导出用） | `lumibox-admin-2026` ← **上线务必修改** |
| `LUMIBOX_DATA` | 数据文件路径 | `<站点>/data/messages.json` |
| `LUMIBOX_SITE` | 静态站点目录 | `<server.py 所在目录>` |

> 默认口令是公开的，只用于本地试用。正式上线不修改的话，任何人都能删除留言。

---

## 方式二：部署到已有官网域名 `http://lumibox.jhhcn.icu/`

### 方案 A：整站交给 server.py（最省事）

把 `lumibox-site/` 整个目录放到服务器，用上面的命令启动，让域名直接指向这个端口。
前后端同源，前端默认就请求 `/api/messages`，**无需任何配置**。

用 systemd 常驻（Linux 示例）：

```ini
# /etc/systemd/system/lumibox.service
[Unit]
Description=LumiBox Website & Guestbook
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/lumibox-site
Environment=LUMIBOX_PORT=8080
Environment=LUMIBOX_ADMIN_TOKEN=换成你的复杂口令
ExecStart=/usr/bin/python3 /opt/lumibox-site/server.py
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lumibox
```

### 方案 B：保留现有 Web 服务器，用反向代理转发 /api

若官网已由 Nginx / Caddy / Apache 托管静态文件，只把 `/api/` 转给后端进程：

```nginx
server {
    listen 80;
    server_name lumibox.jhhcn.icu;
    root /var/www/lumibox-site;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / { try_files $uri $uri/ /index.html; }
}
```

后端仍用 `python3 server.py` 跑在 8080（或 systemd 常驻）。

### 方案 C：静态托管 + 独立后端域名

如果官网放在 GitHub Pages / CDN 等纯静态平台，把 `server.py` 单独部署到任意能跑 Python
的机器（例如 `https://api.example.com`），然后在官网：

1. 打开「留言」页 → 展开底部「站长管理」→ 在 **留言服务地址** 填入后端地址 → 保存；
2. 或在 URL 加参数：`http://lumibox.jhhcn.icu/?api=https://api.example.com#/guestbook`。

后端已开启 CORS（`Access-Control-Allow-Origin: *`），跨域可直接用。
配置存在浏览器 localStorage，仅影响当前浏览器；要让所有访客生效，请改 `app.js` 顶部
的 `window.LUMIBOX_API_BASE`，或在首页加载前注入：

```html
<script>window.LUMIBOX_API_BASE = 'https://api.example.com';</script>
```

> 建议后端配 HTTPS，避免 HTTP 页面到 HTTPS 后端的混合内容拦截。

---

## API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查、留言总数 |
| `GET` | `/api/stats` | 总数 / 今日条数 |
| `GET` | `/api/messages?offset=0&limit=20` | 分页读取（最新在前，公开） |
| `POST` | `/api/messages` | 发表 `{name, content, website?}` |
| `DELETE` | `/api/messages/<id>` | 删除（需 `X-Admin-Token` 头） |
| `GET` | `/api/export` | 导出全部（需 `X-Admin-Token` 头） |

响应统一为 `{ "ok": true, ... }` / `{ "ok": false, "error": "..." }`。

服务端约束：昵称 ≤ 20 字、内容 ≤ 500 字、单次请求体 ≤ 16 KB；
同 IP 30 秒最多 30 条、相同内容 60 秒内不可重复；蜜罐字段 `website` 非空即拒绝；
最多保留 5000 条。IP 仅存脱敏摘要，不存明文。

---

## 站长怎么看到别人的留言

1. **直接看**：打开官网「留言」页，所有访客的留言按时间倒序列出，显示昵称、相对时间、楼层号。
   每次进入页面或点「刷新」都会重新从服务端拉取，所以能看到别人刚发的。
2. **导出备份**：展开「站长管理」→ 输入 `LUMIBOX_ADMIN_TOKEN` → 点「导出 JSON」，
   得到全部留言文件；也可直接复制服务器上的 `data/messages.json`。
3. **删除违规内容**：口令验证通过后，每条留言右上角出现删除按钮，确认后即从服务端移除。

也可以直接调 API：

```bash
curl https://你的域名/api/messages?limit=20
curl -H "X-Admin-Token: 你的口令" https://你的域名/api/export
```

---

## 留言入口重定向（静态镜像站推荐）

官网源文件默认带一段**内联跳转脚本**（在 `index.html` 的 `<head>` 里，不依赖 `app.js`）：

- 在**非在线发布域名**上（例如你自己的 `lumibox.jhhcn.icu`），点导航 / 页脚的「留言」，
  或直接访问 `#/guestbook`，都会跳到带后端的在线留言服务，避免看到「未连接服务」。
- 在线发布域名本身**不会跳转**（防止循环重定向），留言页照常工作。

**部署到自己的域名时，只需覆盖 `index.html` 这一个文件即可生效**，其余文件可以保持旧版：
跳转目标是在线服务，那边运行的是完整新版（含 `?page=guestbook` 直达）。

如需调整：

- 改目标地址：编辑 `index.html` 里的 `ONLINE_HOST` 与 `TARGET` 两个常量。
- 关闭跳转（你已在自己域名跑起 `server.py`、留言要存自己服务器时）：
  在这段脚本**之前**加一行内联脚本设置 `window.LUMIBOX_GUESTBOOK_LOCAL = true`。
- 也可完全自托管：跑起后端后，留言页会直接读同源 `/api`，无需任何跳转。

---

## 常见故障：留言页显示「未连接服务」

**原因**：只上传了静态文件（`index.html` / `style.css` / `app.js`），没有跑 `server.py`，
也没有配置后端地址。此时页面能打开，但 `/api/messages` 返回 404 或跨域失败，于是列表连不上。

按上面「方案一」跑起 `server.py` 并配好反代即可根治。若想**先不跑后端、临时收留言**，
用下面任一方式把前端指向已上线的演示后端：

**方式 1 — 整站生效（推荐给静态托管）**

编辑 `index.html`，在 `</head>` 之前加一行（改成你自己的后端地址）：

```html
<script>window.LUMIBOX_API_BASE = 'https://你的后端域名/';</script>
```

所有访客打开你的官网都会走这个后端，留言跨访客共享。后端需允许跨域
（本项目 `server.py` 已开放 CORS）。

**方式 2 — 单人临时体验**

在留言页点「站长管理 → 留言服务地址」，填入后端地址后保存（存于本机浏览器）。
或直接在网址上加参数：`https://你的域名/?api=https%3A%2F%2F后端域名%2F#/guestbook`。

> 若后端部署在带 `sharecode` 访问凭据的发布平台上，可直接把完整地址填进
> 「留言服务地址」，例如 `https://host/?sharecode=XXXX`；前端会自动把凭据
> 透传给每个 API 请求，并把路径正确插在 `?` 之前。

**分享链接打不开（提示「链接不完整」）**：这类发布网关要求 URL 里始终带
`?sharecode=XXXX`，且必须放在 `#` 之前。请**整条复制**链接，不要只复制域名；
也不要把它拼成 `#/guestbook?sharecode=XXXX`（`#` 后面的内容不会发给服务器）。

---

## 安全说明

- 用户内容在前端一律用 `textContent` 渲染，**不解析 HTML**，可安全显示 `<script>` 等文本；
  后端也剥离控制字符并做长度/类型校验。
- 管理口令只在服务端比对（常数时间比较），前端不内置任何口令；
  错误口令返回 403，删除/导出均需口令。
- 静态文件做了目录穿越防护；数据文件用「临时文件 + `os.replace`」原子写入，并发写入不丢数据。
- 限流刻意放宽，避免反向代理 / NAT 后多个真实访客共享 IP 时互相挤占；刷屏主要靠同内容去重、蜜罐与站长删除兜底。
- 数据文件 `data/messages.json` 请纳入定期备份；此文件不应提交到公开仓库（已在 `.gitignore` 中排除）。

---

## 验收记录（本地实测）

- 两个**完全独立**的浏览器上下文：A 发表 → B 打开页面看到；B 发表 → A 刷新后看到 ✅
- 12 条并发写入全部 201，无丢失 ✅
- 空内容 / 超长昵称 / 超长内容 / 蜜罐 / 非对象请求均被拒绝 ✅
- 注入 `<script>` 与 `<img onerror>` 按纯文本显示，脚本未执行 ✅
- 错误口令 403、正确口令可删除与导出、重复删除 404 ✅
- 目录穿越 `/../server.py` 被拦截 ✅
- 分页无重叠、非法参数有明确错误、limit 上限生效 ✅
- 亮/暗主题、移动端无横向溢出、控制台零报错 ✅
- 数据落盘 `data/messages.json`，服务重启后留言仍在 ✅

# 🎮 Epic Games 免费游戏助手

> **周免游戏跟踪 · 一键领取跳转 · 零浏览器 · 零验证码 · 镜像 ~150MB。**
>
> 追踪 Epic 每周免费游戏 · 记录领取历史 · 新游戏上线立即推送通知。

🇺🇸 [English README](README.md)

---

## 📌 这是什么？

`epic-games-helper` 是一个**轻量级 HTTP API + Web UI** 服务，帮助你不错过 Epic 每周的免费游戏。

- 📡 **追踪** Epic 每周免费游戏（北京时间每周五 0:00 更新）
- 📅 **预告** 下周即将免费的 Epic 游戏
- 🗂️ **记录** 每周领取过的游戏（永久历史，可追溯）
- 📲 **推送** Webhook 通知（Bark / Server酱 / Telegram / 通用 Webhook），新游戏上线立即通知
- 🎯 **生成** 一键领取 URL（直达 Epic 商品页）

> **重要提示：** Epic Games 的购买接口**无法**通过纯 API 完成（需要浏览器 session、Cookie、XSRF、hCaptcha），
> 所以本工具**无法直接帮你自动领取游戏**。但它做了所有周边工作，让领取只需**一键**。

---

## ✨ 功能

图例：**✅ 已实现** · **🚧 开发中** · **❌ 不实现**（说明原因）

### 核心功能

| 状态 | 功能 |
|------|------|
| ✅ | **Epic Device Code OAuth** — 在你浏览器登录一次，获得永不过期 token（不存密码，无 hCaptcha）|
| ✅ | **本周免费游戏追踪** — 从 Epic 公开 catalog API (`freeGamesPromotions`) 自动拉取 |
| ✅ | **下周预告** — 显示 Epic 已公布的下一周免费游戏（提前一周知道）|
| ✅ | **一键领取 URL** — 每个游戏生成专属链接，点击直达 Epic 商品页 |
| ✅ | **丰富游戏卡片** — 封面图、标题、原价、免费时段、"剩 N 天"徽章 |
| ✅ | **正确领取 URL 格式** — 使用 Epic 兼容的 `offers=1-{namespace}-{offerId}`（避开 400）|
| ✅ | **精准商品页 slug** — 从 `offerMappings[0].pageSlug` 取真实商品页 URL |

### Web UI（Epic 风格）

| 状态 | 功能 |
|------|------|
| ✅ | **纯黑画布 + 电光蓝**（`#0078F2`）— 完全对齐 Epic 商店设计语言 |
| ✅ | **顶部 sticky 导航** + 授权状态指示灯 |
| ✅ | **Hero 横幅** 显示每周免费游戏信息 |
| ✅ | **设备码授权流程** — 复制 code → 点击 Epic 链接 → 自动检测授权成功 |
| ✅ | **本周免费游戏区域** + 下周预告（混合排列，用徽章区分）|
| ✅ | **紧凑领取历史** — 按 ISO 周分组，水平卡片布局：缩略图 + 标题 + 日期 + 价格 + 状态 |
| ✅ | **首字占位** — 没有图片的游戏显示首字符（如 "A" for "Alone With You"）|
| ✅ | **调试面板** + API 测试按钮 |
| ✅ | **完全响应式** — 手机 / 平板 / 桌面 |

### 定时 & 通知

| 状态 | 功能 |
|------|------|
| ✅ | **APScheduler 定时任务**（默认：北京时间每周五 0:05）|
| ✅ | **Fingerprint 对比** — 只有本周游戏变化时才推送通知（避免重复）|
| ✅ | **Webhook 推送** — Bark（iOS）/ Server酱（微信）/ Telegram Bot / 通用 Webhook |
| ✅ | **下次运行时间** 在 UI 中显示 |
| ❌ | **真正自动领取** — Epic 需要浏览器 session cookie，无法伪造。点"前往领取"按钮即可，Epic 自己处理 |

### 持久化 & 隐私

| 状态 | 功能 |
|------|------|
| ✅ | **Fernet 加密 token 存储**（AES-128-CBC + HMAC），文件权限 `0600` |
| ✅ | **Master key 自动生成**（首次启动），显式设置 `EPIC_MASTER_KEY` 可跨容器重建保留 |
| ✅ | **领取历史持久化** 到 `logs/history.json`（保留最近 100 条每周游戏）|
| ✅ | **日志/历史目录支持 volume 挂载**，跨容器重启保留 |
| ✅ | **不存任何密码** — 仅存 OAuth token |

### 基础设施

| 状态 | 功能 |
|------|------|
| ✅ | **多架构 Docker 镜像**（`linux/amd64` + `linux/arm64`）— 群晖、威联通、Unraid、Raspberry Pi 4+ |
| ✅ | **镜像体积 ~150MB**（无 Chromium / Playwright / X11 / VNC）|
| ✅ | **REST API** + Swagger UI（`/docs`）|
| ✅ | **Docker Compose** 一键部署 |
| ✅ | **GitHub Actions CI** — 每次 PR 自动校验 Python 语法 + docker-compose 配置 |
| ✅ | **自动同步 README → Docker Hub** — 每次 push main 自动更新 Docker Hub 仓库描述 |

### 不实现的功能

| 状态 | 功能 | 不实现的原因 |
|------|------|------------|
| ❌ | 真正零点击自动领取 | Epic 需要浏览器 session cookie、XSRF token、hCaptcha — 无法通过 API 伪造 |
| ❌ | 多账号支持 | 单账号设计让凭据存储更简单；多账号需要完全不同的 UX（如每账号 tab）|
| ❌ | 内置浏览器兜底（Chromium）| 镜像体积从 150MB 膨胀到 1GB+，且增加 hCaptcha 风险 |
| ❌ | 完整游戏库（含付费游戏）| Epic `library-service` API 需要 OAuth authorization_code flow，Epic 不允许 localhost redirect_uri |
| ❌ | 多地区支持 | 当前硬编码 `zh-CN/CN`；Epic API 对免费游戏地区无感，全球都能用 |

---

## 🚀 快速开始

### 1. Docker 启动

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. 授权

打开 **http://localhost:8080**：

1. 点击 **"开始设备码授权"** 按钮
2. 复制显示的 `user_code`（如 `ABCD EFGH`）
3. 点击 **"🌐 打开 Epic 授权页面"** 按钮（Epic 授权页会在新标签打开）
4. 在 Epic 页面登录你的账号，粘贴 user code
5. 点击 "Allow" — 浏览器会跳回助手的成功页
6. Web UI 自动检测授权成功并保存 token

之后每周免费游戏会自动追踪。

### 3.（可选）配置推送通知

编辑 `docker run` 命令或 `docker-compose.yml`，添加 webhook 环境变量：

```bash
# Bark（iOS 推送，免费）
-e NOTIFY_WEBHOOK_TYPE=bark \
  -e NOTIFY_WEBHOOK_URL=https://api.day.app \
  -e NOTIFY_WEBHOOK_TOKEN=你的_device_key

# Server 酱（微信推送）
-e NOTIFY_WEBHOOK_TYPE=serverchan \
  -e NOTIFY_WEBHOOK_URL=https://sctapi.ftqq.com \
  -e NOTIFY_WEBHOOK_TOKEN=你的_sendkey

# Telegram Bot
-e NOTIFY_WEBHOOK_TYPE=telegram \
  -e NOTIFY_WEBHOOK_URL=https://api.telegram.org/-你的_chat_id \
  -e NOTIFY_WEBHOOK_TOKEN=你的_bot_token
```

---

## 🐳 Docker Compose

```yaml
services:
  epic-helper:
    image: zz3656/epic-games-helper:latest
    container_name: epic-games-helper
    restart: unless-stopped
    ports:
      - "8080:8000"
    environment:
      - TZ=Asia/Shanghai
      # Epic 每周五北京时间 0:00 更新免费游戏
      # 默认：周五 0:05 检查（避开 Epic 更新高峰）
      - SCHEDULE_DAY=fri
      - SCHEDULE_HOUR=0
      - SCHEDULE_MINUTE=5
      - AUTO_CLAIM_ENABLED=true
      # Webhook 推送（可选，见快速开始 §3）
      # - NOTIFY_WEBHOOK_TYPE=bark
      # - NOTIFY_WEBHOOK_URL=https://api.day.app
      # - NOTIFY_WEBHOOK_TOKEN=your_device_key
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

> 📌 **多架构镜像**：`linux/amd64` 和 `linux/arm64`（群晖、威联通、Unraid、Raspberry Pi 4+ 都能跑）

---

## 🔐 隐私与安全

| 存储 | 加密 | 文件 | 权限 |
|------|------|------|------|
| Device Auth Token | Fernet (AES-128-CBC + HMAC) | `/app/data/device_auth.enc` | `0600` |
| Master key | 明文 | `/app/data/.env` | `0600` |
| 历史记录 | JSON | `/app/logs/history.json` | `0644` |

**只存储 OAuth token，不存密码。**

---

## ⚙️ 配置

| 环境变量 | 默认 | 说明 |
|---------|------|------|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 密钥（显式设置可跨容器重建保留 token）|
| `TZ` | `Asia/Shanghai` | 定时器时区 |
| `SCHEDULE_DAY` | `fri` | 触发日（`mon`–`sun`，默认周五）|
| `SCHEDULE_HOUR` | `0` | 触发小时（`0`–`23`，默认凌晨）|
| `SCHEDULE_MINUTE` | `5` | 触发分钟（`0`–`59`，默认 :05）|
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动检查 |
| `NOTIFY_WEBHOOK_TYPE` | _未配置_ | 可选：`bark` / `serverchan` / `telegram` / `generic` |
| `NOTIFY_WEBHOOK_URL` | _未配置_ | Webhook URL |
| `NOTIFY_WEBHOOK_TOKEN` | _未配置_ | Webhook token/密钥 |

---

## 🛠️ API

Swagger 文档：**http://localhost:8080/docs**

### 免费游戏 & 历史

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查（包含下次运行时间 + 通知状态）|
| `/api/free-games` | GET | 本周 + 下周免费游戏（封面、日期、价格、领取链接）|
| `/api/history` | GET | 领取历史（最近 200 条）|
| `/api/account/games` | GET | 聚合视图（免费游戏 + 领取历史）|

### 设备码授权

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/device-auth/status` | GET | 设备码授权是否已配置 |
| `/api/device-auth/account-info` | GET | 验证已存储账号是否仍可用 |
| `/api/device-auth/request` | POST | 申请 device code |
| `/api/device-auth/poll/{code}` | GET | 轮询授权状态 |
| `/api/device-auth/cancel/{code}` | DELETE | 取消待处理的授权 |
| `/api/device-auth` | DELETE | 撤销已保存的授权 |

### 定时任务 & 调试

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scheduler/test-run` | POST | 手动触发定时检查（调试用）|
| `/api/scheduler/test-notify` | POST | 发送测试推送（调试用）|
| `/api/device-auth/test/free-games` | POST | 测试免费游戏 API |
| `/api/device-auth/test/request` | POST | 测试 device code 申请 |
| `/api/device-auth/test/claim` | POST | 测试领取链接生成 |

---

## 🏗️ 架构

```
┌────────────────────────────────────────────────────────────┐
│  Web UI（浏览器）                                          │
│  • Epic 风格（纯黑 + #0078F2）                            │
│  • 设备码授权 + 自动轮询                                  │
│  • 本周免费游戏 + 下周预告                                │
│  • 领取历史（按周分组）                                   │
│  • 调试面板 + Webhook 状态                                │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  FastAPI 后端（端口 8000）                                │
│  • /api/device-auth/*          OAuth 流程                  │
│  • /api/free-games             本周 + 下周游戏             │
│  • /api/history                领取历史                    │
│  • /api/scheduler/*            手动触发 + webhook          │
│  • APScheduler                 每周五 0:05 定时检查        │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  EpicAPIClient（纯 HTTP，无浏览器）                        │
│  • freeGamesPromotions          → 本周 + 下周游戏         │
│  • /store/purchase?offers=...  → checkout URL             │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  Notifier（webhook 推送）                                  │
│  • Bark / Server酱 / Telegram / 通用 Webhook              │
│  • Fingerprint 对比：仅在游戏真正变化时推送                │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── epic_api.py            # 纯 HTTP Epic 客户端（freeGamesPromotions）
│   ├── api_device_auth.py     # 设备码 + 免费游戏 API 端点
│   ├── scheduler.py           # APScheduler 定时检查 + fingerprint
│   ├── notifier.py            # Webhook 推送（Bark/Server酱/Telegram/generic）
│   ├── credential_store.py    # Fernet 加密
│   ├── storage.py             # 历史持久化（deque + JSON 文件）
│   ├── result.py              # 数据模型
│   ├── config.py              # 环境变量
│   └── static/
│       ├── device_auth.js     # 主前端逻辑（~330 行）
│       ├── free_games.js      # 游戏卡片渲染 + 历史（~210 行）
│       └── style.css          # Epic 设计系统（~22 KB）
├── scripts/
│   └── entrypoint.sh          # 容器入口
├── .github/workflows/
│   ├── ci.yml                 # Python 语法 + compose 校验
│   ├── docker-image.yml       # 多架构 Docker 构建 + 推送
│   └── sync-readme-to-dockerhub.yml  # 自动同步 README → Docker Hub
├── Dockerfile
├── docker-compose.yml
├── README.md                  # 英文
└── README-zh-CN.md            # 中文
```

---

## 🐛 故障排查

**设备码授权持续失败** — 打开 Web UI 底部的 **🛠 调试选项** 面板，测试按钮会打印实际的 Epic API 响应和错误。

**点击"领取"后 Epic 显示"在尝试处理您的请求时发生错误"** — Epic 的前端 JS 调用 `cartOffersValidation` 失败。常见原因：(1) 浏览器未登录 Epic，(2) Epic EULA 未接受，(3) Epic 账号未启用 2FA。先在浏览器登录 Epic 并接受 EULA，在 Epic 账户安全设置中启用 2FA，然后重试。

**容器重启后 `Master key 不匹配`**：
```bash
rm ./data/device_auth.enc
# Web UI 重新授权
```

**Webhook 推送没收到** — 打开 **🛠 调试选项** → 点击 **测试 webhook 推送**，查看 webhook 服务商返回的具体错误。

**容器无法启动** — 查看 `docker logs epic-games-helper`。常见原因：端口 `8080` 被占用，修改 `-p` 左侧的映射。

---

## 🙏 致谢与灵感来源

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — "用 Device Code OAuth + 生成 checkout URL"思路的原始项目；本项目是该思路的 Python 重实现。
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic API 详尽逆向文档。
- **[xMistt/rebootpy](https://github.com/xMistt/rebootpy)** — Python 实现的 User-Agent + auth header 参考。
- **[Heroic-Games-Launcher/legendary](https://github.com/Heroic-Games-Launcher/legendary)** — `library-service` API 端点结构参考。

---

## ⚠️ 免责声明

本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)。作者不对账号被封、数据丢失等任何损失负责。

## 📝 License

MIT

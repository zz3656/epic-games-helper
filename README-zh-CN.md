# 🎮 Epic Games 免费游戏助手

> Epic Games 周免游戏跟踪 + 一键领取跳转。**追踪本周免费游戏、识别已拥有游戏、一键跳转领取页面**。

🇺🇸 [English README](README.md)

---

## 📌 这是什么？

`epic-games-helper` 是一个轻量级的 HTTP API + Web UI 服务：

- 📡 **追踪** Epic 每周免费游戏（每周四更新）
- 🗂️ **关联** 你的 Epic 库（自动识别已拥有）
- 🎯 **生成** 每个游戏的一键领取链接
- ⏰ **定时** 检查新一周免费游戏

> **重要提示：** Epic Games 的购买接口**无法**通过纯 API 完成（需要浏览器 session、XSRF、hCaptcha 等），
> 所以本工具**无法直接帮你自动领取游戏**。但它做了所有周边工作，让领取只需**一键**。

查看[路线图](#-路线图)了解已实现与未来规划。

---

## ✨ 功能

### ✅ 已实现

- 🔑 **Epic Device Code OAuth** — 在你自己浏览器登录一次，获得永不过期 token（不存密码，无 hCaptcha）
- 🗓️ **本周免费游戏列表** — 从 Epic 公开 catalog API (`freeGamesPromotions`) 自动拉取
- 📚 **Library 关联** — 使用 Epic 的 `library-service` API 标记已拥有游戏
- 🖼️ **丰富游戏卡片** — 封面图、标题、原价、免费时段、"剩 N 天"徽章
- 🎯 **一键领取链接** — 每个游戏生成专属 checkout URL，点击直达 Epic 购买页（已预填 offer）
- ⏰ **定时检查** — APScheduler 每周触发（可配置日/小时）
- 🔌 **REST API** — `/docs` 开箱即用 Swagger UI
- 🛡️ **Fernet 加密 token 存储**（AES-128-CBC + HMAC），文件权限 `0600`
- 🐳 **多架构 Docker 镜像**（`linux/amd64` + `linux/arm64`）

### 🚧 路线图 — 正在努力实现

- 🎮 **真正的自动领取** — 寻找绕过浏览器限制的路径（TrustedServer policy、GQL 突变，或浏览器兜底）
- 👥 **多账号支持** — 当前单槽位凭据存储，需重构为 N 个账号
- 🪟 **内置浏览器兜底** — API 路径被封时，回退到内置 headless Chromium
- 📲 **推送通知** — 新一周游戏上线时立即推送（支持 Telegram / 邮件 / Webhook）
- 🌍 **多地区支持** — 当前硬编码 `zh-CN/CN`，需支持多 locale

---

## 🚀 快速开始

### 1. 启动

```bash
docker run -d \
  --name epic-helper \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. 授权

打开 **http://localhost:8000**：

1. 点击 **"🔑 Epic 设备码授权"** 区块
2. 复制 `user_code`，点击 Epic 授权链接
3. 在自己浏览器登录 Epic 账号并授权设备
4. Web UI 自动检测授权成功并保存 token

之后每周免费游戏都会自动追踪。

---

## 🐳 Docker Compose

```yaml
services:
  epic-helper:
    image: zz3656/epic-games-helper:latest
    container_name: epic-games-helper
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - AUTO_CLAIM_ENABLED=true
    volumes:
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

| 存储 | 加密 | 文件 |
|---|---|---|
| Device Auth Token | Fernet (AES-128-CBC + HMAC) | `/app/data/device_auth.enc`（`0600`）|
| Master key | 明文 | `/app/data/.env`（`0600`）|

**只存储 OAuth token，不存密码。**

---

## ⚙️ 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 密钥（显式设置可跨容器重建保留 token）|
| `TZ` | `Asia/Shanghai` | 定时器时区 |
| `SCHEDULE_DAY` | `thu` | 触发日（`mon`–`sun`）|
| `SCHEDULE_HOUR` | `17` | 触发小时（`0`–`23`）|
| `SCHEDULE_MINUTE` | `0` | 触发分钟（`0`–`59`）|
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动检查 |

---

## 🛠️ API

Swagger 文档：**http://localhost:8000/docs**

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/free-games` | GET | 本周免费游戏 + 是否已拥有 + 领取链接 |
| `/api/device-auth/status` | GET | 设备码授权是否已配置 |
| `/api/device-auth/account-info` | GET | 验证已存储账号是否仍可用 |
| `/api/device-auth/request` | POST | 申请 device code |
| `/api/device-auth/poll/{code}` | GET | 轮询授权状态 |
| `/api/device-auth/claim-now` | POST | 生成本周游戏领取链接 |
| `/api/claim/progress/{id}` | GET | 轮询领取进度 |
| `/api/device-auth` | DELETE | 撤销授权 |
| `/api/auto-claim/toggle` | POST | 开关自动检查 |
| `/api/history` | GET | 历史记录 |

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────┐
│  Web UI（浏览器）                                   │
│  • 设备码登录区块                                  │
│  • 每账号游戏库（已拥有 / 可领取）                  │
│  • 每个游戏一键领取按钮                            │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│  FastAPI 后端（端口 8000）                          │
│  • /api/device-auth/*      OAuth 流程               │
│  • /api/free-games         周免游戏 + 库检查        │
│  • /api/device-auth/claim-now  生成 checkout URL    │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│  EpicAPIClient（纯 HTTP，无浏览器）                 │
│  • freeGamesPromotions  → 本周免费游戏              │
│  • library-service      → 已拥有检查                │
│  • /store/purchase （只读，为真正的自动领取保留）  │
└──────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── epic_api.py            # 🎯 纯 HTTP Epic 客户端
│   ├── api_device_auth.py     # 设备码 + 免费游戏 API
│   ├── scheduler.py           # APScheduler 定时器
│   ├── credential_store.py    # Fernet 加密
│   ├── storage.py             # 历史持久化
│   ├── result.py              # 数据模型
│   ├── config.py              # 环境变量
│   └── static/
│       ├── device_auth.js     # 前端逻辑
│       └── style.css
├── scripts/
│   └── entrypoint.sh          # 容器入口
├── Dockerfile
├── docker-compose.yml
└── README-zh-CN.md
```

---

## 🐛 故障排查

**设备码授权持续失败** — 打开 Web UI 的"🛠 调试选项"面板，测试按钮会打印实际 Epic API 响应。

**容器重启后 `Master key 不匹配`**：
```bash
rm ./data/device_auth.enc
# Web UI 重新授权
```

**`/store/purchase` 返回 `HTTP 403`** — 这是预期的，Epic 需要浏览器 session cookie，我们伪造不了。点击生成的 checkout URL（一键即可）。

---

## 🙏 致谢与灵感来源

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — "用 Device Code OAuth + 生成 checkout URL"思路的原始项目；本项目是该思路的 Python 重实现。
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic API 详尽逆向文档。
- **[xMistt/rebootpy](https://github.com/xMistt/rebootpy)** — Python 实现的 User-Agent + auth header 参考。
- **[Heroic-Games-Launcher/legendary](https://github.com/Heroic-Games-Launcher/legendary)** — `library-service` API 端点结构参考。
- **[LeleDerGrasshalmi/FortniteEndpointsDocumentation](https://github.com/LeleDerGrasshalmi/FortniteEndpointsDocumentation)** — 社区维护的端点文档。

---

## ⚠️ 免责声明

本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)。作者不对账号被封、数据丢失等任何损失负责。

## 📝 License

MIT
# 🎮 Epic Games 商店追踪器

> **本周促销 · 免费游戏 · 历史赠送清单 · 零依赖。**
>
> 追踪 Epic 商店打折与免费游戏 · 记录历史赠送清单 · 用户认证 & 通知推送 · 镜像 ~150MB。

🇺🇸 [English README](README.md)

---

## 📌 这是什么？

`epic-games-helper` 是一个**轻量级 HTTP API + Web UI** 服务，帮助你追踪 Epic 商店折扣与免费游戏。

- 🏷️ **本周促销** — 当前商店打折游戏，展示折扣比例、原价/现价、历史最低价
- 🎮 **免费游戏追踪** — Epic 每周免费游戏（北京时间每周五 0:00 更新）
- 📅 **预告** 下周即将免费的 Epic 游戏
- 🗂️ **记录** 每周赠送过的游戏（永久历史，按周分组）
- 🎯 **跳转 Epic 商店** — 点击直达 Epic 商品页
- 👤 **用户账户** — 注册、登录、配置个人推送渠道
- 📲 **Webhook 推送** — 通过 Server 酱（微信）或 Telegram Bot 通知

> **浏览无需登录。** 免费游戏和促销数据来自 Epic 公开 API。登录是可选的 — 仅在需要推送通知时使用。

---

## ✨ 功能

图例：**✅ 已实现** · **🚧 开发中** · **❌ 不实现**

### 核心功能

| 状态 | 功能 |
|------|------|
| ✅ | **本周促销追踪** — 当前商店打折游戏，折扣比例、原价/现价、历史最低价对比 |
| ✅ | **本周免费游戏追踪** — 从 Epic 公开 API (`freeGamesPromotions`) 自动拉取 |
| ✅ | **下周预告** — 显示 Epic 已公布的下一周免费游戏 |
| ✅ | **紧凑领取历史** — ISO 周分组，横向卡片：缩略图 + 标题 + 日期 + 价格 |
| ✅ | **首字占位** — 没有图片的游戏显示首字符 |
| ✅ | **精准商品页链接** — 使用 Epic 商品页 slug |
| ✅ | **跳转商店** — 一键直达 Epic 商品页 |

### Web UI（Epic 风格）

| 状态 | 功能 |
|------|------|
| ✅ | **纯黑画布 + 电光蓝**（`#0078F2`）— 对齐 Epic 商店设计 |
| ✅ | **顶部 sticky 导航** |
| ✅ | **Hero 横幅** |
| ✅ | **本周促销游戏网格** — 封面、标题、折扣、价格、商店链接 |
| ✅ | **本周免费游戏网格** — 封面、标题、日期、原价、商店链接 |
| ✅ | **历史赠送清单** — 按周分组，横向卡片排列 |
| ✅ | **完全响应式** — 手机 / 平板 / 桌面 |
| ✅ | **调试面板** + API 测试按钮 |

### 定时任务

| 状态 | 功能 |
|------|------|
| ✅ | **APScheduler 定时任务**（默认：北京时间每周五 0:05）|
| ✅ | **Fingerprint 对比** — 游戏变化时才写入历史 |
| ✅ | **下次运行时间** 在 health API 中返回 |

### 多用户 & 通知推送

| 状态 | 功能 |
|------|------|
| ✅ | **用户注册 & 登录** — JWT 认证，数据存于 `data/users.json` |
| ✅ | **独立推送配置** — 每个用户可配置自己的通知渠道 |
| ✅ | **Webhook 推送** — 检测到新免费游戏时推送，支持 2 种渠道： |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Server 酱**（微信） |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Telegram Bot**（群组/频道） |
| ✅ | **全局 + 用户推送** — 同时支持全局（`NOTIFY_WEBHOOK_*`）和每个用户的推送渠道 |
| ✅ | **测试推送** — 可在 UI 中测试推送配置是否正确 |
| ✅ | **退出登录** — 可在 UI 中退出 |

### 基础设施

| 状态 | 功能 |
|------|------|
| ✅ | **多架构 Docker 镜像**（`linux/amd64` + `linux/arm64`）|
| ✅ | **镜像体积 ~150MB**（无 Chromium / Playwright / X11）|
| ✅ | **REST API** + Swagger UI（`/docs`）|
| ✅ | **Docker Compose** 一键部署 |
| ✅ | **GitHub Actions CI** — 每次 PR 自动校验 |

### 不实现的功能

| 状态 | 功能 | 原因 |
|------|------|------|
| ❌ | 真正零点击自动领取 | Epic 需要浏览器 session cookie、XSRF token、hCaptcha — 无法通过 API 伪造 |
| ❌ | 自动领取 | 不需要 — 免费游戏数据是公开的，本项目仅提供追踪与历史记录 |
| ❌ | 完整游戏库 | Epic `library-service` API 需要 OAuth authorization_code flow，Epic 不允许 localhost redirect_uri |

---

## 🚀 快速开始

### 1. Docker 启动

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. 打开浏览器

访问 **http://localhost:8080** — 不需要登录，不需要配置。

页面显示：
- **本周促销** — 封面、标题、折扣、价格、商店链接
- **本周免费游戏** — 封面、标题、日期、价格、商店链接
- **历史赠送清单** — 每周免费游戏按周分组展示

### 3.（可选）配置定时任务

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  -e TZ=Asia/Shanghai \
  -e SCHEDULE_DAY=fri \
  -e SCHEDULE_HOUR=0 \
  -e SCHEDULE_MINUTE=5 \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
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
      - "8080:8080"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=fri
      - SCHEDULE_HOUR=0
      - SCHEDULE_MINUTE=5
    volumes:
      - ./logs:/app/logs       # 历史记录 + 封面映射
      - ./data:/app/data       # 用户数据 + 配置密钥
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

> 📌 **多架构镜像**：`linux/amd64` 和 `linux/arm64`（群晖、威联通、Unraid、Raspberry Pi 4+ 都能跑）

### 💾 数据持久化

所有数据通过 Docker volume 挂载到宿主机目录：

| 挂载卷 | 内容 |
|--------|------|
| `./logs:/app/logs` | 历史记录（`history.json`）、封面映射 |
| `./data:/app/data` | 用户数据（`users.json`）、`.env` 配置 |

> **数据不会丢失：** 只要保留 `./logs` 和 `./data` 目录，重建容器或更新镜像都不会影响你的历史记录和用户数据。

---

## 🛠️ API

Swagger 文档：**http://localhost:8080/docs**

### 促销 & 免费游戏 & 历史

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查（包含下次运行时间）|
| `/api/free-games` | GET | 本周 + 下周免费游戏（封面、日期、价格、商店链接）|
| `/api/promotions` | GET | 当前商店促销游戏（封面、标题、折扣、价格、商店链接）|
| `/api/history` | GET | 领取历史（最近 200 条）|
| `/api/history/latest` | GET | 最新一条历史 |

### 定时任务 & 调试

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scheduler/test-run` | POST | 手动触发定时检查（调试用）|

### 用户认证

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 注册用户 |
| `/api/auth/login` | POST | 登录（返回 JWT token）|
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/me` | GET | 获取当前用户信息 |
| `/api/auth/push-config` | GET | 获取当前用户推送配置 |
| `/api/auth/push-config` | PUT | 更新推送配置 |
| `/api/auth/test-push` | POST | 测试推送 |

---

## 🏗️ 架构

```
┌────────────────────────────────────────────────────────────┐
│  Web UI（浏览器）                                          │
│  • Epic 风格（纯黑 + #0078F2）                            │
│  • 本周免费游戏网格                                       │
│  • 历史赠送清单（按周分组）                               │
│  • 登录/注册弹窗                                          │
│  • 推送设置弹窗（用户独立渠道配置）                        │
│  • 调试面板 + API 测试按钮                                │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  FastAPI 后端（端口 8080）                                │
│  • /api/free-games             本周 + 下周游戏             │
│  • /api/promotions             本周促销折扣                │
│  • /api/history                领取历史                    │
│  • /api/auth/*                 注册/登录/推送配置          │
│  • /api/scheduler/*            手动触发                    │
│  • APScheduler                 每周五 0:05 定时检查        │
│  • Notifier                    Webhook 推送（Server 酱 / Telegram）│
│  • UserStore                   基于 JSON 的用户存储        │
│  • JWT Auth                    Token 认证                  │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  EpicAPIClient（纯 HTTP，无浏览器）                        │
│  • searchStore (BASE_GAME + discounts)  → 促销             │
│  • freeGamesPromotions          → 本周 + 下周游戏         │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  推送渠道                                                  │
│  • Server 酱（微信） / Telegram Bot                         │
│  • 全局 + 用户独立推送                                     │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── epic_api.py            # 纯 HTTP Epic 客户端（freeGamesPromotions）
│   ├── scheduler.py           # APScheduler 定时检查 + fingerprint + 推送
│   ├── notifier.py            # Webhook 推送（Bark / Server 酱 / PushPlus / Telegram）
│   ├── storage.py             # 历史持久化（deque + JSON 文件）
│   ├── user_store.py          # 用户数据存储（JSON + bcrypt）
│   ├── auth.py                # JWT 认证模块
│   ├── api_users.py           # 用户管理 API（登录/注册/推送配置）
│   ├── result.py              # 数据模型
│   ├── config.py              # 环境变量
│   └── static/
│       ├── device_auth.js     # 页面初始化 + 工具函数（~130 行）
│       ├── free_games.js      # 游戏卡片渲染 + 历史（~260 行）
│       ├── auth_core.js       # 认证核心（登录/注册弹窗）
│       ├── auth_settings.js   # 推送设置弹窗 + 用户 UI
│       └── style.css          # Epic 设计系统（~20 KB）
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

**点击链接后 Epic 显示错误** — Epic 前端 JS 调用 `cartOffersValidation` 失败。常见原因：(1) 浏览器未登录 Epic，(2) Epic EULA 未接受，(3) 2FA 未启用。先在浏览器登录 Epic 并接受 EULA，在 Epic 账户安全设置中启用 2FA，然后重试。

**容器无法启动** — 查看 `docker logs epic-games-helper`。常见原因：端口 `8080` 被占用，修改 `-p` 左侧的映射。

---

## 🙏 致谢

- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic `freeGamesPromotions` API 接口与响应结构文档

---

## ⚠️ 免责声明

本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)。作者不对账号被封、数据丢失等任何损失负责。

## 📝 License

MIT

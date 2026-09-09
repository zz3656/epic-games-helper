# 🎮 Epic Games 免费游戏自动领取

> 基于 **Docker + Epic OAuth Device Code** 的周免游戏自动领取服务。**零浏览器、零验证码**。

🇺🇸 [English README](README.md)

## ✨ 两种认证方式

本项目支持 **两种登录模式**，任选其一：

### 🎯 推荐：**设备码授权（零验证码）**

> 灵感来自 [claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)——使用 Epic 官方的 OAuth device code 流程。

| 特性 | 优势 |
|------|------|
| ⚡ **一次授权永久使用** | 用户在自己浏览器登录一次，工具获得永不过期的 token |
| 🚫 **零 hCaptcha** | 登录走 Epic 官方 OAuth 页面，没有任何自动化特征 |
| 📦 **零 Playwright/Chromium** | 纯 HTTP API 调用，容器从 ~1GB 降到 ~150MB |
| 🛡️ **零 IP 风控** | 浏览器登录从你电脑的 IP 出发，不是服务器 IP |
| ♾️ **永不过期** | 只有你手动撤销 Epic 设备授权才会失效 |

### 🔐 备选：**账号密码（浏览器自动化）**

适用于无法使用设备码或临时测试的用户。使用 Playwright + 反检测 stealth——但偶尔会遇到 hCaptcha。

| 优点 | 缺点 |
|------|------|
| 一步登录，简单直接 | 可能触发 hCaptcha（会尝试自动解决） |
| 任何网络环境都可以用 | 需要 Playwright + Chromium（容器 ~1GB） |

## 🚀 快速开始

### 1. 启动

```bash
docker compose up -d
```

> 💡 **无需手动创建 `.env` 文件！** 容器首次启动时会自动生成 `EPIC_MASTER_KEY` 并保存到 `./data/.env`。

打开：**http://localhost:8000**

### 2. 授权（任选其一）

**方式 A：设备码授权（推荐）**
1. Web UI → "🎯 Epic 设备码登录" 区块
2. 点击 "🔑 Epic 设备码授权"
3. 复制 `user_code`，点击链接跳转到 Epic 官方授权页面
4. 在浏览器登录 Epic 账号并授权设备
5. Web UI 自动保存 token，之后每周自动领取无需重新登录

**方式 B：账号密码**
1. Web UI → "🔁 保存凭证 · 每周自动领取" 区块
2. 输入 Epic 邮箱 + 密码
3. 点击 "💾 保存凭证（加密）"

### 3. 等待自动领取

默认调度：**每周四 17:00 北京时间**。可在 Web UI 查看历史记录。

## 🐳 Docker Compose

```yaml
services:
  epic-claimer:
    image: zz3656/epic-games-claimer:latest
    container_name: epic-games-claimer
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - AUTO_CLAIM_ENABLED=true
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **多架构镜像**：支持 `linux/amd64` 和 `linux/arm64`（群晖、威联通等 ARM 设备也能跑）

## 🔐 隐私与安全

| 存储内容 | 加密方式 | 文件 |
|---------|---------|------|
| Device Auth Token | Fernet (AES-128-CBC) | `/app/data/device_auth.enc` (0600) |
| 账号密码 | Fernet (AES-128-CBC) | `/app/data/credentials.enc` (0600) |
| 主密钥 | 明文 | `/app/data/.env` (0600) |

**设备码模式**只存储 `{account_id, device_id, secret, access_token, refresh_token}`——**没有密码**，领取时无需重新输入。

## ⚙️ 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 加密密钥 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 周几触发（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时（0-23） |
| `SCHEDULE_MINUTE` | `0` | 触发分钟（0-59） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |

## 🛠️ API

启动后访问 **http://localhost:8000/docs** 查看完整 API 文档。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/claim` | POST | 手动领取（账号密码） |
| `/api/device-auth/request` | POST | 申请 device code |
| `/api/device-auth/poll/{code}` | GET | 轮询授权状态 |
| `/api/device-auth/status` | GET | 查询 device auth 状态 |
| `/api/device-auth/test/free-games` | POST | 调试：测试免费游戏 API |
| `/api/device-auth/test/request` | POST | 调试：测试 device code 申请 |
| `/api/device-auth/test/claim` | POST | 调试：用 token 测试领取流程 |
| `/api/credentials` | POST/DELETE | 保存/删除凭证 |
| `/api/auto-claim/toggle` | POST | 开关自动领取 |
| `/api/history` | GET | 历史记录 |

## 🐛 故障排查

### 设备码授权失败

Web UI → "🛠 调试选项" → 点击 "测试免费游戏 API" 或 "测试申请 device code"——输出会显示 Epic API 的实际错误。常见原因：

- **Client ID 失效**：Epic 轮换公共 client ID。修改 `app/epic_api.py` 中的 `EPIC_CLIENT_ID`
- **容器网络问题**：容器无法访问 Epic API。检查防火墙/代理
- **被限流**：请求太频繁，等待 10 分钟

### 浏览器模式（账号密码）触发 hCaptcha

1. 自动点击 checkbox（最多 3 次，每次等 8 秒）
2. 如果还在，等 30 秒让 Epic 服务端验证
3. 如果仍然失败，错误信息会显示具体提示

### Master key 变更导致凭证无法解密

```
ERROR 解密失败：master key 与凭证不匹配
```

解决：Web UI → "🗑 删除凭证" → 重新保存。

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────┐
│  Web UI（浏览器）                                         │
│  • 设备码登录区块 + 调试面板                                │
│  • 账号密码区块                                            │
│  • 自动领取开关 + 历史记录                                  │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  FastAPI 后端（端口 8000）                                │
│  • /api/device-auth/*     设备码授权流程                   │
│  • /api/claim              手动领取                        │
│  • /api/credentials        凭证加密存取                    │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  Scheduler（自动选择认证模式）                              │
│                                                          │
│  有 device auth token?                                    │
│    YES → EpicAPIClient（纯 HTTP，零验证码）                │
│    NO  → EpicClaimer（Playwright + 反检测）               │
└──────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
epicgames/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── claimer.py             # Playwright 领取核心
│   ├── claimer_login.py       # 登录逻辑 + hCaptcha
│   ├── claimer_captcha.py     # hCaptcha 自动解决
│   ├── claimer_games.py       # 浏览器抓取 + 领取游戏
│   ├── epic_api.py            # 🎯 纯 HTTP API 客户端（device auth）
│   ├── api_device_auth.py     # 设备码授权 API
│   ├── api_vnc.py             # VNC 状态（已弃用）
│   ├── credential_store.py    # Fernet 加密
│   ├── scheduler.py           # 自动选择认证模式
│   └── ...
├── scripts/
│   └── entrypoint.sh          # 容器入口
├── Dockerfile
├── docker-compose.yml
└── README-zh-CN.md
```

## ⚠️ 免责声明

- 本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)
- 频繁自动操作可能触发账号风控
- 作者不对账号被封、数据丢失等任何损失负责

## 📝 License

MIT

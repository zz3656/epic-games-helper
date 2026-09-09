# 🎮 Epic Games 免费游戏自动领取

> 基于 **Epic OAuth Device Code** 的周免游戏自动领取服务。**零浏览器、零验证码、零 Playwright**。

🇺🇸 [English README](README.md)

## ✨ 单一认证方式：**设备码授权**

| 特性 | 优势 |
|------|------|
| ⚡ **一次授权永久使用** | 用户在自己浏览器登录一次，工具获得永不过期的 token |
| 🚫 **零 hCaptcha** | 登录走 Epic 官方 OAuth 页面，没有任何自动化特征 |
| 📦 **零 Playwright/Chromium** | 纯 HTTP API 调用，容器仅 ~150MB |
| 🛡️ **零 IP 风控** | 浏览器登录从你电脑的 IP 出发，不是服务器 IP |
| ♾️ **永不过期** | 只有你手动撤销 Epic 设备授权才会失效 |

## 🚀 快速开始

### 1. 启动

```bash
docker run -d \
  --name epic-claimer \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-claimer:latest
```

### 2. 授权

打开 **http://localhost:8000**：

1. 进入 "🎯 Epic 设备码登录" 区块
2. 点击 "🔑 Epic 设备码授权"
3. 复制 `user_code`，点击链接跳转到 Epic 官方授权页
4. 在自己浏览器登录 Epic 账号并授权设备
5. Web UI 自动保存 token，之后每周自动领取

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
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **多架构镜像**：支持 `linux/amd64` 和 `linux/arm64`（群晖、威联通、Unraid 等 ARM 设备也能跑）

## 🔐 隐私与安全

| 存储 | 加密 | 文件 |
|---|---|---|
| Device Auth Token | Fernet (AES-128-CBC) | `/app/data/device_auth.enc` (0600) |
| Master key | 明文 | `/app/data/.env` (0600) |

**只存储 token，不存储密码。**

## ⚙️ 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 加密密钥 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 周几触发（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时（0-23） |
| `SCHEDULE_MINUTE` | `0` | 触发分钟（0-59） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |

## 🛠️ API

API 文档：**http://localhost:8000/docs**

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/device-auth/request` | POST | 申请 device code |
| `/api/device-auth/poll/{code}` | GET | 轮询授权状态 |
| `/api/device-auth/status` | GET | 查询 device auth 状态 |
| `/api/device-auth/claim-now` | POST | 用 token 立即领取 |
| `/api/claim/progress/{id}` | GET | 轮询领取进度 |
| `/api/device-auth` | DELETE | 撤销授权 |
| `/api/device-auth/test/*` | POST | 调试端点 |
| `/api/auto-claim/toggle` | POST | 开关自动领取 |
| `/api/history` | GET | 历史记录 |

## 🐛 故障排查

### 设备码授权失败

Web UI → "🛠 调试选项" → 点击测试按钮，输出会显示 Epic API 的实际错误。常见原因：

- **所有 client_id 都失效**：Epic 轮换了 OAuth 客户端。修改 `app/epic_api.py` 中的 `EPIC_CLIENTS`
- **容器网络问题**：容器无法访问 Epic API
- **被限流**：请求太频繁，等待 10 分钟

### Master key 不匹配

```bash
rm ./data/device_auth.enc
# Web 界面重新授权
```

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│  Web UI（浏览器）                                 │
│  • 设备码登录 + 立即领取 + 自动领取开关            │
│  • 历史记录 + 调试面板                            │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  FastAPI 后端（端口 8000）                        │
│  • /api/device-auth/*    设备码授权              │
│  • /api/device-auth/claim-now  立即领取         │
│  • /api/auto-claim/toggle 开关                   │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  Scheduler（每周四 17:00）                        │
│  EpicAPIClient → 纯 HTTP API 调用                │
└──────────────────────────────────────────────────┘
```

## 📁 项目结构

```
epicgames/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── epic_api.py            # 🎯 纯 HTTP API 客户端
│   ├── api_device_auth.py     # 设备码授权 API
│   ├── scheduler.py           # 定时调度
│   ├── credential_store.py    # Fernet 加密
│   ├── storage.py             # 结果持久化
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

## 🙏 致谢与灵感来源

本项目站在巨人的肩膀上，特别感谢：

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — 使用 Epic **Device Code OAuth 流程**代替账号密码登录的原始灵感。OAuth 的两步走流程（client_credentials → device_code）直接借鉴了他们的实现。
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic 非公开 API 的详尽逆向工程文档。OAuth client 列表、grant type 规范、endpoint URL 都来源于这份研究。
- **[xMistt/rebootpy](https://github.com/xMistt/rebootpy)** — Python Epic Games 库。提供了正确的 User-Agent header 和 account_service endpoint 格式参考。
- **[FortniteEndpointsDocumentation](https://github.com/LeleDerGrasshalmi/FortniteEndpointsDocumentation)** — 社区维护的 endpoint 文档。

如果你 fork 或基于本项目开发，请保留对原作者的致谢。

## ⚠️ 免责声明

- 本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)
- 作者不对账号被封、数据丢失等任何损失负责

## 📝 License

MIT

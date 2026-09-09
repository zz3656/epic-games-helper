# 🎮 Epic Games 自动领取

> 每周自动领取 Epic Games 免费游戏。**设备码授权** · 零浏览器 · 零验证码 · 容器 ~150MB。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![Docker Pulls](https://img.shields.io/docker/pulls/zz3656/epic-games-claimer.svg?style=flat)](https://hub.docker.com/r/zz3656/epic-games-claimer)
[![Multi-arch](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-lightgrey.svg)](https://hub.docker.com/r/zz3656/epic-games-claimer)

---

## ✨ 单一认证方式：**设备码授权**

- ⚡ 一次授权永久使用
- 🚫 零 hCaptcha / 零自动化检测
- 📦 容器体积仅 ~150MB（无 Chromium）
- 🛡️ 服务器 IP 不会被 Epic 风控
- ♾️ Token 永不过期（除非手动撤销）

---

## 🚀 快速开始

```bash
docker run -d \
  --name epic-claimer \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-claimer:latest
```

打开 **http://localhost:8000**

1. 进入 "🎯 Epic 设备码登录" 区块
2. 点击 "🔑 Epic 设备码授权"
3. 复制 `user_code`，点击链接跳转 Epic 官方授权页
4. 在自己浏览器登录 Epic 账号并授权设备
5. 完成后 Web UI 自动保存 token

之后每周自动领取，无需任何操作。

---

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

---

## 🔐 隐私与安全

| 存储 | 加密 | 文件 |
|---|---|---|
| Device Auth Token | Fernet (AES-128-CBC) | `/app/data/device_auth.enc` (0600) |
| Master key | 明文 | `/app/data/.env` (0600) |

**只存储 token，不存储密码。**

---

## ⚙️ 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 密钥 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 触发日（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时 |
| `SCHEDULE_MINUTE` | `0` | 触发分钟 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |

---

## 🛣️ 多架构支持

| 架构 | 支持 |
|---|---|
| linux/amd64 | ✅ |
| linux/arm64 | ✅ |

群晖、威联通、Unraid 等 ARM 设备也能跑。

---

## 🐛 故障排查

**设备码授权失败** — 在 Web UI "🛠 调试选项" 板块点击测试按钮，输出会显示 Epic API 的实际错误。

**Master key 不匹配**：
```bash
rm ./data/device_auth.enc
# Web 界面重新授权
```

---

## 🙏 Credits

- [claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node) — Original inspiration for the **Device Code OAuth flow**
- [MixV2/EpicResearch](https://github.com/MixV2/EpicResearch) — Comprehensive Epic API documentation
- [xMistt/rebootpy](https://github.com/xMistt/rebootpy) — Python Epic library & auth headers

## 📜 License

MIT

---

> GitHub: [zz3656/epic-games-claimer](https://github.com/zz3656/epic-games-claimer)
> Docker Hub: [zz3656/epic-games-claimer](https://hub.docker.com/r/zz3656/epic-games-claimer)

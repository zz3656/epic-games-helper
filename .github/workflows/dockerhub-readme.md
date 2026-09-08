# 🎮 Epic Games 自动领取

> 每周自动领取 Epic Games 免费游戏。基于 Docker + Playwright 的容器化方案，支持「输入一次、每周自动跑」模式。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)

---

## ✨ 功能特性

| 功能 | 说明 |
|---|---|
| 🎯 **Web 可视化界面** | 浏览器打开即用，账号密码可视化输入 |
| 🔒 **隐私零留存模式** | 账号密码仅在请求内存中使用，不写文件 / 不进日志 |
| 🔁 **自动领取模式** | 账号密码 Fernet (AES-128) 加密持久化，每周自动执行 |
| 🐳 **一键 Docker 部署** | 容器化运行，环境隔离，安全加固 |
| ⏰ **APScheduler 调度** | 可配置每周任意时间触发（默认周四 17:00 北京时间） |
| 📊 **历史记录** | 查看过往领取结果（已脱敏） |
| 🛡️ **安全加固** | 容器无特权模式、资源限制、加密文件 0600 权限 |

---

## 🚀 快速开始

### 1. 生成 master key（仅"自动领取"模式需要）

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出粘贴到 `.env` 文件的 `EPIC_MASTER_KEY=...`。

### 2. Docker Run

```bash
docker pull zz3656/epic-games-claimer:latest

docker run -d \
  --name epic-claimer \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/screenshots:/app/screenshots \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-claimer:latest
```

### 3. Docker Compose

```yaml
services:
  epic-claimer:
    image: zz3656/epic-games-claimer:latest
    container_name: epic-games-claimer
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - HEADLESS=true
      - AUTO_CLAIM_ENABLED=true
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

### 4. 访问 Web 界面

打开：**http://localhost:8000**

- **立即领取**：账号密码仅在请求中使用，领取完立即清空
- **保存凭证 · 自动领取**：加密保存账号密码，每周自动跑

---

## 🔐 隐私与安全

| 数据 | 处理方式 |
|---|---|
| 账号密码（立即领取模式） | 仅请求作用域内，函数返回后 GC 回收 |
| 账号密码（自动领取模式） | Fernet (AES-128-CBC + HMAC) 加密 + 0600 权限 |
| Master key | 通过 `.env` 文件管理，**不入 git** |
| Cookie / Session | 每次新 BrowserContext，领取后立即销毁 |
| 日志 | 永不记录完整密码；用户名已脱敏 |

⚠️ `EPIC_MASTER_KEY` 是自动领取模式的唯一防线：泄露即等于凭证泄露，请用密码管理器妥善保管。

---

## ⚙️ 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `EPIC_MASTER_KEY` | *必填* | Fernet 密钥（自动领取模式） |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 触发日（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时 |
| `SCHEDULE_MINUTE` | `0` | 触发分钟 |
| `HEADLESS` | `true` | 浏览器无头模式 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |

---

## 🐛 故障排查

**登录失败** — Epic 经常改版或触发人机验证：
- 检查 `/app/screenshots/login_failed_*.png` 截图
- 查看容器日志：`docker compose logs -f`

**Master key 变更后凭证无法解密**：
```bash
# 1. 进入容器删除旧凭证
docker exec -it epic-games-claimer rm /app/data/credentials.enc
# 2. Web 界面重新保存凭证
```

---

## 📜 License

MIT

---

> GitHub: [zz3656/epic-games-claimer](https://github.com/zz3656/epic-games-claimer)
> Docker Hub: [zz3656/epic-games-claimer](https://hub.docker.com/r/zz3656/epic-games-claimer)

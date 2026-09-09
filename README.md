# 🎮 Epic Games 免费游戏自动领取

> 基于 **Docker + Playwright** 的 Epic Games 周免游戏自动领取服务，带 Web 界面和零凭证留存设计。

[English README](README.md)

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🌐 **Web 可视化界面** | 浏览器打开即用，账号密码可视化输入 |
| 🔓 **立即领取** | 每次手动输入账号密码，领取完即清，零留存 |
| 🔁 **自动领取** | 输入一次，每周自动跑；Fernet (AES-128-CBC) 加密存储 |
| 🐳 **零配置启动** | 首次启动自动生成密钥，无需手动创建 `.env` |
| ⏰ **可调度** | 支持配置每周任意时间触发（默认周四 17:00 北京时间） |
| 📊 **历史记录** | 查看过往领取结果（已脱敏） |
| 🛡️ **安全加固** | 容器无特权模式、资源限制、加密文件 0600 权限 |
| 🖥️ **VNC 支持** | 可选 VNC 服务，用于手动解决 hCaptcha 验证码 |

## 🚀 快速开始

### 1. 启动

```bash
docker compose up -d
```

> 💡 **无需手动创建 `.env` 文件！** 容器首次启动时会自动生成 `EPIC_MASTER_KEY` 并保存到 `./data/.env`。

查看生成的密钥：

```bash
docker compose logs | grep EPIC_MASTER_KEY
# 或直接查看文件：
cat ./data/.env
```

打开：**http://localhost:8000**

### 2. 启用自动领取（一次性配置）

在 Web 界面的 **"💾 保存凭证（加密）"** 区块：
1. 输入 Epic 账号密码
2. 勾选"保存后启用每周自动领取"
3. 点击保存

之后每周定时（默认周四 17:00 北京时间）会自动登录并领取。

### 3. 管理自动领取

- **关闭开关**：Web 界面 → "自动领取开关"
- **删除凭证**：Web 界面 → "🗑 删除凭证" 按钮
- **查看历史**：Web 界面 → 历史记录表格

### 4. Docker Compose 配置示例

默认配置（不启用 VNC）：

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
      - HEADLESS=true
      - AUTO_CLAIM_ENABLED=true
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

启用 VNC（手动验证 hCaptcha 用）：

```yaml
services:
  epic-claimer:
    image: zz3656/epic-games-claimer:latest
    container_name: epic-games-claimer
    restart: unless-stopped
    # 单端口设计：API 和 VNC 都通过 8000 端口访问
    # VNC 访问地址: http://服务器IP:8000/vnc-viewer
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - HEADLESS=true
      - AUTO_CLAIM_ENABLED=true
      - ENABLE_VNC=true        # 启用 VNC 服务
      # - VNC_PASSWORD=yourpw  # 可选：设置 VNC 访问密码
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **VNC 使用说明**：设置 `ENABLE_VNC=true` 后，在主界面 `http://服务器IP:8000/vnc-viewer` 新标签页打开 VNC 查看器。先在主界面点击"开始领取"，Chrome 窗口会在领取过程中出现。如果弹出 hCaptcha，在 VNC 窗口中手动完成验证即可。

## 🔐 隐私与安全

### 数据流

```
用户浏览器
   │ HTTPS（账号密码在内存中处理）
   ▼
FastAPI 进程
   │
   │ Fernet.encrypt()  ←  EPIC_MASTER_KEY 来自 .env
   ▼
/app/data/credentials.enc   ← 密文（0600 权限）
   ▲
   │ Fernet.decrypt()（每周定时触发）
   │
   ▼
内存（领取流程中）
   │
   │ 流程结束后 clear()
   ▼
引用置 None → GC 回收
```

### 加密细节

- **算法**：Fernet（**AES-128-CBC** + HMAC-SHA256）
- **文件权限**：`0600`（仅容器内 root 可读）
- **密钥来源**：`.env` 中的 `EPIC_MASTER_KEY`（不入 git）

### 威胁模型

| 攻击场景 | 后果 |
|---------|------|
| 攻击者拿到 `credentials.enc` 但无 key | 🔒 无法解密 → 安全 |
| 攻击者拿到 `credentials.enc` + key | ⚠️ 凭证完全泄露 |
| 攻击者能 attach 到运行中的容器进程 | 进程内明文密码可见（仅运行时） |
| 日志泄露 | 账号密码永不写日志（已脱敏） |

### ⚠️ 重要提醒

- **`EPIC_MASTER_KEY` 是唯一的防线**，请：
  - 用密码管理器保管，不要贴到聊天/issue/截图里
  - 定期更换（换 key 后需重新输入账号密码保存）
- 如果怀疑 key 泄露 → 立刻删除凭证 + 换 key + 改 Epic 密码
- 推荐用 Epic 小号而非主力号

## 📁 项目结构

```
epicgames/
├── app/
│   ├── main.py                # FastAPI 入口 + API 路由
│   ├── claimer.py             # Playwright 领取核心
│   ├── claimer_login.py       # 登录逻辑
│   ├── claimer_login_form.py  # 表单填充
│   ├── claimer_login_post.py  # POST 提交
│   ├── claimer_browser.py     # 浏览器管理
│   ├── claimer_games.py       # 游戏抓取与领取
│   ├── claimer_captcha.py     # 验证码检测
│   ├── scheduler.py           # APScheduler 定时调度
│   ├── credential_store.py    # 🔒 Fernet 加密凭证存取
│   ├── storage.py             # 结果存储
│   ├── config.py              # 环境变量配置
│   ├── api_vnc.py             # VNC 状态 + 截图 API
│   ├── api_vnc_ws.py          # VNC WebSocket 代理
│   └── static/                # 前端资源 + noVNC
├── scripts/
│   ├── build-and-run.sh
│   └── entrypoint.sh          # 🐳 容器入口（自动生成密钥、VNC 启动）
├── Dockerfile
├── docker-compose.yml
├── .env.example               # 环境变量模板
├── .env                       # 密钥文件（自动生成，gitignore）
├── requirements.txt
├── logs/                      # 领取日志
├── screenshots/               # 异常截图
└── data/                      # 凭证密文持久化目录
```

## ⚙️ 配置

所有配置通过环境变量管理。容器首次启动时会自动生成 `EPIC_MASTER_KEY` 并写入 `./data/.env`，后续启动自动读取。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 加密密钥 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 周几触发（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时（0-23） |
| `SCHEDULE_MINUTE` | `0` | 触发分钟（0-59） |
| `HEADLESS` | `true` | 浏览器无头模式 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |
| `ENABLE_VNC` | `false` | 启动 VNC 服务（用于手动解决 hCaptcha） |
| `VNC_PASSWORD` | *(空)* | VNC 访问密码（不设置则无密码） |

## 🛠️ API

启动后访问 **http://localhost:8000/docs** 查看完整 API 文档。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + 状态 |
| `/api/claim` | POST | 立即领取（明文账号密码） |
| `/api/claim/verification` | POST | 提交邮箱验证码 |
| `/api/credentials` | POST | 保存加密凭证 |
| `/api/credentials` | DELETE | 删除凭证 |
| `/api/credentials/status` | GET | 查询凭证状态 |
| `/api/auto-claim/toggle` | POST | 开关自动领取 |
| `/api/history` | GET | 历史记录 |
| `/api/vnc/status` | GET | VNC 服务状态 |
| `/vnc-viewer` | GET | 嵌入式 VNC 查看器页面 |
| `/vnc-ws` | WS | VNC WebSocket 代理 |

## 🐛 故障排查

### 1. 登录失败

Epic Games 经常改版或触发人机验证：
- 设置 `ENABLE_VNC=true` 并启用 VNC，用浏览器手动操作
- 检查 `/app/screenshots/login_failed_*.png` 截图
- 查看 `docker compose logs -f`

### 2. hCaptcha 验证

如果 Epic 弹出 hCaptcha 图形验证，Web 界面会明确提示：

1. **账号或密码错误**（🔑）：检查输入是否正确
2. **需要 hCaptcha 验证**（🧩）：需要手动验证
   - **启用 VNC 后**：点击失败通知中的蓝色「🎯 点击这里打开 noVNC」按钮
   - 新标签页打开 VNC 查看器，在 Chrome 窗口中手动完成 hCaptcha
   - 领取任务会自动继续（等待最长 120 秒）

确保 `ENABLE_VNC=true` 已配置后再尝试。

### 3. VNC 打开黑屏

- 确认容器环境变量中设置了 `ENABLE_VNC=true`
- 查看容器日志：`docker compose logs | grep VNC`
- 正常输出应包含 `ENABLE_VNC=true - starting VNC server...` 和 `VNC setup complete.`
- 如果没有看到，说明 VNC 服务未启动，请在环境变量中添加 `ENABLE_VNC=true` 后重启容器

### 4. Master key 变更导致凭证无法解密

```
ERROR 解密失败：master key 与凭证不匹配
```

解决：删除旧凭证 → Web 界面"删除凭证" → 重新保存。

### 5. 想自定义密钥？

容器首次运行后，编辑 `./data/.env` 修改 `EPIC_MASTER_KEY`，然后重启：
```bash
docker compose restart
```

## ⚠️ 免责声明

- 本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)
- 频繁自动操作可能触发账号风控
- 作者不对账号被封、数据丢失等任何损失负责

## 🏗️ 架构

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐
│  用户浏览器   │────▶│  FastAPI (:8000) │────▶│  Chromium         │
│              │     │                │     │  (Playwright)      │
│ VNC 查看器   │────▶│  • VNC WS 代理  │────▶│                  │
│              │     │  • REST API    │     ┌──────────────────┐
│              │     │  • Web UI      │────▶│  VNC 服务器 (:5900)│
└──────────────┘     └────────────────┘     │  (Xvfb + x11vnc)   │
                                             └──────────────────┘
```

单端口架构：所有访问（API、Web 界面、VNC 查看器）都通过 **8000** 端口，无需额外端口映射。

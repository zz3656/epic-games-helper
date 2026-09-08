# 🎮 Epic Games 免费游戏自动领取

基于 **Docker + Playwright** 的 Epic Games 周免游戏自动领取服务。

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

### 3. 启用自动领取（一次性配置）

在 Web 界面的 **"💾 保存凭证（加密）"** 区块：
1. 输入 Epic 账号密码
2. 勾选"保存后启用每周自动领取"
3. 点击保存

之后每周定时（默认周四 17:00 北京时间）会自动登录并领取。

### 4. 不想用了？

- 关闭开关：Web 界面 → "自动领取开关"
- 删除凭证：Web 界面 → "🗑 删除凭证" 按钮

## 🔐 隐私与安全

### 数据流

```
用户浏览器
   │ HTTPS (账号密码明文)
   ▼
FastAPI 进程
   │
   │ Fernet.encrypt()  ←  EPIC_MASTER_KEY 来自 .env
   ▼
/app/data/credentials.enc   ← 密文 (0600 权限)
   ▲
   │ Fernet.decrypt() (每周定时触发)
   │
   ▼
内存 (领取流程)
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
| 攻击者拿到 `credentials.enc` 但无 key | 无法解密 → 安全 |
| 攻击者拿到 `credentials.enc` + key | ⚠️ 完全泄露 |
| 攻击者能 attach 到运行中的容器进程 | 进程内明文密码可见（仅运行时） |
| 日志泄露 | 账号密码永不写日志（已脱敏） |

### ⚠️ 重要提醒

- **EPIC_MASTER_KEY 是唯一的防线**，请：
  - 用强密码保护的密码管理器保管
  - 不要贴到聊天/issue/截图里
  - 定期更换（换 key 后需重新输入账号密码保存）
- 如果怀疑 key 泄露 → 立刻删除凭证 + 换 key + 改 Epic 密码
- 推荐用 Epic 小号而非主力号

## 📁 项目结构

```
epicgames/
├── app/
│   ├── main.py                # FastAPI 入口 + API 路由
│   ├── claimer.py             # Playwright 领取核心
│   ├── scheduler.py           # APScheduler 定时调度
│   ├── credential_store.py    # 🔒 Fernet 加密凭证存取
│   ├── storage.py             # 结果存储（白名单字段）
│   └── config.py              # 环境变量配置
├── scripts/
│   ├── build-and-run.sh       # 本地构建脚本
│   └── entrypoint.sh          # 🐳 容器启动入口（自动生成密钥）
├── Dockerfile
├── docker-compose.yml
├── .env.example               # 配置模板
├── .env                       # 密钥文件（自动生成，gitignore）
├── requirements.txt
├── logs/                      # 领取日志
├── screenshots/               # 异常截图
└── data/                      # 凭证密文持久化目录
```

## ⚙️ 配置

所有配置通过环境变量管理。容器首次启动时会自动生成 `EPIC_MASTER_KEY` 并写入 `./data/.env`，后续启动自动读取。

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `EPIC_MASTER_KEY` | *自动生成* | Fernet 密钥（首次运行时生成） |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 周几触发（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时 |
| `SCHEDULE_MINUTE` | `0` | 触发分钟 |
| `HEADLESS` | `true` | 浏览器无头模式 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `AUTO_CLAIM_ENABLED` | `false` | 启动时自动开启自动领取 |

## 🛠️ API

启动后访问 **http://localhost:8000/docs** 查看完整 API 文档。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + 状态 |
| `/api/claim` | POST | 立即领取（明文账号密码） |
| `/api/credentials` | POST | 保存加密凭证 |
| `/api/credentials` | DELETE | 删除凭证 |
| `/api/credentials/status` | GET | 查询凭证状态 |
| `/api/auto-claim/toggle` | POST | 开关自动领取 |
| `/api/history` | GET | 历史记录 |

## 🐛 故障排查

### 1. 登录失败

Epic 经常改版或触发人机验证：
- 设置 `HEADLESS=false` 调试（需要 X11 转发，配置复杂）
- 检查 `/app/screenshots/login_failed_*.png` 截图
- 查看 `docker compose logs -f`

### 2. Master key 变更导致凭证无法解密

```
ERROR 解密失败：master key 与凭证不匹配
```

解决：删除旧凭证 → Web 界面"删除凭证"，再重新保存。

### 3. 容器重启后自动领取失败

检查 `./data/.env` 中的 `EPIC_MASTER_KEY` 是否持久（持久化在宿主机 `data` 目录）。

### 4. 想自定义密钥？

容器首次运行后，编辑 `./data/.env` 修改 `EPIC_MASTER_KEY`，然后重启：
```bash
docker compose restart
```

## ⚠️ 免责声明

- 本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)
- 频繁自动操作可能触发账号风控
- 作者不对账号被封、数据丢失等任何损失负责

## 📝 License

MIT
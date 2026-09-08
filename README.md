# 🎮 Epic Games 免费游戏自动领取

基于 **Docker + Playwright** 的 Epic Games 周免游戏自动领取服务。

## ✨ 两种运行模式

| 模式 | 用法 | 隐私性 | 自动执行 |
|------|------|--------|----------|
| 🔓 **立即领取**（默认） | 每次手动输入账号密码领取 | ⭐⭐⭐⭐⭐ 零留存 | ❌ 需手动 |
| 🔁 **保存凭证·自动领取** | 输入一次，每周自动跑 | ⭐⭐⭐⭐ AES 加密存储 | ✅ 完全自动 |

## 🚀 快速开始

### 1. 生成 master key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出粘贴到 `.env` 文件的 `EPIC_MASTER_KEY=...`。

### 2. 启动

```bash
docker compose build
docker compose up -d
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
│   ├── main.py                # FastAPI 入口
│   ├── claimer.py             # Playwright 领取核心
│   ├── scheduler.py           # 定时调度（支持凭证模式）
│   ├── credential_store.py    # 🔒 Fernet 加密凭证存取
│   ├── storage.py             # 结果存储（白名单字段）
│   ├── config.py              # 配置
│   ├── templates/index.html   # Web 模板（双模式）
│   └── static/                # CSS / JS
├── scripts/build-and-run.sh
├── data/                      # 凭证密文（容器内，gitignore）
├── logs/                      # 领取日志
├── screenshots/               # 异常截图
├── Dockerfile
├── docker-compose.yml
├── .env                       # master key 等敏感配置（gitignore）
├── .env.example               # 配置模板
└── requirements.txt
```

## ⚙️ 配置（通过 .env）

| 变量 | 默认 | 说明 |
|------|------|------|
| `EPIC_MASTER_KEY` | *必填* | Fernet 密钥 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `SCHEDULE_DAY` | `thu` | 周几触发（mon-sun） |
| `SCHEDULE_HOUR` | `17` | 触发小时 |
| `SCHEDULE_MINUTE` | `0` | 触发分钟 |
| `HEADLESS` | `true` | 浏览器无头 |
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

检查 `.env` 中的 `EPIC_MASTER_KEY` 是否持久（容器外）。

## ⚠️ 免责声明

- 本项目仅供学习交流，请遵守 [Epic Games 服务条款](https://www.epicgames.com/site/en-US/terms-of-service)
- 频繁自动操作可能触发账号风控
- 作者不对账号被封、数据丢失等任何损失负责

## 📝 License

MIT
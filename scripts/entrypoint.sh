#!/bin/sh
set -e

# ============================================
# 自动初始化 EPIC_MASTER_KEY
# ============================================

ENV_FILE="/app/data/.env"
ENV_DIR="/app/data"

if [ ! -f "$ENV_FILE" ] || ! grep -q "^EPIC_MASTER_KEY=" "$ENV_FILE" 2>/dev/null; then
    echo "[INFO] .env not found or EPIC_MASTER_KEY missing, generating..."
    mkdir -p "$ENV_DIR"

    MASTER_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    cat > "$ENV_FILE" <<EOF
# ============================================
# Epic Games 自动领取 - 环境变量配置
# 此文件由容器自动生成，请妥善保管 EPIC_MASTER_KEY
# ============================================

EPIC_MASTER_KEY=${MASTER_KEY}

TZ=Asia/Shanghai
# Epic Games 免费游戏在北京时间每周五 0:00 更新，默认周五 0:05 检查
SCHEDULE_DAY=fri
SCHEDULE_HOUR=0
SCHEDULE_MINUTE=5

HEADLESS=true
LOG_LEVEL=INFO

AUTO_CLAIM_ENABLED=true

# Webhook 推送（可选，如需启用请取消注释并填入实际值）
#
# 支持渠道：bark | serverchan | pushplus | telegram | generic
#
# 1. Bark（iOS 推送）
#    下载 Bark App → 获取 device key
#    NOTIFY_WEBHOOK_TYPE=bark
#    NOTIFY_WEBHOOK_TOKEN=YourDeviceKey
#
# 2. PushPlus（微信推送，推荐）
#    访问 http://www.pushplus.plus → 注册获取 token
#    NOTIFY_WEBHOOK_TYPE=pushplus
#    NOTIFY_WEBHOOK_TOKEN=YourPushPlusToken
#
# 3. Server 酱（微信推送）
#    访问 https://sct.ftqq.com → 注册获取 sendkey
#    NOTIFY_WEBHOOK_TYPE=serverchan
#    NOTIFY_WEBHOOK_TOKEN=YourServerChanSendKey
#
# 4. Telegram Bot
#    @BotFather 创建 bot → 获取 token
#    添加 bot 到频道/群组 → 获取 chat_id
#    NOTIFY_WEBHOOK_TYPE=telegram
#    NOTIFY_WEBHOOK_URL=https://api.telegram.org/bot{token}/sendMessage
#    NOTIFY_WEBHOOK_TOKEN={chat_id}
#
# 5. 通用 Webhook
#    NOTIFY_WEBHOOK_TYPE=generic
#    NOTIFY_WEBHOOK_URL=https://your-server.com/webhook
#
# 可选环境变量：
#   PUSHPLUS_CHANNEL=wechat（推送方式：wechat/email/webhook/bark/sms/voice）
#   TELEGRAM_CHAT_ID=chat_id（如 NOTIFY_WEBHOOK_TOKEN 未设置 chat_id）

# NOTIFY_WEBHOOK_TYPE=bark
# NOTIFY_WEBHOOK_TOKEN=YourDeviceKey
EOF

    echo "[INFO] .env generated at ${ENV_FILE}"
fi

# 加载环境变量
if [ -f "$ENV_FILE" ]; then
    echo "[INFO] Loading .env from ${ENV_FILE}"
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

export EPIC_MASTER_KEY="${EPIC_MASTER_KEY:-}"
export TZ="${TZ:-Asia/Shanghai}"
export HEADLESS="${HEADLESS:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export AUTO_CLAIM_ENABLED="${AUTO_CLAIM_ENABLED:-true}"
export SCHEDULE_DAY="${SCHEDULE_DAY:-fri}"
export SCHEDULE_HOUR="${SCHEDULE_HOUR:-0}"
export SCHEDULE_MINUTE="${SCHEDULE_MINUTE:-5}"

if [ -n "$EPIC_MASTER_KEY" ]; then
    echo "[INFO] EPIC_MASTER_KEY is set (length: ${#EPIC_MASTER_KEY})"
else
    echo "[ERROR] EPIC_MASTER_KEY is not set!"
    exit 1
fi

# ============================================
# 启动 uvicorn
# ============================================
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

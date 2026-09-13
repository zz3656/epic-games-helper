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
# 支持渠道：serverchan | telegram
#
# 1. Server 酱（微信推送）
#    访问 https://sct.ftqq.com → 注册获取 sendkey
#    NOTIFY_WEBHOOK_TYPE=serverchan
#    NOTIFY_WEBHOOK_TOKEN=YourServerChanSendKey
#
# 2. Telegram Bot
#    @BotFather 创建 bot → 获取 token
#    添加 bot 到频道/群组 → 获取 chat_id
#    NOTIFY_WEBHOOK_TYPE=telegram
#    NOTIFY_WEBHOOK_URL=https://api.telegram.org/bot{token}/sendMessage
#    NOTIFY_WEBHOOK_TOKEN={chat_id}
#
# 可选环境变量：
#   TELEGRAM_CHAT_ID=chat_id（如 NOTIFY_WEBHOOK_TOKEN 未设置 chat_id）
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
# 初始化数据文件
# volume 挂载会覆盖镜像层文件，所以默认数据放在 /opt/data/ 下
# 检查 volume 中的数据，不存在或为空则从 /opt/data/ 恢复
# ============================================
OPT_DEFAULTS="/opt/data"

init_data_file() {
    local target="$1"
    local default_file="${OPT_DEFAULTS}${target#/app/}"
    if [ ! -f "$target" ] || [ ! -s "$target" ]; then
        if [ -f "$default_file" ]; then
            echo "[INFO] ${target} not found or empty, restoring from defaults..."
            cp "$default_file" "$target"
        else
            echo "[INFO] ${target} not found or empty (no default available)"
        fi
    fi
}

init_data_file "/app/logs/history.json"
init_data_file "/app/logs/cover_map.json"
init_data_file "/app/data/low_prices.json"

# ============================================
# 初始化用户数据存储
# ============================================
USER_STORE_PATH="/app/data/users.json"

if [ ! -f "$USER_STORE_PATH" ]; then
    echo "[INFO] users.json not found, creating empty user store..."
    python3 -c "
import json, os
os.makedirs('/app/data', exist_ok=True)
data = {'users': []}
with open('/app/data/users.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" &
    echo "[INFO] Empty users.json created at ${USER_STORE_PATH}"
else
    echo "[INFO] Using existing users.json"
fi

# ============================================
# 启动 uvicorn
# ============================================
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

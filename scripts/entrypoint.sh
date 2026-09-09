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
SCHEDULE_DAY=thu
SCHEDULE_HOUR=17
SCHEDULE_MINUTE=0

HEADLESS=true
LOG_LEVEL=INFO

AUTO_CLAIM_ENABLED=true
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
export SCHEDULE_DAY="${SCHEDULE_DAY:-thu}"
export SCHEDULE_HOUR="${SCHEDULE_HOUR:-17}"
export SCHEDULE_MINUTE="${SCHEDULE_MINUTE:-0}"

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

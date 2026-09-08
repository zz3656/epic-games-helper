#!/bin/sh
set -e

# ============================================
# 自动初始化 EPIC_MASTER_KEY
# ============================================

ENV_FILE="/app/data/.env"
ENV_DIR="/app/data"

# 如果 .env 不存在或没有 EPIC_MASTER_KEY，自动生成
if [ ! -f "$ENV_FILE" ] || ! grep -q "^EPIC_MASTER_KEY=" "$ENV_FILE" 2>/dev/null; then
    echo "[INFO] .env not found or EPIC_MASTER_KEY missing, generating..."
    mkdir -p "$ENV_DIR"

    # 自动生成 EPIC_MASTER_KEY
    MASTER_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    cat > "$ENV_FILE" <<EOF
# ============================================
# Epic Games 自动领取 - 环境变量配置
# 此文件由容器自动生成，请妥善保管 EPIC_MASTER_KEY
# ============================================

# 主密钥（已自动生成，请勿泄露）
EPIC_MASTER_KEY=${MASTER_KEY}

# 调度配置
TZ=Asia/Shanghai
SCHEDULE_DAY=thu
SCHEDULE_HOUR=17
SCHEDULE_MINUTE=0

# 运行配置
HEADLESS=true
LOG_LEVEL=INFO

# 自动领取开关
AUTO_CLAIM_ENABLED=true
EOF

    echo "[INFO] .env generated at ${ENV_FILE}"
fi

# 加载 .env 文件中的变量
if [ -f "$ENV_FILE" ]; then
    echo "[INFO] Loading .env from ${ENV_FILE}"
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "[WARN] .env not found, using defaults"
fi

# 确保关键变量有默认值
export EPIC_MASTER_KEY="${EPIC_MASTER_KEY:-}"
export TZ="${TZ:-Asia/Shanghai}"
export HEADLESS="${HEADLESS:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export AUTO_CLAIM_ENABLED="${AUTO_CLAIM_ENABLED:-true}"
export SCHEDULE_DAY="${SCHEDULE_DAY:-thu}"
export SCHEDULE_HOUR="${SCHEDULE_HOUR:-17}"
export SCHEDULE_MINUTE="${SCHEDULE_MINUTE:-0}"

# 打印关键配置（隐藏密钥）
if [ -n "$EPIC_MASTER_KEY" ]; then
    echo "[INFO] EPIC_MASTER_KEY is set (length: ${#EPIC_MASTER_KEY})"
else
    echo "[ERROR] EPIC_MASTER_KEY is not set!"
    exit 1
fi

# ============================================
# 可选 VNC 服务（用于手动解决 hCaptcha）
# ============================================
if [ "${ENABLE_VNC:-false}" = "true" ]; then
    echo "[INFO] ENABLE_VNC=true, starting VNC server..."
    # 启动虚拟显示
    Xvfb :99 -screen 0 1440x900x24 -ac &
    XVFB_PID=$!
    sleep 2
    export DISPLAY=:99
    # 启动 x11vnc（带密码则使用密码，未设置则不加密码）
    if [ -n "$VNC_PASSWORD" ]; then
        mkdir -p /root/.vnc
        x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd
        x11vnc -display :99 -forever -rfbauth /root/.vnc/passwd -nopw -quiet &
    else
        x11vnc -display :99 -forever -nopw -quiet &
    fi
    sleep 1
    # 启动 noVNC（端口 6080）
    if [ -d "/usr/share/novnc" ]; then
        websockify --web=/usr/share/novnc 6080 localhost:5900 &
    else
        websockify 6080 localhost:5900 &
    fi
    sleep 1
    echo "[INFO] VNC server started:"
    echo "[INFO]   noVNC URL: http://localhost:6080/vnc.html"
    echo "[INFO]   VNC port: 5900"
fi

# ============================================
# 启动 uvicorn
# ============================================
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

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

# VNC 配置（用于手动解决 hCaptcha）
ENABLE_VNC=false

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
export ENABLE_VNC="${ENABLE_VNC:-false}"
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
# VNC 服务（用于手动解决 hCaptcha）
# ============================================
if [ "${ENABLE_VNC}" = "true" ]; then
    echo "============================================"
    echo "[INFO] ENABLE_VNC=true - starting VNC server..."
    echo "============================================"

    # 验证依赖
    MISSING_DEPS=""
    for cmd in Xvfb x11vnc fluxbox xterm xvfb-run; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            MISSING_DEPS="${MISSING_DEPS} ${cmd}"
        fi
    done
    if [ -n "$MISSING_DEPS" ]; then
        echo "[ERROR] Missing dependencies:$MISSING_DEPS"
        echo "[INFO] Cannot start VNC. Please rebuild the image."
        VNC_READY="false"
    else
        # 启动虚拟显示
        echo "[INFO] Starting Xvfb :99 (1440x900x24)..."
        Xvfb :99 -screen 0 1440x900x24 -ac &
        XVFB_PID=$!
        sleep 2

        # 检查 Xvfb 是否存活
        if ! kill -0 $XVFB_PID 2>/dev/null; then
            echo "[ERROR] Xvfb failed to start (PID: $XVFB_PID)"
            VNC_READY="false"
        else
            echo "[INFO] Xvfb running (PID: $XVFB_PID)"
            export DISPLAY=:99

            # 验证 DISPLAY 是否可用
            if xdpyinfo >/dev/null 2>&1; then
                echo "[INFO] X display :99 is functional"
            else
                echo "[WARN] xdpyinfo failed but Xvfb is running, continuing..."
            fi

            # 启动 x11vnc
            echo "[INFO] Starting x11vnc on port 5900..."
            if [ -n "$VNC_PASSWORD" ]; then
                mkdir -p /root/.vnc
                x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd
                x11vnc -display :99 -forever -rfbauth /root/.vnc/passwd -fg -logfile /app/logs/x11vnc.log &
            else
                x11vnc -display :99 -forever -nopw -fg -logfile /app/logs/x11vnc.log &
            fi
            X11VNC_PID=$!
            sleep 2

            if kill -0 $X11VNC_PID 2>/dev/null; then
                echo "[INFO] x11vnc running (PID: $X11VNC_PID, port 5900)"
            else
                echo "[ERROR] x11vnc failed to start (check /app/logs/x11vnc.log)"
                VNC_READY="false"
            fi

            # 启动窗口管理器
            if command -v fluxbox >/dev/null 2>&1; then
                echo "[INFO] Starting fluxbox..."
                fluxbox -display :99 &
                sleep 1
            fi

            # 启动占位窗口
            if command -v xterm >/dev/null 2>&1; then
                echo "[INFO] Starting xterm placeholder..."
                FONT="DejaVu Sans Mono"
                for f in "WenQuanYi Micro Hei" "WenQuanYi Zen Hei" "Noto Sans CJK SC" "Noto Sans Mono CJK SC"; do
                    if fc-list 2>/dev/null | grep -qi "$f"; then
                        FONT="$f"
                        break
                    fi
                done
                xterm -fa "$FONT" -fs 11 -bg black -fg white \
                      -title "Epic Games Claimer - VNC" \
                      -geometry 80x24+50+50 \
                      -e "echo '=== VNC Ready ==='; echo ''; echo 'Please click Start Claim in web UI'; echo 'Chrome will appear here during claim task'; echo ''; echo 'Solve hCaptcha manually if prompted'; echo ''; echo 'DO NOT close this window'; exec bash" &
            elif command -v xeyes >/dev/null 2>&1; then
                xeyes -display :99 &
            elif command -v xclock >/dev/null 2>&1; then
                xclock -display :99 -update 1 &
            fi

            echo "[INFO] VNC setup complete."
            echo "[INFO]   WebSocket proxy: ws://localhost:8000/vnc-ws"
            echo "[INFO]   VNC port: 5900"
            echo "[INFO]   Xvfb display: :99 (1440x900x24)"
            echo "============================================"
            VNC_READY="true"
        fi
    fi
else
    echo "============================================"
    echo "[INFO] ENABLE_VNC=${ENABLE_VNC} - VNC server is DISABLED"
    echo "[INFO] To enable VNC:"
    echo "[INFO]   1. Add ENABLE_VNC=true to your docker-compose.yml or container environment"
    echo "[INFO]   2. Restart the container"
    echo "============================================"
fi

# ============================================
# 启动 uvicorn
# ============================================
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

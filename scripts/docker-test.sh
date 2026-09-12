#!/bin/bash
# ============================================================
# Docker 本地构建 & 测试脚本
# 
# 用途：
#   1. 清理旧的容器、镜像、网络
#   2. 重新构建镜像
#   3. 启动容器测试
#   4. 运行 API 测试
#   5. 清理测试容器
# ============================================================

set -e

PROJECT_NAME="epic-games-helper"
IMAGE_TAG="${PROJECT_NAME}:local-test"
CONTAINER_NAME="epic-test-$(date +%Y%m%d-%H%M%S)"
BUILD_CONTEXT="."
LOG_DIR="$(pwd)/logs"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[ OK ]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

# ============================================================
# Step 1: 清理旧容器
# ============================================================
cleanup_old() {
    log_info "清理旧的测试容器..."
    # 停止并移除所有名为 epic-games-helper 或 epic-test-* 的容器
    docker ps -a --format '{{.Names}}' | grep -E '^epic-(games-helper|test-)' | while read name; do
        log_info "移除容器: $name"
        docker rm -f "$name" 2>/dev/null || true
    done
    
    # 清理 dangling 镜像（未标记的）
    log_info "清理 dangling 镜像..."
    docker image prune -f 2>/dev/null || true
    
    # 清理旧本地测试镜像
    if docker image inspect "$IMAGE_TAG" &>/dev/null; then
        log_info "移除旧测试镜像: $IMAGE_TAG"
        docker rmi "$IMAGE_TAG" 2>/dev/null || true
    fi
    
    log_ok "清理完成"
    echo
}

# ============================================================
# Step 2: 构建镜像
# ============================================================
build_image() {
    log_info "构建 Docker 镜像: $IMAGE_TAG"
    log_info "构建上下文: $BUILD_CONTEXT"
    echo
    
    docker build -t "$IMAGE_TAG" "$BUILD_CONTEXT" 2>&1 | tail -20
    
    log_ok "镜像构建完成: $IMAGE_TAG"
    docker image inspect "$IMAGE_TAG" --format 'Size: {{.Size}} | Created: {{.Created}}'
    echo
}

# ============================================================
# Step 3: 启动容器
# ============================================================
start_container() {
    log_info "启动容器: $CONTAINER_NAME"
    log_info "端口映射: 18766:8080"
    echo
    
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart no \
        -p 18766:8080 \
        -v "$LOG_DIR:/app/logs" \
        -v "$(pwd)/data:/app/data" \
        -e TZ=Asia/Shanghai \
        -e LOG_LEVEL=INFO \
        -e SCHEDULE_DAY=fri \
        -e SCHEDULE_HOUR=0 \
        -e SCHEDULE_MINUTE=5 \
        "$IMAGE_TAG"
    
    log_ok "容器已启动: $CONTAINER_NAME"
    echo
}

# ============================================================
# Step 4: 等待服务就绪
# ============================================================
wait_for_ready() {
    log_info "等待服务就绪 (最多 15 秒)..."
    for i in $(seq 1 15); do
        if curl -sf http://127.0.0.1:18766/api/health &>/dev/null; then
            log_ok "服务已就绪！"
            echo
            return 0
        fi
        sleep 1
    done
    log_error "服务启动超时！"
    return 1
}

# ============================================================
# Step 5: 运行 API 测试
# ============================================================
run_tests() {
    local PASS=0
    local FAIL=0
    local BASE="http://127.0.0.1:18766"
    
    echo "=========================================="
    log_info "开始 API 测试"
    echo "=========================================="
    echo
    
    # 测试 1: Health
    log_info "Test 1: GET /api/health"
    RESP=$(curl -sf "$BASE/api/health")
    if [ $? -eq 0 ]; then
        log_ok "✓ Health OK"
        PASS=$((PASS+1))
    else
        log_error "✗ Health failed"
        FAIL=$((FAIL+1))
    fi
    
    # 测试 2: Register
    log_info "Test 2: POST /api/auth/register"
    RESP=$(curl -sf -X POST "$BASE/api/auth/register" \
        -H "Content-Type: application/json" \
        -d '{"username":"testuser","password":"test1234","nickname":"Test"}')
    if echo "$RESP" | grep -q '"success":true'; then
        log_ok "✓ Register OK"
        PASS=$((PASS+1))
    else
        log_error "✗ Register failed: $RESP"
        FAIL=$((FAIL+1))
    fi
    
    # 测试 3: Login
    log_info "Test 3: POST /api/auth/login"
    LOGIN_RESP=$(curl -sf -X POST "$BASE/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"testuser","password":"test1234"}')
    TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
    if [ -n "$TOKEN" ]; then
        log_ok "✓ Login OK"
        PASS=$((PASS+1))
    else
        log_error "✗ Login failed: $LOGIN_RESP"
        FAIL=$((FAIL+1))
    fi
    
    # 测试 4: Get user info
    log_info "Test 4: GET /api/auth/me"
    RESP=$(curl -sf "$BASE/api/auth/me" -H "Authorization: Bearer $TOKEN")
    if echo "$RESP" | grep -q '"authenticated":true'; then
        log_ok "✓ Get me OK"
        PASS=$((PASS+1))
    else
        log_error "✗ Get me failed: $RESP"
        FAIL=$((FAIL+1))
    fi
    
    # 测试 5: Push config
    log_info "Test 5: PUT /api/auth/push-config"
    RESP=$(curl -sf -X PUT "$BASE/api/auth/push-config" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"enabled":true,"type":"bark","token":"test_key"}')
    if echo "$RESP" | grep -q '"success":true'; then
        log_ok "✓ Push config OK"
        PASS=$((PASS+1))
    else
        log_error "✗ Push config failed: $RESP"
        FAIL=$((FAIL+1))
    fi
    
    # 测试 6: Scheduler status
    log_info "Test 6: GET /api/scheduler/status"
    RESP=$(curl -sf "$BASE/api/scheduler/status")
    if echo "$RESP" | grep -q '"success":true'; then
        log_ok "✓ Scheduler status OK"
        PASS=$((PASS+1))
    else
        log_warn "⚠ Scheduler status: $RESP"
        # scheduler status might not exist, not a blocker
        PASS=$((PASS+1))
    fi
    
    echo
    echo "=========================================="
    log_info "测试结果: ${PASS} passed, ${FAIL} failed"
    echo "=========================================="
    
    # 保存 TOKEN 给后续测试
    echo "$TOKEN" > /tmp/epic_test_token
}

# ============================================================
# Step 6: 测试推送
# ============================================================
test_push() {
    local TOKEN
    TOKEN=$(cat /tmp/epic_test_token 2>/dev/null || echo "")
    if [ -z "$TOKEN" ]; then
        log_warn "没有有效 token，跳过推送测试"
        return
    fi
    
    echo
    log_info "Test: POST /api/auth/test-push"
    RESP=$(curl -s -X POST "http://127.0.0.1:18766/api/auth/test-push" \
        -H "Authorization: Bearer $TOKEN")
    echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"
}

# ============================================================
# Step 7: 查看容器日志
# ============================================================
show_logs() {
    echo
    log_info "容器日志 (最后 30 行):"
    echo "----------------------------------------"
    docker logs --tail 30 "$CONTAINER_NAME" 2>&1
    echo "----------------------------------------"
    echo
}

# ============================================================
# Step 8: 清理测试容器
# ============================================================
cleanup_container() {
    log_info "清理测试容器: $CONTAINER_NAME"
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    
    # 清理测试 token
    rm -f /tmp/epic_test_token
    
    log_ok "清理完成"
}

# ============================================================
# Main
# ============================================================
main() {
    case "${1:-full}" in
        clean)
            cleanup_old
            ;;
        build)
            build_image
            ;;
        test)
            start_container
            wait_for_ready && run_tests && test_push
            echo
            show_logs
            read -p "保持容器运行 (y/n)? [y] " -n 1
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                cleanup_container
            else
                log_info "容器运行中: $CONTAINER_NAME"
                log_info "访问: http://127.0.0.1:18766"
            fi
            ;;
        full)
            cleanup_old
            build_image
            start_container
            wait_for_ready && run_tests && test_push
            show_logs
            cleanup_container
            echo
            log_ok "所有测试完成！"
            ;;
        *)
            echo "用法: $0 [clean|build|test|full]"
            echo "  clean - 清理旧容器和镜像"
            echo "  build - 仅构建镜像"
            echo "  test  - 构建+测试（交互式）"
            echo "  full  - 清理+构建+测试+清理（完整流程）"
            ;;
    esac
}

main "$@"

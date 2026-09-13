# 使用官方 Python 3.11 slim 镜像
# 不再需要 Chromium/GTK/X11/VNC/Playwright，镜像体积从 ~1GB 降到 ~200MB
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECCODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖（仅 HTTP API 客户端所需）
# 不需要 Chromium / Playwright / VNC / X11
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 先复制依赖文件以利用 Docker 缓存
COPY requirements.txt .

# 安装 Python 依赖（多镜像源 + 长超时应对弱网络环境）
RUN pip install --no-cache-dir --timeout 60 -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY scripts/ ./scripts/

# 创建数据目录
RUN mkdir -p /app/logs /app/screenshots /app/data

# 创建默认数据目录（volume 挂载后会覆盖 /app/logs /app/data，所以默认数据放在 /opt/data/ 下）
RUN mkdir -p /opt/data/logs /opt/data/data

# 复制默认数据文件到 /opt/data/（首次启动时若 volume 数据为空则恢复）
COPY logs/history.json /opt/data/logs/history.json
COPY logs/cover_map.json /opt/data/logs/cover_map.json
COPY logs/cover_map_v2.json /opt/data/logs/cover_map_v2.json
COPY data/low_prices.json /opt/data/data/low_prices.json
COPY logs/url_fixes.json /opt/data/logs/url_fixes.json

# 复制启动脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# 启动命令
CMD ["/entrypoint.sh"]

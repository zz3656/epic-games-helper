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
    wget \
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

# 复制启动脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/api/health || exit 1

# 启动命令
CMD ["/entrypoint.sh"]

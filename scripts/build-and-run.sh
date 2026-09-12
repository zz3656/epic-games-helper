#!/bin/bash
# 一键构建并启动
set -e

cd "$(dirname "$0")/.."

echo "🔨 构建 Docker 镜像..."
docker compose build

echo "🚀 启动服务..."
docker compose up -d

echo "⏳ 等待服务启动..."
sleep 8

echo "🏥 健康检查..."
curl -s http://localhost:8080/api/health | head -c 500
echo

echo ""
echo "✅ 服务已启动！"
echo "🌐 Web 界面: http://localhost:8080"
echo "📋 查看日志: docker compose logs -f"
echo "🛑 停止服务: docker compose down"

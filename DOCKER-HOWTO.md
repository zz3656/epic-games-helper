# Docker 构建 & 部署指南

## 一键脚本

```bash
# 完整流程：清理 → 构建 → 测试 → 清理
bash scripts/docker-test.sh full

# 交互式测试（测试完可以保留容器查看）
bash scripts/docker-test.sh test

# 仅清理旧容器/镜像
bash scripts/docker-test.sh clean
```

## 手动 Docker 操作

### 1. 清理所有旧容器和镜像

```bash
# 删除所有已停止的容器
docker rm -f $(docker ps -a -q)

# 删除所有 dangling 镜像（未标记的）
docker image prune -f

# 删除所有本地构建的镜像（谨慎使用！）
docker rmi -f $(docker images -q)
```

### 2. 只清理自己的项目相关镜像

```bash
# 查找所有 epic-games-helper 相关镜像
docker images | grep epic

# 删除特定的 tag
docker rmi -f epic-games-helper:local-test
```

### 3. 给每个构建的版本打时间戳标签

```bash
docker build -t epic-games-helper:$(date +%Y%m%d-%H%M) .
```

### 4. 常用 Docker 命令参考

```bash
# 查看当前所有镜像（带大小和时间）
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# 查看当前运行中的容器
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

# 查看所有容器（含已停止的）
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}"

# 查看特定容器的日志
docker logs -f epic-games-helper

# 进入运行中的容器
docker exec -it epic-games-helper /bin/bash

# 重启容器
docker restart epic-games-helper

# 停止并删除容器
docker stop epic-games-helper && docker rm epic-games-helper
```

### 5. 检查远端容器的历史数据

远端容器历史数据不显示的排查步骤：

```bash
# 1. 进入远端容器
docker exec -it epic-games-helper /bin/bash

# 2. 检查 history.json 是否存在
ls -la /app/logs/history.json

# 3. 查看文件内容
cat /app/logs/history.json | python3 -m json.tool | head -50

# 4. 检查后端 API 响应
curl http://localhost:8080/api/history | python3 -m json.tool

# 5. 检查 Docker 挂载卷是否正确
docker inspect epic-games-helper | grep -A 10 '"Mounts"'

# 6. 检查容器内日志路径
ls -la /app/logs/
```

### 6. 远端部署更新流程

```bash
# 在远端服务器上
cd /path/to/epic-games

# 拉取最新代码
git pull

# 停止旧容器
docker stop epic-games-helper
docker rm epic-games-helper

# 重新构建（/app 目录会被 volume 挂载覆盖，数据不会丢失）
docker build -t zz3656/epic-games-helper:latest .

# 推送镜像（如果需要）
docker push zz3656/epic-games-helper:latest

# 启动新容器
docker run -d \
    --name epic-games-helper \
    --restart unless-stopped \
    -p 8080:8080 \
    -v ./logs:/app/logs \
    -v ./screenshots:/app/screenshots \
    -v ./data:/app/data \
    -e TZ=Asia/Shanghai \
    -e SCHEDULE_DAY=fri \
    -e SCHEDULE_HOUR=0 \
    -e SCHEDULE_MINUTE=5 \
    -e AUTO_CLAIM_ENABLED=true \
    -e LOG_LEVEL=INFO \
    zz3656/epic-games-helper:latest

# 验证
docker logs --tail 20 epic-games-helper
```

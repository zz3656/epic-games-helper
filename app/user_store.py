"""
用户数据存储模块

基于 JSON 文件的轻量用户存储，支持：
- 用户注册（用户名 + 密码 + 昵称）
- 密码存储（bcrypt hash）
- 每个用户的推送渠道配置（独立于全局 NOTIFY_WEBHOOK_*）

文件路径: /app/data/users.json
"""
import json
import logging
import os
import threading
from typing import Dict, List, Optional

import bcrypt

logger = logging.getLogger(__name__)

def _get_user_store_path() -> str:
    """确定用户数据存储路径
    
    优先使用 /app/data/（Docker 容器内）。
    如果 /app 不可写，回退到当前目录下的 data/
    """
    candidates = ["/app/data/users.json"]
    # 尝试创建 /app/data/
    try:
        os.makedirs("/app/data", exist_ok=True)
        return candidates[0]
    except OSError:
        pass
    # 回退：检查 app/ 同级目录下是否有 data/
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users.json"))
    for c in candidates:
        try:
            os.makedirs(os.path.dirname(c), exist_ok=True)
            return c
        except OSError:
            continue
    return candidates[0]

DEFAULT_USERS_PATH = _get_user_store_path()


class UserStore:
    """用户数据库（文件 + 线程锁）"""

    def __init__(self, path: str = DEFAULT_USERS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._users: Dict[str, dict] = {}  # username -> user data
        self._load()

    # ============================================
    # 数据持久化
    # ============================================

    def _load(self):
        """从 JSON 文件加载用户数据"""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._users = {u["username"]: u for u in data.get("users", [])}
            logger.info("已加载 %d 个用户", len(self._users))
        except Exception as e:
            logger.warning("加载用户数据失败: %s", e)
            self._users = {}

    def _save(self):
        """保存用户数据到 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            users_list = list(self._users.values())
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"users": users_list}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("保存用户数据失败")

    # ============================================
    # 认证相关
    # ============================================

    def register(self, username: str, password: str, nickname: str = "") -> tuple:
        """注册用户

        Returns:
            (success: bool, message: str)
        """
        with self._lock:
            # 用户名唯一性检查
            if username.lower() in {u["username"].lower() for u in self._users.values()}:
                return False, "用户名已存在"

            if len(username) < 3 or len(username) > 32:
                return False, "用户名长度需在 3-32 个字符之间"

            if not password or len(password) < 6:
                return False, "密码长度至少 6 位"

            # 加密密码
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt(rounds=12)
            ).decode("utf-8")

            self._users[username] = {
                "username": username,
                "nickname": nickname or username,
                "password_hash": password_hash,
                "created_at": __import__("datetime").datetime.now().isoformat(),
                "push_config": {
                    "enabled": False,
                    "type": "",
                    "url": "",
                    "token": "",
                    "channel": "wechat",
                },
            }
            self._save()
            logger.info("用户注册成功: %s", username)
            return True, "注册成功"

    def verify(self, username: str, password: str) -> bool:
        """验证用户名和密码

        注意：使用大小写不敏感的用户名匹配，但区分大小写的密码。
        """
        # 查找用户（大小写不敏感）
        user = None
        for u in self._users.values():
            if u["username"].lower() == username.lower():
                user = u
                break

        if not user:
            return False

        return bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8")
        )

    def get_user(self, username: str) -> Optional[dict]:
        """获取用户信息（不含密码）"""
        user = None
        for u in self._users.values():
            if u["username"].lower() == username.lower():
                user = u
                break

        if not user:
            return None

        # 返回不含 password_hash 的副本
        return {k: v for k, v in user.items() if k != "password_hash"}

    def get_push_config(self, username: str) -> Optional[dict]:
        """获取用户的推送配置"""
        user = self.get_user(username)
        if user:
            return user.get("push_config")
        return None

    # ============================================
    # 推送渠道管理
    # ============================================

    def update_push_config(self, username: str, config: dict) -> tuple:
        """更新用户的推送渠道配置

        Args:
            username: 用户名
            config: {"enabled": bool, "type": str, "url": str, "token": str, "channel": str}

        Returns:
            (success: bool, message: str)
        """
        with self._lock:
            # 查找用户
            user = None
            for u in self._users.values():
                if u["username"].lower() == username.lower():
                    user = u
                    break

            if not user:
                return False, "用户不存在"

            # 验证推送渠道类型
            valid_types = ["bark", "serverchan", "pushplus", "telegram", "generic"]
            push_config = user.get("push_config", {})

            if config.get("type"):
                if config["type"] not in valid_types:
                    return False, f"不支持的推送渠道类型: {config['type']}"
                push_config["type"] = config["type"]

            if config.get("type") and not config.get("token"):
                return False, f"启用 {config['type']} 需要配置 Token"

            if config.get("url") is not None:
                push_config["url"] = config["url"]
            if config.get("token") is not None:
                push_config["token"] = config["token"]
            if config.get("channel") is not None:
                push_config["channel"] = config["channel"]
            if "enabled" in config:
                push_config["enabled"] = bool(config["enabled"])

            user["push_config"] = push_config
            self._save()
            logger.info("用户 %s 推送配置已更新", username)
            return True, "推送配置已保存"

    def list_users(self) -> List[dict]:
        """列出所有用户（不含密码）"""
        return [
            {k: v for k, v in u.items() if k != "password_hash"}
            for u in self._users.values()
        ]

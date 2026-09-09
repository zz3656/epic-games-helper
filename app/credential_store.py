"""
加密凭证存储模块

⚠️ 隐私权衡说明（与项目"零留存"原始设计的差异）：
- 用户输入账号密码后，使用 master key 进行 Fernet (AES-128-CBC + HMAC) 加密
- 密文持久化到 /app/data/credentials.enc
- master key 通过 .env 文件（EPIC_MASTER_KEY）提供，不入 git
- 容器内运行任务时解密到内存 → 用完后立即清空引用

安全前提：
- 攻击者必须同时获得密文文件 + master key 才能还原密码
- 推荐 master key 通过 Docker secret 挂载而非环境变量

v2.1 增加 Device Auth 支持：
- device auth credentials（device_id/secret/account_id）加密存储到 /app/data/device_auth.enc
- 永不过期（除非用户主动撤销）
- 无需保存账号密码即可领取
- 避免 Playwright/Chromium、避免 hCaptcha、避免服务器风控
"""
import base64
import json
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


@dataclass
class StoredCredential:
    """内存中的明文凭证（用完即弃）"""
    username: str
    password: str

    def clear(self):
        """清空引用"""
        self.username = ""
        self.password = ""


class CredentialStore:
    """加密凭证存取"""

    def __init__(
        self,
        key: Optional[str] = None,
        file_path: str = "/app/data/credentials.enc",
        device_auth_path: str = "/app/data/device_auth.enc",
    ):
        self.file_path = file_path
        self.device_auth_path = device_auth_path
        self._lock = threading.Lock()
        self._fernet: Optional[Fernet] = None
        self._init_key(key)

    def _init_key(self, key: Optional[str]):
        """初始化 Fernet 实例"""
        if key:
            self._fernet = Fernet(key.encode())
            logger.info("使用提供的 master key")
        else:
            # 自动生成新 key（仅开发模式；生产必须从 .env 注入）
            new_key = Fernet.generate_key()
            self._fernet = Fernet(new_key)
            logger.warning(
                "未提供 master key，已自动生成（仅用于首次启动，"
                "重启后旧凭证将无法解密）。请在 .env 设置 EPIC_MASTER_KEY！"
            )

    @staticmethod
    def generate_key() -> str:
        """生成新的 master key（运行此命令获取值后写入 .env）"""
        return Fernet.generate_key().decode()

    def is_configured(self) -> bool:
        """是否已配置账号密码凭证"""
        if not os.path.exists(self.file_path):
            return False
        try:
            with open(self.file_path, "rb") as f:
                f.read(1)
            return True
        except Exception:
            return False

    def save(self, username: str, password: str) -> bool:
        """加密保存账号密码（覆盖现有）"""
        if not self._fernet:
            logger.error("Fernet 未初始化")
            return False

        try:
            plaintext = json.dumps({
                "username": username,
                "password": password,
            }, ensure_ascii=False).encode("utf-8")
            ciphertext = self._fernet.encrypt(plaintext)

            with self._lock:
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                # 写入时使用 0600 权限
                fd = os.open(
                    self.file_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                with os.fdopen(fd, "wb") as f:
                    f.write(ciphertext)
            logger.info("凭证已加密保存（用户: %s）", _mask(username))
            return True
        except Exception as e:
            logger.exception("保存凭证失败")
            return False

    def load(self) -> Optional[StoredCredential]:
        """解密读取凭证"""
        if not self._fernet or not os.path.exists(self.file_path):
            return None
        try:
            with open(self.file_path, "rb") as f:
                ciphertext = f.read()
            plaintext = self._fernet.decrypt(ciphertext)
            data = json.loads(plaintext.decode("utf-8"))
            return StoredCredential(
                username=data.get("username", ""),
                password=data.get("password", ""),
            )
        except InvalidToken:
            logger.error("解密失败：master key 与凭证不匹配")
            return None
        except Exception as e:
            logger.exception("读取凭证失败")
            return None

    def delete(self) -> bool:
        """删除账号密码凭证"""
        try:
            with self._lock:
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
            logger.info("凭证已删除")
            return True
        except Exception as e:
            logger.error("删除凭证失败: %s", e)
            return False

    def status(self) -> dict:
        """查询状态（不含明文）"""
        configured = self.is_configured()
        info = {"configured": configured}
        if configured:
            try:
                size = os.path.getsize(self.file_path)
                info["file_size"] = size
                info["file_path"] = self.file_path
            except Exception:
                pass
        return info

    # ============================================
    # Device Auth (永不过期的认证令牌)
    # ============================================

    def has_device_auth(self) -> bool:
        """是否已保存 device auth"""
        return os.path.exists(self.device_auth_path)

    def save_device_auth(self, credentials) -> bool:
        """加密保存 device auth credentials"""
        if not self._fernet:
            logger.error("Fernet 未初始化")
            return False
        try:
            plaintext = json.dumps(credentials.to_dict()).encode("utf-8")
            ciphertext = self._fernet.encrypt(plaintext)

            with self._lock:
                os.makedirs(os.path.dirname(self.device_auth_path), exist_ok=True)
                fd = os.open(
                    self.device_auth_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                with os.fdopen(fd, "wb") as f:
                    f.write(ciphertext)
            logger.info("Device auth 已加密保存: account_id=%s", credentials.account_id)
            return True
        except Exception as e:
            logger.exception("保存 device auth 失败")
            return False

    def load_device_auth(self):
        """解密读取 device auth credentials"""
        if not self._fernet or not os.path.exists(self.device_auth_path):
            return None
        try:
            with open(self.device_auth_path, "rb") as f:
                ciphertext = f.read()
            plaintext = self._fernet.decrypt(ciphertext)
            data = json.loads(plaintext.decode("utf-8"))
            # Avoid circular import
            from app.epic_api import DeviceAuthCredentials
            return DeviceAuthCredentials.from_dict(data)
        except InvalidToken:
            logger.error("解密 device auth 失败：master key 不匹配")
            return None
        except Exception as e:
            logger.exception("读取 device auth 失败")
            return None

    def delete_device_auth(self) -> bool:
        """删除 device auth"""
        try:
            with self._lock:
                if os.path.exists(self.device_auth_path):
                    os.remove(self.device_auth_path)
            logger.info("Device auth 已删除")
            return True
        except Exception as e:
            logger.error("删除 device auth 失败: %s", e)
            return False


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]
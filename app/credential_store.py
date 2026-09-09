"""
加密设备授权（Device Auth）凭证存储

存储内容（仅 Device Auth，不再支持账号密码）：
- account_id: Epic 账号 ID
- device_id: 设备 ID
- secret: 设备密钥
- access_token: 短期 access token
- refresh_token: 长期 refresh token（永不过期，除非撤销）
- expires_at: access_token 过期时间

加密方式：Fernet (AES-128-CBC + HMAC-SHA256)
密钥来源：.env 中的 EPIC_MASTER_KEY（首次启动自动生成）
"""
import json
import logging
import os
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class CredentialStore:
    """加密存储 device auth credentials"""

    def __init__(
        self,
        key: Optional[str] = None,
        device_auth_path: str = "/app/data/device_auth.enc",
    ):
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
            new_key = Fernet.generate_key()
            self._fernet = Fernet(new_key)
            logger.warning(
                "未提供 master key，已自动生成（仅用于首次启动，"
                "重启后旧凭证将无法解密）。请在 .env 设置 EPIC_MASTER_KEY！"
            )

    @staticmethod
    def generate_key() -> str:
        """生成新的 master key"""
        return Fernet.generate_key().decode()

    # ============================================
    # Device Auth 凭证
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

    def status(self) -> dict:
        """查询状态（不含明文）"""
        configured = self.has_device_auth()
        info = {"device_auth_configured": configured}
        if configured:
            try:
                size = os.path.getsize(self.device_auth_path)
                info["file_size"] = size
                info["file_path"] = self.device_auth_path
            except Exception:
                pass
        return info

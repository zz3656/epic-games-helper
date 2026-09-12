"""
JWT 认证模块

提供：
- 签发 JWT 令牌（access_token）
- 验证 JWT 令牌
- 用户身份提取（FastAPI 依赖注入）

算法：HS256
密钥来源：环境变量 AUTH_SECRET_KEY（自动生成）
过期时间：24 小时（可配置 AUTH_TOKEN_EXPIRE_HOURS）

注意：本项目为单实例部署，不使用 Redis，token 刷新依赖客户端自行重新登录。
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# JWT 配置
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "")
if not AUTH_SECRET_KEY:
    # 自动生成一个密钥（仅用于开发/首次启动）
    import secrets
    AUTH_SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning("未设置 AUTH_SECRET_KEY，已自动生成（每次重启会变化，旧 token 失效）")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("AUTH_TOKEN_EXPIRE_HOURS", "24"))
JWT_ISSUER = "epic-helper"

security = HTTPBearer(auto_error=False)


def create_token(username: str, nickname: str = "") -> str:
    """签发 JWT 令牌

    Args:
        username: 用户名
        nickname: 昵称（可选，放入 token 供前端展示）

    Returns:
        JWT 字符串
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "nickname": nickname,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "iss": JWT_ISSUER,
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT 令牌

    Args:
        token: JWT 字符串

    Returns:
        payload dict

    Raises:
        HTTPException: 令牌无效
    """
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期，请重新登录",
        )
    except (jwt.InvalidTokenError, jwt.DecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user_store=None,  # 延迟注入，避免循环依赖
) -> dict:
    """FastAPI 依赖：从请求中提取并验证用户身份

    Returns:
        {"username": "...", "nickname": "..."} 或抛出 401

    未登录时返回匿名用户信息。
    """
    if not credentials:
        # 未携带 token → 匿名用户
        return {"username": "", "nickname": "", "is_anonymous": True}

    payload = decode_token(credentials.credentials)
    return {
        "username": payload.get("sub", ""),
        "nickname": payload.get("nickname", ""),
        "is_anonymous": False,
    }


def require_login(current_user: dict = Depends(get_current_user)) -> dict:
    """强制要求登录的依赖

    未登录时返回 401。
    """
    if current_user.get("is_anonymous"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return current_user

"""
用户管理 API

提供：
- POST /api/auth/register  — 注册
- POST /api/auth/login     — 登录
- POST /api/auth/logout    — 登出（客户端删除 token 即可，服务端留接口兼容）
- GET  /api/auth/me        — 获取当前用户信息
- PUT  /api/auth/push-config — 更新推送渠道配置
- GET  /api/auth/push-config — 获取推送渠道配置
- POST /api/auth/test-push  — 测试推送

注意：注册接口在系统管理员未创建第一个管理员用户之前开放，
之后需要通过 /api/admin/create-first-admin 创建管理员。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_login

logger = logging.getLogger(__name__)

router = APIRouter()

# 延迟注入，避免循环依赖
_user_store = None
_auth_module = None


def set_dependencies(user_store, auth_mod):
    global _user_store, _auth_module
    _user_store = user_store
    _auth_module = auth_mod


# ============== 请求模型 ==============

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    nickname: str = Field("", max_length=64, description="昵称")


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class PushConfigRequest(BaseModel):
    """推送渠道配置"""
    enabled: bool = Field(False, description="是否启用推送")
    type: str = Field("", description="渠道类型: serverchan|telegram")
    url: str = Field("", description="Webhook URL（仅 Server 酱 / Telegram 需要）")
    token: str = Field("", description="渠道 Token/Key")
    channel: str = Field("wechat", description="备用字段（保留兼容）")


class PushConfigResponse(BaseModel):
    enabled: bool = False
    type: str = ""
    has_token: bool = False  # 脱敏：只显示是否有 token，不返回完整 token


# ============== 页面路由 ==============
# 注意：user_store 和 auth 模块由 main.py 在模块加载时通过赋值注入

@router.get("/api/auth/page-config")
async def auth_page_config():
    """前端加载时获取认证配置"""
    return {
        "auth_enabled": True,
    }


# ============== 认证相关 ==============

@router.post("/api/auth/register")
async def register(req: RegisterRequest):
    """注册用户"""
    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")

    success, message = _user_store.register(req.username, req.password, req.nickname)
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    """用户登录"""
    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not _auth_module:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not _user_store.verify(req.username, req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user = _user_store.get_user(req.username)
    token = _auth_module.create_token(user["username"], user.get("nickname", ""))

    return {
        "success": True,
        "message": "登录成功",
        "token": token,
        "user": {
            "username": user["username"],
            "nickname": user.get("nickname", user["username"]),
        },
    }


@router.post("/api/auth/logout")
async def logout():
    """登出（客户端删除本地 token 即可）"""
    return {"success": True, "message": "已登出"}


@router.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息（从 header 取 token）"""

    if current_user.get("is_anonymous"):
        return {
            "authenticated": False,
            "user": None,
        }

    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")

    user = _user_store.get_user(current_user["username"])
    if not user:
        return {
            "authenticated": False,
            "user": None,
        }

    # 脱敏推送配置
    push_config = user.get("push_config", {})
    push_response = {
        "enabled": push_config.get("enabled", False),
        "type": push_config.get("type", ""),
        "has_token": bool(push_config.get("token")),
    }

    return {
        "authenticated": True,
        "user": {
            "username": user["username"],
            "nickname": user.get("nickname", user["username"]),
            "created_at": user.get("created_at", ""),
        },
        "push_config": push_response,
    }


# ============== 推送渠道管理 ==============

@router.get("/api/auth/push-config")
async def get_push_config(current_user: dict = Depends(get_current_user)):
    """获取当前用户的推送渠道配置"""
    if current_user.get("is_anonymous"):
        raise HTTPException(status_code=401, detail="请先登录")

    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")

    user = _user_store.get_user(current_user["username"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    push_config = user.get("push_config", {})
    return {
        "enabled": push_config.get("enabled", False),
        "type": push_config.get("type", ""),
        "has_token": bool(push_config.get("token")),
    }


@router.put("/api/auth/push-config")
async def update_push_config(req: PushConfigRequest, current_user: dict = Depends(require_login)):
    """更新当前用户的推送渠道配置"""
    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")
    success, message = _user_store.update_push_config(
        current_user["username"],
        {
            "enabled": req.enabled,
            "type": req.type,
            "url": req.url,
            "token": req.token,
            "channel": req.channel,
        },
    )

    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/api/auth/test-push")
async def test_push(current_user: dict = Depends(require_login)):
    """测试推送（需要登录）"""
    from app.notifier import Notifier

    if not _user_store:
        raise HTTPException(status_code=500, detail="服务未初始化")
    push_config = _user_store.get_push_config(current_user["username"])

    if not push_config or not push_config.get("enabled"):
        raise HTTPException(status_code=400, detail="请先配置并启用推送渠道")

    # 临时构建一个 Notifier 实例，使用用户的配置
    notifier = Notifier(user_push_config=push_config)
    notifier.type = push_config.get("type", "")
    notifier.url = push_config.get("url", "")
    notifier.token = push_config.get("token", "")
    notifier.pushplus_channel = push_config.get("channel", "wechat")
    notifier.telegram_chat_id = ""

    success, detail = notifier.send_with_detail(
        title="🎮 Epic 推送测试",
        body="这是一条测试推送。如果你收到了这条消息，说明推送配置正确。",
        games=[{
            "title": "测试游戏",
            "url": "https://store.epicgames.com/zh-CN/free-games",
            "original_price": "¥99.00",
            "end_date": "2026-12-31",
        }],
    )

    message = "推送已发送" if success else "推送失败"
    if detail:
        message = f"推送失败：{detail}"

    return {
        "success": success,
        "message": message,
    }

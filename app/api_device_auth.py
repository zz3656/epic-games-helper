"""
Device Auth 申请与轮询 API（从 main.py 拆分）

用户在自己浏览器完成 Epic 登录授权后，工具获得永不过期的 device auth token。
"""
import asyncio
import logging
import os
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.epic_api import EpicAPIClient, DeviceAuthCredentials

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存中的 device code 申请记录（用于轮询）
_pending_device_codes: Dict[str, Dict] = {}
# 凭据存储（从 main.py 引入，避免循环依赖）
_credential_store = None


def set_credential_store(store):
    global _credential_store
    _credential_store = store


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int


class DeviceAuthSaveRequest(BaseModel):
    account_id: str
    device_id: str
    secret: str


@router.post("/api/device-auth/request")
async def request_device_auth():
    """申请 device code

    返回 user_code 和 verification_uri，用户需要在浏览器中打开 verification_uri
    并输入 user_code 完成 Epic 登录授权。
    """
    try:
        async with EpicAPIClient() as client:
            device_code, user_code, verification_uri, expires_in = \
                await client.request_device_code()

        # 保存到内存，10 分钟后过期
        _pending_device_codes[device_code] = {
            "user_code": user_code,
            "verification_uri": verification_uri,
            "expires_at": time.time() + expires_in,
            "created_at": time.time(),
        }

        logger.info("Device code 申请成功: user_code=%s", user_code)
        return JSONResponse(content={
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": f"{verification_uri}?code={user_code}" if "?" not in verification_uri else verification_uri,
            "expires_in": expires_in,
        })
    except Exception as e:
        logger.exception("申请 device code 失败")
        raise HTTPException(status_code=500, detail=f"申请失败: {e}")


@router.get("/api/device-auth/poll/{device_code}")
async def poll_device_auth(device_code: str):
    """轮询 device code 完成状态

    返回状态：pending（等待用户）/ success（用户完成）/ expired（过期）
    """
    pending = _pending_device_codes.get(device_code)
    if not pending:
        return JSONResponse(content={
            "status": "expired",
            "message": "Device code 已过期或不存在，请重新申请",
        })

    if time.time() > pending["expires_at"]:
        _pending_device_codes.pop(device_code, None)
        return JSONResponse(content={"status": "expired", "message": "已过期"})

    try:
        async with EpicAPIClient() as client:
            credentials = await client.poll_device_code(device_code)

        if credentials:
            # 用户已完成登录，保存 device auth
            if _credential_store and _credential_store.save_device_auth(credentials):
                _pending_device_codes.pop(device_code, None)
                logger.info("Device auth 保存成功: account_id=%s", credentials.account_id)
                return JSONResponse(content={
                    "status": "success",
                    "message": "Epic 登录授权成功！之后每周自动领取无需重新登录",
                    "account_id": credentials.account_id,
                })
            else:
                return JSONResponse(content={
                    "status": "error",
                    "message": "保存 device auth 失败",
                })

        return JSONResponse(content={
            "status": "pending",
            "message": "等待用户在浏览器完成登录...",
            "user_code": pending["user_code"],
            "verification_uri_complete": f"{pending['verification_uri']}?code={pending['user_code']}" if "?" not in pending["verification_uri"] else pending["verification_uri"],
        })
    except Exception as e:
        logger.exception("轮询 device code 失败")
        return JSONResponse(content={
            "status": "error",
            "message": f"轮询失败: {e}",
        })


@router.delete("/api/device-auth/cancel/{device_code}")
async def cancel_device_auth(device_code: str):
    """取消 device code 申请"""
    _pending_device_codes.pop(device_code, None)
    return JSONResponse(content={"cancelled": True})


@router.delete("/api/device-auth")
async def delete_device_auth_endpoint():
    """撤销已保存的 device auth"""
    if not _credential_store:
        raise HTTPException(status_code=500, detail="Credential store 未初始化")
    if not _credential_store.has_device_auth():
        raise HTTPException(status_code=404, detail="未配置 device auth")
    if _credential_store.delete_device_auth():
        return JSONResponse(content={"success": True, "message": "设备授权已撤销"})
    raise HTTPException(status_code=500, detail="撤销失败")


@router.get("/api/device-auth/status")
async def device_auth_status():
    """查询 device auth 状态"""
    configured = False
    if _credential_store:
        configured = _credential_store.has_device_auth()
    return JSONResponse(content={
        "device_auth_configured": configured,
    })


@router.post("/api/device-auth/test/free-games")
async def test_fetch_free_games():
    """调试接口：测试免费游戏 API（无需登录）"""
    from app.epic_api import EpicAPIClient
    try:
        async with EpicAPIClient() as client:
            games = await client.fetch_free_games()
        return JSONResponse(content={
            "success": True,
            "count": len(games),
            "games": [
                {"title": g.title, "offer_id": g.offer_id, "url": g.url}
                for g in games
            ],
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e),
        }, status_code=500)


@router.post("/api/device-auth/test/request")
async def test_request_device_code():
    """调试接口：测试申请 device code（不存储）"""
    from app.epic_api import EpicAPIClient
    try:
        async with EpicAPIClient() as client:
            device_code, user_code, verification_uri, expires_in = \
                await client.request_device_code()
        return JSONResponse(content={
            "success": True,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": f"{verification_uri}?code={user_code}" if "?" not in verification_uri else verification_uri,
            "expires_in": expires_in,
            "device_code_preview": device_code[:10] + "...",
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e),
        }, status_code=500)


@router.post("/api/device-auth/test/claim")
async def test_claim_with_device_auth():
    """调试接口：用 device auth token 测试领取流程

    必须先完成设备码授权才能使用。
    """
    if not _credential_store or not _credential_store.has_device_auth():
        return JSONResponse(content={
            "success": False,
            "error": "未配置 device auth，请先完成设备码授权",
        }, status_code=400)

    from app.epic_api import EpicAPIClient
    credentials = _credential_store.load_device_auth()
    if not credentials:
        return JSONResponse(content={
            "success": False,
            "error": "读取 device auth 失败",
        }, status_code=500)

    try:
        async with EpicAPIClient() as client:
            games = await client.fetch_free_games()
            if not games:
                return JSONResponse(content={
                    "success": True,
                    "message": "本周暂无免费游戏",
                    "games": [],
                })

            results = []
            for game in games:
                status, message = await client.claim_game(credentials, game)
                results.append({
                    "title": game.title,
                    "offer_id": game.offer_id,
                    "status": status,
                    "message": message,
                })

            return JSONResponse(content={
                "success": True,
                "games": results,
            })
    except Exception as e:
        logger.exception("测试领取失败")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
        }, status_code=500)

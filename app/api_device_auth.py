"""
Device Auth 申请与轮询 API

用户在自己浏览器完成 Epic 登录授权后，工具获得永不过期的 device auth token。
之后调用 Epic HTTP API 完成领取，无需浏览器、无需 hCaptcha。
"""
import asyncio
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.epic_api import EpicAPIClient

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
            device_code, user_code, verification_uri, expires_in, client_used = \
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


# 用于 /api/device-auth/claim-now 的进度追踪
from typing import Dict, Any
import asyncio as _asyncio

_claim_progress: Dict[str, Dict[str, Any]] = {}
_claim_results: Dict[str, Dict[str, Any]] = {}


class DeviceAuthClaimRequest(BaseModel):
    claim_id: str


@router.post("/api/device-auth/claim-now")
async def claim_now_with_device_auth(req: DeviceAuthClaimRequest):
    """使用 device auth token 立即领取（基于 device auth 模式，无需账号密码）

    与 /api/claim 的区别：本接口使用 device auth token 绕过浏览器，完全 HTTP API 调用。
    """
    from app.epic_api import EpicAPIClient, FreeGame as ApiFreeGame

    if not _credential_store or not _credential_store.has_device_auth():
        raise HTTPException(status_code=400, detail="未配置 device auth，请先完成设备码授权")

    claim_id = req.claim_id
    _claim_progress[claim_id] = {
        "claim_id": claim_id,
        "step": "启动中...",
        "status": "active",
    }

    async def _do_claim():
        credentials = _credential_store.load_device_auth()
        if not credentials:
            _claim_progress[claim_id] = {"step": "读取 device auth 失败", "status": "done"}
            return

        try:
            _claim_progress[claim_id]["step"] = "📦 获取本周免费游戏..."
            _claim_progress[claim_id]["status"] = "active"

            async with EpicAPIClient() as client:
                free_games = await client.fetch_free_games()

                if not free_games:
                    _claim_results[claim_id] = {
                        "success": True,
                        "error": "本周暂无免费游戏",
                        "games": [],
                    }
                    _claim_progress[claim_id] = {"step": "本周暂无免费游戏", "status": "done"}
                    return

                _claim_progress[claim_id]["step"] = f"发现 {len(free_games)} 款免费游戏，开始领取"

                results = []
                for i, game in enumerate(free_games, 1):
                    _claim_progress[claim_id]["step"] = (
                        f"🎯 领取 [{i}/{len(free_games)}]: {game.title}"
                    )
                    status, message = await client.claim_game(credentials, game)
                    results.append({
                        "title": game.title,
                        "offer_id": game.offer_id,
                        "url": game.url,
                        "status": status,
                        "message": message,
                    })

                success = all(g["status"] in ("claimed", "already_claimed", "needs_manual") for g in results)
                _claim_results[claim_id] = {
                    "success": success,
                    "username": f"DeviceAuth:{credentials.account_id[:6]}***",
                    "error": None if success else "部分或全部游戏领取失败",
                    "games": results,
                }
                _claim_progress[claim_id] = {
                    "step": f"{'✅' if success else '❌'} 领取{'成功' if success else '完成'}",
                    "status": "done",
                }
        except Exception as e:
            logger.exception("device auth 领取失败")
            _claim_results[claim_id] = {
                "success": False,
                "error": f"异常: {type(e).__name__}: {e}",
                "games": [],
            }
            _claim_progress[claim_id] = {"step": f"异常: {e}", "status": "done"}

    _asyncio.create_task(_do_claim())
    return JSONResponse(content={"claim_id": claim_id, "message": "领取任务已启动"})


@router.get("/api/claim/progress/{claim_id}")
async def claim_progress_endpoint(claim_id: str):
    """查询领取进度（复用 /api/claim 的进度接口）"""
    progress = _claim_progress.get(claim_id)
    if not progress:
        result_dict = _claim_results.get(claim_id)
        if result_dict:
            _claim_results.pop(claim_id, None)
            return JSONResponse(content={
                "claim_id": claim_id,
                "step": "领取完成",
                "status": "done",
                "result": result_dict,
            })
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    if progress.get("status") == "done":
        result_dict = _claim_results.get(claim_id)
        if result_dict:
            progress["result"] = result_dict
        _claim_progress.pop(claim_id, None)
        if result_dict:
            _claim_results.pop(claim_id, None)

    return JSONResponse(content=progress)


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


@router.post("/api/device-auth/test/free-games-raw")
async def test_fetch_free_games_raw():
    """调试接口：查看 Epic API 原始返回（诊断用）"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.get(
                "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions",
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/141.0.0.0 Safari/537.36",
                },
            )
            data = resp.json()
            elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
            # 只看前 5 个游戏的详细 promotions 结构
            summary = []
            for item in elements[:5]:
                title = item.get("title", "")
                item_id = item.get("id", "")
                slug = item.get("productSlug") or item.get("urlSlug") or item.get("offerId", "")
                promos = item.get("promotions") or {}
                summary.append({
                    "title": title,
                    "id": item_id,
                    "slug": slug,
                    "promotions": promos,  # 完整结构
                })
            return JSONResponse(content={
                "success": True,
                "total_elements": len(elements),
                "elements_with_promotions": sum(1 for e in elements if e.get("promotions")),
                "summary": summary,
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
            device_code, user_code, verification_uri, expires_in, client_used = \
                await client.request_device_code()
        return JSONResponse(content={
            "success": True,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": f"{verification_uri}?code={user_code}" if "?" not in verification_uri else verification_uri,
            "expires_in": expires_in,
            "device_code_preview": device_code[:10] + "...",
            "client_used": client_used,
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


@router.get("/api/device-auth/account-info")
async def device_auth_account_info():
    """查询当前已登录设备码账号的可用性

    返回：
    - configured: 是否已保存 device auth
    - account_id: 账号 ID（脱敏）
    - access_token_valid: access_token 是否有效
    - library_api_accessible: library API 是否能访问（账户可用）
    - error: 错误信息（如有）
    """
    if not _credential_store or not _credential_store.has_device_auth():
        return JSONResponse(content={
            "configured": False,
            "account_id": "",
            "access_token_valid": False,
            "library_api_accessible": False,
            "error": "未配置 device auth，请先完成设备码授权",
        })

    credentials = _credential_store.load_device_auth()
    if not credentials:
        return JSONResponse(content={
            "configured": False,
            "account_id": "",
            "access_token_valid": False,
            "library_api_accessible": False,
            "error": "读取 device auth 失败（可能是 master key 不匹配）",
        }, status_code=500)

    account_id = credentials.account_id
    masked_id = (account_id[:6] + "***") if account_id else ""

    result = {
        "configured": True,
        "account_id": masked_id,
        "access_token_valid": not credentials.is_expired(),
        "library_api_accessible": False,
        "error": "",
    }

    # 尝试使用 credentials 访问 library API 检查是否可用
    from app.epic_api import EpicAPIClient
    try:
        async with EpicAPIClient() as client:
            # 先尝试用现有 token
            check_creds = credentials
            if check_creds.is_expired():
                try:
                    check_creds = await client.refresh_access_token(check_creds)
                    result["access_token_valid"] = True
                except Exception as e:
                    result["error"] = f"token 刷新失败：{e}"
                    return JSONResponse(content=result)

            # 尝试调 library API（只取 1 条验证可访问）
            resp = await client.client.get(
                "https://library-service.live.use1a.on.epicgames.com/library/api/public/items",
                params={"includeMetadata": "true", "count": 1},
                headers={"Authorization": f"Bearer {check_creds.access_token}"},
            )
            if resp.status_code == 200:
                result["library_api_accessible"] = True
            elif resp.status_code == 401:
                result["error"] = "Token 无效，需重新授权"
            elif resp.status_code == 403:
                result["error"] = "Token 无权访问 library API，需重新授权"
            else:
                result["error"] = f"library API 返回 HTTP {resp.status_code}"
    except Exception as e:
        logger.exception("检查账号可用性异常")
        result["error"] = f"检查异常：{type(e).__name__}: {e}"

    return JSONResponse(content=result)


@router.get("/api/free-games")
async def get_free_games():
    """获取本周免费游戏列表，包含封面图、描述、是否已拥有、领取链接等信息

    如已授权 device auth，会检查 entitlement 标记是否已拥有。
    """
    from app.epic_api import EpicAPIClient

    credentials = None
    if _credential_store and _credential_store.has_device_auth():
        try:
            credentials = _credential_store.load_device_auth()
        except Exception as e:
            logger.warning("读取 device auth 失败：%s", e)
            return JSONResponse(content={
                "success": False,
                "error": f"读取 device auth 失败：{e}",
                "credential_unavailable": True,
            }, status_code=500)

    try:
        async with EpicAPIClient() as client:
            logger.info("Fetching free games (credentials=%s)", "yes" if credentials else "no")
            games = await client.fetch_free_games_with_status(credentials)
            logger.info("Got %d free games", len(games))
            return JSONResponse(content={
                "success": True,
                "games": [
                    {
                        "title": g.title,
                        "url": g.url,
                        "offer_id": g.offer_id,
                        "namespace": g.namespace,
                        "image_url": g.image_url,
                        "description": g.description,
                        "already_owned": g.already_owned,
                        "checkout_url": g.checkout_url,
                        "start_date": g.start_date,
                        "end_date": g.end_date,
                        "original_price": g.original_price,
                    }
                    for g in games
                ],
            })
    except Exception as e:
        logger.exception("获取免费游戏列表失败")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
        }, status_code=500)

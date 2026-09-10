"""
Device Auth 申请与轮询 API

用户在自己浏览器完成 Epic 登录授权后，工具获得永不过期的 device auth token。
之后调用 Epic HTTP API 完成领取，无需浏览器、无需 hCaptcha。
"""
import asyncio
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.epic_api import EpicAPIClient, EPIC_ENTITLEMENTS_URL

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
                    "message": "Epic 登录授权成功！之后每周自动跟踪游戏领取状态",
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
                free_games, _ = await client.fetch_free_games()

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
            games, upcoming = await client.fetch_free_games()
        return JSONResponse(content={
            "success": True,
            "count": len(games),
            "upcoming_count": len(upcoming),
            "games": [
                {"title": g.title, "offer_id": g.offer_id, "url": g.url}
                for g in games
            ],
            "upcoming": [
                {"title": g.title, "offer_id": g.offer_id, "url": g.url,
                 "start_date": g.start_date, "end_date": g.end_date}
                for g in upcoming
            ],
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e),
        }, status_code=500)


@router.post("/api/scheduler/test-run")
async def test_scheduler_run():
    """手动触发定时任务（调试用）

    用于验证周五 0:05 定时任务的完整逻辑：
    1. 拉取本周免费游戏
    2. 与上一次的 fingerprint 对比
    3. 如果有变化，推送 webhook
    4. 写入 history.json

    如有 device auth 则实际执行；否则仅记录游戏列表。
    """
    from app.main import scheduler as _sched
    if _sched is None:
        return JSONResponse(content={"success": False, "error": "scheduler 未初始化"}, status_code=500)
    try:
        await _sched._run_scheduled_job()
        return JSONResponse(content={"success": True, "message": "定时任务已手动触发"})
    except Exception as e:
        logger.exception("手动触发定时任务失败")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@router.post("/api/scheduler/test-notify")
async def test_scheduler_notify():
    """发送测试推送（调试用，验证 webhook 配置是否正确）"""
    from app.main import scheduler as _sched
    if _sched is None:
        return JSONResponse(content={"success": False, "error": "scheduler 未初始化"}, status_code=500)
    if not _sched.notifier.enabled:
        return JSONResponse(content={
            "success": False,
            "error": "Webhook 未配置。请设置 NOTIFY_WEBHOOK_TYPE/NOTIFY_WEBHOOK_URL/NOTIFY_WEBHOOK_TOKEN 环境变量",
        }, status_code=400)
    sent = await _sched.notifier.send(
        title="🎮 Epic 推送测试",
        body="这是一条测试推送。如果你收到了这条消息，说明 webhook 配置正确。",
        games=[{
            "title": "测试游戏",
            "url": "https://store.epicgames.com/zh-CN/free-games",
            "original_price": "¥99.00",
            "end_date": "2026-12-31",
        }],
    )
    return JSONResponse(content={
        "success": sent,
        "message": "推送已发送" if sent else "推送失败（查看后端日志）",
    })


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
            games, _ = await client.fetch_free_games()
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
    """查询当前已登录设备码账号的基本信息

    返回：
    - configured: 是否已保存 device auth
    - account_id: 账号 ID（脱敏）
    - access_token_valid: access_token 是否有效（本地判断）
    - access_token_expires_in: 过期时间（秒）
    - note: 说明文字

    注意：此接口不调任何 Epic API，避免超时。只检查本地凭证状态。
    library API 的检查请使用 /api/free-games 返回的 diagnostics。
    """
    if not _credential_store or not _credential_store.has_device_auth():
        return JSONResponse(content={
            "configured": False,
            "account_id": "",
            "access_token_valid": False,
            "access_token_expires_in": 0,
            "note": "未配置 device auth，请先完成设备码授权",
        })

    credentials = _credential_store.load_device_auth()
    if not credentials:
        return JSONResponse(content={
            "configured": False,
            "account_id": "",
            "access_token_valid": False,
            "access_token_expires_in": 0,
            "note": "读取 device auth 失败（可能是 master key 不匹配）",
        }, status_code=500)

    account_id = credentials.account_id
    masked_id = (account_id[:6] + "***") if account_id else ""

    expires_in = max(0, int(credentials.expires_at - time.time())) if credentials.expires_at else 0

    return JSONResponse(content={
        "configured": True,
        "account_id": masked_id,
        "device_id_prefix": (credentials.device_id[:6] + "***") if credentials.device_id else "",
        "access_token_valid": not credentials.is_expired(),
        "access_token_expires_in": expires_in,
        "note": "本地凭证检查。如需验证账号可用性，请调用 /api/free-games",
    })


# @router.get("/api/debug/entitlements-raw")
# async def debug_entitlements_raw():
#     """调试接口：已禁用（完整游戏库功能已下线，entitlements 仅返回 UE 插件噪声）
#
#     历史：曾用于查看用户 entitlements 分布，发现 98% 是 UE 引擎插件（噪声），
#     完整游戏库需 library-service 权限（OAuth authorization_code flow），
#     第三方应用无法获取。
#     """
#     return JSONResponse(content={
#         "success": False,
#         "error": "该调试接口已禁用。完整游戏库功能不可用（参见 README）。",
#     }, status_code=410)


# ============================================
# Authorization Code Flow 端点
# ============================================
# Authorization Code Flow 端点已从当前版本移除
# ============================================
# 原因：Epic 内部 OAuth client (launcherAppClient2) 未注册 localhost redirect_uri，
# 任何 /id/authorize 调用都会返回 errors.com.epicgames.accountportal.client_redirect_domain_mismatch 错误。
# 完整游戏库查询需要的 library:public:items 权限只能通过 OAuth authorization_code flow 获得，
# 但第三方应用无法使用该流程。device auth + entitlements API 仅返回 UE 插件噪声（98% 不是游戏）。
#
# 如需查看完整游戏库，请前往 https://www.epicgames.com/store/mygames
# ============================================


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
            games, upcoming, diagnostics = await client.fetch_free_games_with_status(credentials)
            logger.info("Got %d free games, %d upcoming, diagnostics=%s",
                        len(games), len(upcoming), diagnostics)
            return JSONResponse(content={
                "success": True,
                "diagnostics": diagnostics,
                "free_games": [
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
                "upcoming_free_games": [
                    {
                        "title": g.title,
                        "url": g.url,
                        "offer_id": g.offer_id,
                        "namespace": g.namespace,
                        "image_url": g.image_url,
                        "start_date": g.start_date,
                        "end_date": g.end_date,
                        "original_price": g.original_price,
                    }
                    for g in upcoming
                ],
            })
    except Exception as e:
        logger.exception("获取免费游戏列表失败")
        return JSONResponse(content={
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }, status_code=500)


@router.get("/api/account/games")
async def get_account_games():
    """获取本账号的相关游戏列表（简化版）：
    1. 本周免费游戏（含领取链接）
    2. 下周预告

    注：完整游戏库查询已被禁用（library-service 需要 OAuth 授权，第三方应用不可用）。
    如需查看完整游戏库，请前往 https://www.epicgames.com/store/mygames
    """
    from app.epic_api import EpicAPIClient

    try:
        async with EpicAPIClient() as client:
            free_games, upcoming_games, free_diag = await client.fetch_free_games_with_status(None)
            free_list = [
                {
                    "title": g.title,
                    "url": g.url,
                    "offer_id": g.offer_id,
                    "namespace": g.namespace,
                    "image_url": g.image_url,
                    "description": g.description,
                    "checkout_url": g.checkout_url,
                    "start_date": g.start_date,
                    "end_date": g.end_date,
                    "original_price": g.original_price,
                }
                for g in free_games
            ]
            upcoming_list = [
                {
                    "title": g.title,
                    "url": g.url,
                    "offer_id": g.offer_id,
                    "namespace": g.namespace,
                    "image_url": g.image_url,
                    "start_date": g.start_date,
                    "end_date": g.end_date,
                    "original_price": g.original_price,
                }
                for g in upcoming_games
            ]

            logger.info("Free games: %d, Upcoming: %d", len(free_list), len(upcoming_list))
            return JSONResponse(content={
                "success": True,
                "free_games": free_list,
                "upcoming_free_games": upcoming_list,
                "free_games_diagnostic": free_diag,
            })
    except Exception as e:
        logger.exception("获取游戏列表失败")
        return JSONResponse(content={
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }, status_code=500)

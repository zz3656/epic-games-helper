"""FastAPI 主入口"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi.responses import FileResponse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import load_config
from app.credential_store import CredentialStore
from app.scheduler import ClaimScheduler
from app.storage import ResultStore

# 日志
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 全局对象（在 lifespan 中初始化）
config = load_config()
store = ResultStore()
cred_store = CredentialStore(key=os.getenv("EPIC_MASTER_KEY"))
auto_claim_default = os.getenv("AUTO_CLAIM_ENABLED", "false").lower() == "true"
scheduler = ClaimScheduler(
    config=config,
    store=store,
    credential_store=cred_store,
    auto_claim_enabled=auto_claim_default,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    scheduler.start()
    if cred_store.is_configured():
        logger.info("检测到已保存的加密凭证（自动领取 %s）",
                    "已启用" if auto_claim_default else "未启用")
    else:
        logger.info("未配置凭证，需先通过 Web 端保存账号密码")
    logger.info("Epic Games 自动领取服务已启动")
    yield
    # 关闭
    scheduler.shutdown()
    logger.info("服务关闭")


app = FastAPI(
    title="Epic Games 自动领取",
    description="每周自动领取 Epic Games 免费游戏",
    version="2.0.0",
    lifespan=lifespan,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 注册拆分的路由
from app.api_vnc import router as vnc_router
from app.api_vnc_ws import router as vnc_ws_router
app.include_router(vnc_router)
app.include_router(vnc_ws_router)


# ============== 进度追踪 ==============
claim_progress: Dict[str, Dict[str, Any]] = {}
claim_results: Dict[str, Dict[str, Any]] = {}  # 存储完整结果，供进度查询时附加
pending_verifications: Dict[str, Dict[str, Any]] = {}  # 待输入邮箱验证码的任务


def track_progress(claim_id: str, step: str, status: str, extra: Optional[Dict] = None):
    """记录领取进度（供前端轮询）"""
    entry = {"claim_id": claim_id, "step": step, "status": status}
    if extra:
        entry.update(extra)
    claim_progress[claim_id] = entry


def store_result(claim_id: str, result_dict: Dict[str, Any]):
    """存储完整领取结果"""
    claim_results[claim_id] = result_dict


def register_verification(claim_id: str, username: str):
    """登记需要邮箱验证码的任务"""
    pending_verifications[claim_id] = {
        "claim_id": claim_id,
        "username": username,
        "started_at": __import__('datetime').datetime.now().isoformat(timespec="seconds"),
    }


def unregister_verification(claim_id: str):
    pending_verifications.pop(claim_id, None)


# ============== 数据模型 ==============
class Credentials(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)
    verification_code: str = Field(default="", max_length=20)


class SaveCredentialsRequest(BaseModel):
    """保存凭证请求 - 加密后存储"""
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)
    enable_auto_claim: bool = True


class AutoClaimToggle(BaseModel):
    enabled: bool


# ============== 页面路由 ==============
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "schedule_info": {
                "day": config.schedule_day,
                "hour": config.schedule_hour,
                "minute": config.schedule_minute,
                "timezone": config.timezone,
            },
            "auto_claim_enabled": scheduler.auto_claim_enabled,
            "credential_configured": cred_store.is_configured(),
        },
    )


@app.get("/vnc-viewer", response_class=HTMLResponse)
async def vnc_page(request: Request):
    """嵌入式 VNC 页面（不需要单独的端口）

    仅需 8000 端口即可访问 VNC，不需要 6080/5900 端口映射。
    """
    html_path = os.path.join(BASE_DIR, "static", "embedded-vnc.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="VNC 页面文件不存在")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ============== API 路由 ==============
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "schedule": {
            "day": config.schedule_day,
            "time": f"{config.schedule_hour:02d}:{config.schedule_minute:02d}",
            "timezone": config.timezone,
        },
        "auto_claim_enabled": scheduler.auto_claim_enabled,
        "credential_configured": cred_store.is_configured(),
    }


# /api/vnc/status 等 VNC/截图接口已拆出到 app.api_vnc


async def _progress_callback(claim_id: str, step: str, status: str):
    """进度回调：桥接 claimer → claim_progress"""
    track_progress(claim_id, step, status)


@app.post("/api/claim")
async def claim_now(creds: Credentials):
    """立即触发一次领取（密码仅在请求作用域内）"""
    claim_id = str(uuid.uuid4())
    logger.info("收到领取请求，用户: %s (claim_id=%s)", _mask(creds.username), claim_id)

    async def _do_claim():
        scheduler._on_progress = lambda step, status: track_progress(claim_id, step, status)
        try:
            # 优先使用请求中提供的验证码，否则从临时文件读取
            verification_code = creds.verification_code or None
            if not verification_code:
                try:
                    import os
                    if os.path.exists(VERIFICATION_CODE_FILE):
                        with open(VERIFICATION_CODE_FILE) as f:
                            verification_code = f.read().strip()
                        # 读取后删除（一次性使用）
                        os.remove(VERIFICATION_CODE_FILE)
                        logger.info("使用临时保存的邮箱验证码")
                except Exception as e:
                    logger.warning("读取临时验证码失败: %s", e)
            result = await scheduler.run_now(
                creds.username, creds.password,
                verification_code=verification_code,
            )
            result_dict = _result_to_dict(result)
            # 检查是否需要邮箱验证
            if result_dict.get("needs_verification"):
                register_verification(claim_id, creds.username)
                track_progress(claim_id, "需要邮箱验证码", "done")
            else:
                store_result(claim_id, result_dict)
                track_progress(claim_id, f"领取完成: {'成功' if result.success else '失败'}", "done")
            return result
        except Exception as e:
            track_progress(claim_id, f"异常: {e}", "done")
            raise
        finally:
            creds.password = None  # noqa: F841
            scheduler._on_progress = None

    asyncio.create_task(_do_claim())
    return JSONResponse(content={"claim_id": claim_id, "message": "领取任务已启动"})


@app.get("/api/claim/progress/{claim_id}")
async def claim_progress_endpoint(claim_id: str):
    """查询领取进度（轮询接口）"""
    progress = claim_progress.get(claim_id)
    needs_verification = claim_id in pending_verifications
    if not progress:
        result_dict = claim_results.get(claim_id)
        if result_dict:
            claim_results.pop(claim_id, None)
            return JSONResponse(content={"claim_id": claim_id, "step": "领取完成", "status": "done",
                                        "result": result_dict})
        # 是否有等待中的邮箱验证
        if needs_verification:
            return JSONResponse(content={"claim_id": claim_id, "step": "需要邮箱验证码",
                                        "status": "needs_verification", "result": None})
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if progress.get("status") == "done":
        result_dict = claim_results.get(claim_id)
        if result_dict:
            progress["result"] = result_dict
        claim_progress.pop(claim_id, None)
        if result_dict:
            claim_results.pop(claim_id, None)
    if needs_verification:
        progress["status"] = "needs_verification"
    return JSONResponse(content=progress)


class VerificationCodeRequest(BaseModel):
    claim_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=4, max_length=10)


# 用于跨请求保存验证代码的临时文件路径
VERIFICATION_CODE_FILE = "/app/data/.pending_verification_code"


@app.post("/api/claim/verification")
async def submit_verification_code(req: VerificationCodeRequest):
    """提交邮箱验证码，保存到临时文件供下次领取使用。"""
    pending = pending_verifications.get(req.claim_id)
    if not pending:
        # 仍然允许保存验证码，以便下次领取时读取
        pass
    # 写入临时文件
    try:
        import os
        os.makedirs("/app/data", exist_ok=True)
        with open(VERIFICATION_CODE_FILE, "w") as f:
            f.write(req.code)
        # 清理已验证任务
        unregister_verification(req.claim_id)
        track_progress(req.claim_id, "已保存验证码，请重新触发领取任务", "done")
        return JSONResponse(content={
            "claim_id": req.claim_id,
            "message": "验证码已保存，请在 60 秒内点击「开始领取」按钮重新触发任务，系统会自动使用该验证码",
            "code_saved": True,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@app.get("/api/claim/verification/pending")
async def pending_verification_status():
    """检查是否有待提交的验证码"""
    import os
    code_exists = os.path.exists(VERIFICATION_CODE_FILE)
    pending = list(pending_verifications.values())
    return {
        "pending_tasks": pending,
        "saved_code_exists": code_exists,
    }


# ----- 凭证管理 -----
@app.post("/api/credentials")
async def save_credentials(req: SaveCredentialsRequest):
    """
    保存账号密码（加密后持久化）

    启用自动领取后，每周四定时从加密文件解密并执行。
    """
    username = req.username
    password = req.password

    if not cred_store.save(username, password):
        raise HTTPException(status_code=500, detail="保存失败")

    scheduler.enable_auto_claim(req.enable_auto_claim)

    logger.info("凭证已保存，自动领取: %s", "启用" if req.enable_auto_claim else "关闭")
    return {
        "success": True,
        "message": "凭证已加密保存",
        "auto_claim_enabled": scheduler.auto_claim_enabled,
        "credential_configured": True,
    }


@app.delete("/api/credentials")
async def delete_credentials():
    """删除已保存的凭证"""
    if not cred_store.is_configured():
        raise HTTPException(status_code=404, detail="未配置凭证")
    if cred_store.delete():
        scheduler.enable_auto_claim(False)
        return {"success": True, "message": "凭证已删除"}
    raise HTTPException(status_code=500, detail="删除失败")


@app.get("/api/credentials/status")
async def credentials_status():
    """查询凭证状态（不返回明文）"""
    return {
        "configured": cred_store.is_configured(),
        "auto_claim_enabled": scheduler.auto_claim_enabled,
        **cred_store.status(),
    }


# /api/screenshots 接口已拆出到 app.api_vnc


@app.post("/api/auto-claim/toggle")
async def toggle_auto_claim(req: AutoClaimToggle):
    """开关自动领取（不影响已保存的凭证）"""
    if req.enabled and not cred_store.is_configured():
        raise HTTPException(status_code=400, detail="未配置凭证，请先保存账号密码")
    scheduler.enable_auto_claim(req.enabled)
    return {
        "success": True,
        "auto_claim_enabled": scheduler.auto_claim_enabled,
    }


# ----- 历史 -----
@app.get("/api/history")
async def history(limit: int = 20):
    records = store.list()
    return {"total": len(records), "items": records[-limit:][::-1]}


@app.get("/api/history/latest")
async def history_latest():
    return store.latest()


# ============== 工具 ==============
def _result_to_dict(result) -> dict:
    import os
    vnc_enabled = os.getenv("ENABLE_VNC", "false").lower() == "true"
    return {
        "success": result.success,
        "username": result.username,
        "error": result.error,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "screenshot_path": result.screenshot_path,
        "login_failed": result.success is False and result.games == [] and (
            result.login_status or ""
        ) != "" and (result.login_status or "") != "success",
        "login_status": getattr(result, "login_status", "") or "",
        "needs_verification": (getattr(result, "login_status", "") or "") == "needs_verification",
        "vnc_enabled": vnc_enabled,
        "games": [
            {
                "title": g.title, "url": g.url,
                "status": g.status, "message": g.message,
            }
            for g in result.games
        ],
    }


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=config.log_level.lower(),
    )
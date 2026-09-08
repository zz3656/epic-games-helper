"""FastAPI 主入口"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
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


# ============== 进度追踪 ==============
claim_progress: Dict[str, Dict[str, Any]] = {}
claim_results: Dict[str, Dict[str, Any]] = {}  # 存储完整结果，供进度查询时附加


def track_progress(claim_id: str, step: str, status: str, extra: Optional[Dict] = None):
    """记录领取进度（供前端轮询）"""
    entry = {"claim_id": claim_id, "step": step, "status": status}
    if extra:
        entry.update(extra)
    claim_progress[claim_id] = entry


def store_result(claim_id: str, result_dict: Dict[str, Any]):
    """存储完整领取结果"""
    claim_results[claim_id] = result_dict


# ============== 数据模型 ==============
class Credentials(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


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


async def _progress_callback(claim_id: str, step: str, status: str):
    """进度回调：桥接 claimer → claim_progress"""
    track_progress(claim_id, step, status)


@app.post("/api/claim")
async def claim_now(creds: Credentials):
    """立即触发一次领取（密码仅在请求作用域内）"""
    claim_id = str(uuid.uuid4())
    logger.info("收到领取请求，用户: %s (claim_id=%s)", _mask(creds.username), claim_id)

    async def _do_claim():
        # 设置进度回调桥接
        scheduler._on_progress = lambda step, status: track_progress(claim_id, step, status)
        try:
            result = await scheduler.run_now(creds.username, creds.password)
            result_dict = _result_to_dict(result)
            store_result(claim_id, result_dict)
            track_progress(claim_id, f"领取完成: {'成功' if result.success else '失败'}", "done")
            return result
        except Exception as e:
            track_progress(claim_id, f"异常: {e}", "done")
            raise
        finally:
            creds.password = None  # noqa: F841
            # 清理回调
            scheduler._on_progress = None

    # 后台执行领取，立即返回 claim_id
    asyncio.create_task(_do_claim())
    return JSONResponse(content={"claim_id": claim_id, "message": "领取任务已启动"})


@app.get("/api/claim/progress/{claim_id}")
async def claim_progress_endpoint(claim_id: str):
    """查询领取进度（轮询接口）"""
    progress = claim_progress.get(claim_id)
    if not progress:
        # 检查是否已有结果
        result_dict = claim_results.get(claim_id)
        if result_dict:
            claim_results.pop(claim_id, None)
            return JSONResponse(content={"claim_id": claim_id, "step": "领取完成", "status": "done",
                                        "result": result_dict})
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    # 如果进度已完成，附加完整结果
    if progress.get("status") == "done":
        result_dict = claim_results.get(claim_id)
        if result_dict:
            progress["result"] = result_dict
        claim_progress.pop(claim_id, None)
        if result_dict:
            claim_results.pop(claim_id, None)
    return JSONResponse(content=progress)


@app.get("/api/claim/progress/{claim_id}")
async def claim_progress_endpoint(claim_id: str):
    """查询领取进度（轮询接口）"""
    progress = claim_progress.get(claim_id)
    if not progress:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    # 如果进度已完成，附加完整结果
    if progress.get("status") == "done":
        # 清理旧进度
        claim_progress.pop(claim_id, None)
    return JSONResponse(content=progress)


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
    return {
        "success": result.success,
        "username": result.username,
        "error": result.error,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "screenshot_path": result.screenshot_path,
        "login_failed": result.success is False and result.games == [] and (
            result.error or ""
        ).startswith("登录失败"),
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
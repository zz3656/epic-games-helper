"""
FastAPI 主入口

应用架构：
- Device Auth 设备码授权（用户在浏览器完成 Epic 登录）
- Epic HTTP API 调用（完全避开浏览器、hCaptcha、Playwright）
- 定时调度（每周自动领取）
"""
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
    if cred_store.has_device_auth():
        logger.info("检测到已保存的 device auth（自动领取 %s）",
                    "已启用" if auto_claim_default else "未启用")
    else:
        logger.info("未配置 device auth，需先通过 Web 端完成 Epic 设备码授权")
    logger.info("Epic Games 自动领取服务已启动")
    yield
    # 关闭
    scheduler.shutdown()
    logger.info("服务关闭")


app = FastAPI(
    title="Epic Games 自动领取",
    description="通过 Epic 设备码授权 + HTTP API 自动领取每周免费游戏",
    version="3.0.0",
    lifespan=lifespan,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 注册 device auth 路由
from app.api_device_auth import router as device_auth_router, set_credential_store
app.include_router(device_auth_router)

# 注入凭据存储
set_credential_store(cred_store)


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
            "device_auth_configured": cred_store.has_device_auth(),
        },
    )


# ============== 基础 API ==============
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "schedule": {
            "day": config.schedule_day,
            "time": f"{config.schedule_hour:02d}:{config.schedule_minute:02d}",
            "timezone": config.timezone,
        },
        "auto_claim_enabled": scheduler.auto_claim_enabled,
        "device_auth_configured": cred_store.has_device_auth(),
    }


@app.get("/api/credentials/status")
async def credentials_status():
    """查询凭证状态（仅 device auth）"""
    return cred_store.status()


@app.post("/api/auto-claim/toggle")
async def toggle_auto_claim(req: AutoClaimToggle):
    """开关自动领取（不影响已保存的 device auth）"""
    if req.enabled and not cred_store.has_device_auth():
        raise HTTPException(status_code=400, detail="未配置 device auth，请先完成 Epic 设备码授权")
    scheduler.enable_auto_claim(req.enabled)
    return {
        "success": True,
        "auto_claim_enabled": scheduler.auto_claim_enabled,
    }


# ----- 历史 -----

# ============== 数据模型 ==============
class AutoClaimToggle(BaseModel):
    enabled: bool


@app.get("/api/history")
async def history(limit: int = 20):
    records = store.list()
    return {"total": len(records), "items": records[-limit:][::-1]}


@app.get("/api/history/latest")
async def history_latest():
    return store.latest()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=config.log_level.lower(),
    )

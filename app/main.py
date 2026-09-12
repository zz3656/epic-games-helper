"""
FastAPI 主入口

应用架构：
- Epic HTTP API 调用（纯 HTTP，无浏览器，无验证码）
- APScheduler 定时调度（每周拉取免费游戏 + 写入历史）
- JWT 用户认证 + Webhook 通知推送
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config
from app.scheduler import ClaimScheduler
from app.storage import ResultStore
from app.user_store import UserStore

# 日志
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 全局对象（在 lifespan 中初始化）
config = load_config()
store = ResultStore()
user_store = UserStore()
scheduler = ClaimScheduler(
    config=config,
    store=store,
    user_store=user_store,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    scheduler.start()
    logger.info("定时任务已启动，每周五 0:05 检查 Epic 免费游戏更新")
    if user_store:
        users = user_store.list_users()
        logger.info("系统有 %d 个用户 (存储路径: %s)", len(users), user_store.path)
    logger.info("历史文件路径: %s", store.file_path)
    logger.info("Epic Games 免费游戏助手服务已启动")
    yield
    # 关闭
    scheduler.shutdown()
    logger.info("服务关闭")


app = FastAPI(
    title="Epic Games Store Tracker",
    description="Epic Games 商店折扣追踪 · 免费游戏跟踪 · 领取历史 · 通知推送",
    version="3.0.0",
    lifespan=lifespan,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 注册封面代理路由（让国内用户走本地中转，加载 Epic CDN 封面图）
from app.api_cover_proxy import router as cover_proxy_router
app.include_router(cover_proxy_router)

# 注册用户管理路由（user_store 和 auth 模块通过模块级变量注入）
from app import api_users
api_users._user_store = user_store
api_users._auth_module = __import__("app.auth", fromlist=[""])
from app.api_users import router as user_router
app.include_router(user_router)


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
            "next_run": scheduler.get_next_run_time(),
        },
    }


@app.get("/api/free-games")
async def get_free_games():
    """获取本周免费游戏 + 下周预告（纯 HTTP，无需登录）"""
    from app.epic_api import EpicAPIClient
    try:
        async with EpicAPIClient() as client:
            logger.info("Fetching free games")
            games, upcoming = await client.fetch_free_games()
            return {
                "success": True,
                "free_games": [
                    {
                        "title": g.title,
                        "url": g.url,
                        "offer_id": g.offer_id,
                        "namespace": g.namespace,
                        "image_url": g.image_url,
                        "description": g.description,
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
                        "description": g.description,
                        "start_date": g.start_date,
                        "end_date": g.end_date,
                        "original_price": g.original_price,
                    }
                    for g in upcoming
                ],
            }
    except Exception as e:
        logger.exception("获取免费游戏列表失败")
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }


# ----- 历史 -----

def _get_record_expires_at(record: dict) -> Optional[str]:
    """获取一条历史记录的过期时间（ISO 字符串），无则返回 None。

    优先级：
    1. record.expires_at（scheduler 主动写入）
    2. 退回从 record.games 中提取最大 end_date（兼容旧数据）
    """
    expires_at = record.get("expires_at")
    if expires_at:
        return expires_at
    # 兼容旧数据：从 games 数组里提取最大 end_date
    end_dates = [g.get("end_date", "") for g in record.get("games", []) if g.get("end_date")]
    if not end_dates:
        return None
    try:
        return max(end_dates)
    except Exception:
        return end_dates[0] if end_dates else None


def _is_record_expired(record: dict, now: datetime) -> bool:
    """判断一条历史记录是否已过免费期。

    逻辑：
    - 有 expires_at 字段或 games[] 含 end_date：按其中最晚时间与当前时间比较
    - 完全无过期时间信息（理论不应出现）：默认视为已过期（保守起见）
    - 解析失败：默认视为未过期，避免误过滤
    """
    expires_at = _get_record_expires_at(record)
    if not expires_at:
        # 完全无过期信息，保守处理为“未过期”，避免误过滤。但实际上当前代码路径
        # 总能补上 expires_at 或 end_date，这只是防御。
        return False
    try:
        # Python 3.11+ 的 fromisoformat 支持 'Z' 后缀
        ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        # 转换为 UTC naive 统一比较
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts <= now
    except Exception:
        # 解析失败：保守处理为“未过期”，避免误过滤
        return False


@app.get("/api/history")
async def history(limit: int = 20):
    """返回已过期的历史赠送记录（仍在免费期的游戏不算历史）

    - 过滤掉 expires_at > now 的记录（本周免费、下周预告等）
    - 按 started_at 倒序
    - 限制返回数量
    """
    now = datetime.now()
    records = store.list()
    expired = [r for r in records if _is_record_expired(r, now)]
    expired.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    items = expired[:limit]
    return {"total": len(expired), "items": items}


@app.get("/api/history/latest")
async def history_latest():
    """返回最近一条已过期的历史记录（便于前端判断是否还有历史可展示）"""
    now = datetime.now()
    records = store.list()
    expired = [r for r in records if _is_record_expired(r, now)]
    expired.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return expired[0] if expired else {}


@app.get("/api/cover-map")
async def cover_map():
    """返回历史游戏封面映射（用于前端渲染无封面的历史游戏）
    
    从 logs/cover_map.json 读取，该文件由 scripts/backfill_covers.py + apply_cover_map.py 生成。
    前端在渲染无封面历史卡片时，可用此 API 查询真实封面图。
    """
    import json
    import os
    # 直接硬编码路径，确保在 Docker 容器和本地都能正确找到文件
    cover_file = "/app/logs/cover_map.json"
    if os.path.exists(cover_file):
        try:
            with open(cover_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"success": True, "map": data}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "cover_map.json not found", "map": {}}


@app.get("/api/promotions")
async def promotions():
    """返回当前 Epic 商店促销游戏列表（非免费，打折中）"""
    from app.epic_api import EpicAPIClient
    try:
        client = EpicAPIClient()
        try:
            games = await client.fetch_promotions()
        finally:
            await client.close()

        result = []
        for g in games:
            result.append({
                "title": g.title,
                "url": g.url,
                "image_url": g.image_url,
                "description": g.description,
                "original_price": g.original_price,
                "current_price": g.current_price,
                "discount_percent": g.discount_percent,
                "lowest_price": g.lowest_price,
            })
        return {"success": True, "promotions": result}
    except Exception as e:
        logger.error("获取促销游戏失败: %s", e)
        return {"success": False, "error": str(e), "promotions": []}


@app.get("/api/history-prices")
async def history_prices():
    """获取所有当前在 Epic 商店中的游戏价格信息（用于历史卡片价格展示）

    前端用此 API 回填历史赠送游戏卡片的当前售价。
    通过 slug/title 匹配历史游戏与当前商店中的游戏。
    """
    import re
    from app.epic_api import EpicAPIClient
    try:
        client = EpicAPIClient()
        try:
            resp = await client.client.get(
                "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions",
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
            )
            resp.raise_for_status()
            data = resp.json()
            elems = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])

            price_map = {}
            for g in elems:
                if g.get("offerType") != "BASE_GAME":
                    continue
                price = g.get("price", {}).get("totalPrice", {}) or {}
                fmt = price.get("fmtPrice", {}) or {}
                orig = fmt.get("originalPrice", "")
                curr = fmt.get("discountPrice", "")
                # 优先用 productSlug 匹配，其次用 pageSlug
                slug = ""
                mappings = g.get("offerMappings") or []
                if mappings and mappings[0].get("pageSlug"):
                    slug = mappings[0]["pageSlug"]
                if not slug:
                    slug = g.get("productSlug") or ""

                title = g.get("title", "")
                # 只保存有价格信息的游戏
                if orig or curr:
                    price_map[title] = {
                        "original_price": orig,
                        "current_price": curr,
                        "slug": slug,
                        "title": title,
                    }
                    # 同时按 slug 索引
                    if slug:
                        price_map[slug] = price_map[title]

            return {"success": True, "prices": price_map}
        finally:
            await client.close()
    except Exception as e:
        logger.error("获取游戏价格信息失败: %s", e)
        return {"success": False, "error": str(e), "prices": {}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        log_level=config.log_level.lower(),
    )

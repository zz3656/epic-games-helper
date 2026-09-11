"""
Epic CDN 封面图代理

目的：国内用户访问 cdn1.epicgames.com 很慢、经常超时。
方案：浏览器请求本地 /api/cover-proxy?url=...，后端用 httpx 拉取并内存缓存，
然后以 image 响应回给浏览器。同一 URL 只下载一次。

安全：
- 只允许代理 epicgames.com / store.epicgames.com / catalog-public-service 等白名单域
- URL 必须以 http(s):// 开头
- 单次请求超时 15s，限制大小 25MB
"""
import asyncio
import logging
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

# ============== 配置 ==============
ALLOWED_DOMAINS = (
    "cdn1.epicgames.com",
    "cdn2.epicgames.com",
    "epicgames.com",
    "store.epicgames.com",
    "catalog-public-service-prod06.ol.epicgames.com",
    "images.unrealengine.com",
)
MAX_BYTES = 25 * 1024 * 1024        # 25MB 上限（封面图远不到）
TIMEOUT_SECONDS = 15.0
# 缓存条目上限（按 URL 去重，避免内存爆炸）
CACHE_MAX_ENTRIES = 512
# 单条缓存 TTL（秒）。Epic CDN 通常 immutable，缓存 7 天基本安全
CACHE_TTL_SECONDS = 7 * 24 * 3600

# ============== 内存缓存 ==============
# 简单 dict + 写入锁；按插入顺序淘汰最旧条目（FIFO）
_cache: dict[str, Tuple[float, bytes, str]] = {}
_cache_lock = asyncio.Lock()


def _is_allowed(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


async def _evict_if_needed() -> None:
    """FIFO 淘汰，直到条目数 <= CACHE_MAX_ENTRIES"""
    while len(_cache) > CACHE_MAX_ENTRIES:
        # dict 是有序的，popitem(last=False) 弹出最早插入的
        _cache.popitem(last=False)


@router.get("/api/cover-proxy")
async def cover_proxy(url: str = Query(..., min_length=10, max_length=2048)):
    """代理拉取 Epic CDN 封面图，带内存缓存

    - 仅白名单域名
    - 命中缓存直接返回（极快）
    - 未命中用 httpx 拉取，按 8KB 分块读取，超过 MAX_BYTES 立刻中断
    """
    if not _is_allowed(url):
        raise HTTPException(status_code=400, detail="url not allowed")

    now = time.time()

    # ---------- 查缓存 ----------
    async with _cache_lock:
        cached = _cache.get(url)
        if cached is not None:
            ts, data, ctype = cached
            if now - ts < CACHE_TTL_SECONDS:
                return Response(
                    content=data,
                    media_type=ctype or "image/jpeg",
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "X-Cache": "HIT",
                    },
                )
            # 过期则丢弃
            _cache.pop(url, None)

    # ---------- 拉取 ----------
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 EpicGamesFreeGameHelper/3.0",
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
                # 不带 Referer，避免触发 CDN 的防盗链
            },
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"upstream {resp.status_code}",
                    )
                content_type = resp.headers.get("content-type", "image/jpeg")
                # 只接受图片
                if not content_type.startswith("image/"):
                    raise HTTPException(
                        status_code=502,
                        detail=f"bad content-type: {content_type}",
                    )

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(8192):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise HTTPException(status_code=502, detail="too large")
                    chunks.append(chunk)

        data = b"".join(chunks)
    except httpx.HTTPError as e:
        logger.warning("cover-proxy 拉取失败 url=%s err=%s", url, e)
        raise HTTPException(status_code=502, detail=f"fetch failed: {e.__class__.__name__}")
    except HTTPException:
        raise
    except Exception as e:  # 兜底
        logger.warning("cover-proxy 异常 url=%s err=%s", url, e)
        raise HTTPException(status_code=502, detail="proxy error")

    # ---------- 写缓存 ----------
    async with _cache_lock:
        _cache[url] = (now, data, content_type)
        await _evict_if_needed()

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Cache": "MISS",
        },
    )


@router.get("/api/cover-proxy/stats")
async def cover_proxy_stats():
    """简单状态查询（调试用）"""
    now = time.time()
    valid = sum(1 for ts, _, _ in _cache.values() if now - ts < CACHE_TTL_SECONDS)
    return {
        "entries": len(_cache),
        "valid": valid,
        "max_entries": CACHE_MAX_ENTRIES,
        "ttl_seconds": CACHE_TTL_SECONDS,
    }

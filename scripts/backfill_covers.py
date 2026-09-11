#!/usr/bin/env python3
"""
回填历史游戏的封面图

方法：
1. 从 history.json 提取所有历史游戏的 namespace
2. 对每个 namespace，调用 Epic Catalog Offers API 获取该 namespace 下所有 offer
3. 通过游戏名模糊匹配，找到历史游戏在 offers 中的对应项
4. 提取 cover image (Thumbnail/OfferImageWide) 和 description
5. 将结果写入一个新的 cover_map.json
6. （可选）直接更新 history.json

API：
    GET https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/{ns}/offers
    Authorization: Bearer <client_credentials_token>

兼容的历史游戏最多 100 个 namespace。
"""
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ============= 配置 =============
ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "history.json"
COVER_MAP_FILE = ROOT / "logs" / "cover_map.json"  # 输出映射文件
CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"
TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
CATALOG_BASE = "https://catalog-public-service-prod06.ol.epicgames.com"
BATCH_SIZE = 100
MAX_CONCURRENT = 8  # 并发请求数
MAX_PAGES_PER_NS = 10  # 每个 namespace 最多拉 10 页（1000 offers）


# ============= Token =============
def _get_token() -> str:
    import base64
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    with httpx.Client(timeout=30.0) as session:
        resp = session.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


# ============= 提取历史游戏 namespace =============
def extract_namespaces() -> Dict[str, Dict]:
    """从 history.json 提取所有历史游戏的 (namespace, title) 映射"""
    if not HISTORY_FILE.exists():
        logger.error("找不到历史文件: %s", HISTORY_FILE)
        return {}
    
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    
    ns_map = {}  # (namespace, title) -> game_data
    for rec in records:
        for g in rec.get("games", []):
            ns = g.get("namespace", "")
            title = g.get("title", "")
            if ns and title:
                key = (ns, title)
                if key not in ns_map:
                    ns_map[key] = g
    
    return ns_map


# ============= 拉取 namespace 下的所有 offers =============
async def fetch_namespace_offers(
    session: httpx.AsyncClient,
    token: str,
    ns: str,
) -> Dict[str, dict]:
    """拉取 namespace 下所有 offer，返回 title -> info 映射"""
    url = f"{CATALOG_BASE}/catalog/api/shared/namespace/{ns}/offers"
    offers = {}
    page = 0
    
    while page < MAX_PAGES_PER_NS:
        resp = await session.get(
            url,
            params={"start": page * BATCH_SIZE, "count": BATCH_SIZE},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            logger.warning("namespace %s offers API 返回 %s", ns, resp.status_code)
            break
        
        data = resp.json()
        elements = data.get("elements", [])
        if not elements:
            break
        
        for offer in elements:
            title = offer.get("title", "").strip()
            if not title:
                continue
            
            # 提取封面
            ki = offer.get("keyImages", [])
            thumbnail = _find_cover_image(ki)
            
            # 提取描述
            desc = (offer.get("description", "") or offer.get("shortDescription", "") or "").strip()
            
            offers[title.lower()] = {
                "title": title,
                "thumbnail": thumbnail or "",
                "description": desc,
            }
        
        total = data.get("paging", {}).get("total", 0)
        if page * BATCH_SIZE >= total:
            break
        page += 1
    
    return offers


def _find_cover_image(key_images: list) -> Optional[str]:
    """从 keyImages 中查找最佳封面 URL"""
    for preferred_type in ["Thumbnail", "OfferImageWide", "OfferImageTall", "DieselStoreFrontWide"]:
        for img in key_images:
            if img.get("type") == preferred_type:
                url = img.get("url", "")
                if url:
                    return url
    if key_images:
        return key_images[0].get("url", "")
    return None


# ============= 模糊匹配 =============
def _match_title(
    game_title: str,
    offer_titles: list,
) -> Optional[Tuple[str, dict]]:
    """
    通过游戏名模糊匹配 offers
    
    匹配策略：
    1. 完全匹配（大小写不敏感）
    2. 子串匹配（游戏名是 offer 名的子串，或反之）
    3. 按最长公共子串评分
    """
    game_lower = game_title.lower().strip()
    if not game_lower:
        return None
    
    best_match = None
    best_score = 0
    
    for offer_title in offer_titles:
        offer_lower = offer_title.lower()
        
        # 完全匹配
        if game_lower == offer_lower:
            return (offer_title, None)
        
        # 游戏名是 offer 名的子串（如 "Bouncemasters" match "Bouncemasters Desktop Edition"）
        if game_lower in offer_lower:
            score = len(game_lower)
            if score > best_score:
                best_score = score
                best_match = offer_title
            continue
        
        # offer 名是游戏名的子串
        if offer_lower in game_lower:
            score = len(offer_lower)
            if score > best_score:
                best_score = score
                best_match = offer_title
            continue
        
        # 去常用后缀后匹配
        for suffix in [" desktop edition", " standard edition", " deluxe edition", " bundle", " the game of the year edition"]:
            if game_lower.endswith(suffix):
                if game_lower[: -len(suffix)] == offer_lower:
                    return (offer_title, None)
        
        # 最长公共子串评分（归一化）
        common = _longest_common_substring(game_lower, offer_lower)
        if common:
            score = len(common) / max(len(game_lower), len(offer_lower))
            if score > 0.5 and score > best_score:
                best_score = score
                best_match = offer_title
    
    if best_match:
        return (best_match, None)
    return None


def _longest_common_substring(a: str, b: str) -> str:
    """最长公共子串（简化版，用于模糊匹配评分）"""
    if not a or not b:
        return ""
    m = len(a)
    n = len(b)
    max_len = 0
    end_idx = 0
    # 动态规划 - 但内存只保留两行
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > max_len:
                    max_len = curr[j]
                    end_idx = i
            else:
                curr[j] = 0
        prev, curr = curr, [0] * (n + 1)
    return a[end_idx - max_len: end_idx]


# ============= 回填 =============
async def backfill():
    """主流程"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("开始回填历史游戏封面...")
    
    # 1. 提取 namespace
    ns_map = extract_namespaces()
    if not ns_map:
        logger.error("没有找到历史游戏")
        return
    
    # 按 namespace 分组
    ns_groups = defaultdict(list)  # namespace -> [(title, game_data), ...]
    for (ns, title), game_data in ns_map.items():
        ns_groups[ns].append((title, game_data))
    
    logger.info("找到 %d 个 namespace, %d 个唯一游戏", len(ns_groups), len(ns_map))
    
    # 2. 获取 token
    token = _get_token()
    logger.info("Token 获取成功")
    
    # 3. 并发拉取所有 namespace 的 offers
    cover_map = {}  # title -> {thumbnail, description}
    matched_count = 0
    unmatched_count = 0
    total_api_calls = 0
    
    async with httpx.AsyncClient(timeout=60.0) as session:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def fetch_with_limit(ns):
            nonlocal total_api_calls
            async with semaphore:
                total_api_calls += 1
                return ns, await fetch_namespace_offers(session, token, ns)
        
        tasks = [fetch_with_limit(ns) for ns in ns_groups]
        results = await asyncio.gather(*tasks)
    
    # 4. 按 namespace 匹配
    for ns, offers_data in results:
        game_list = ns_groups.get(ns, [])
        offer_titles = list(offers_data.keys())
        
        for game_title, game_data in game_list:
            result = _match_title(game_title, offer_titles)
            if result:
                matched_title = result[0]
                info = offers_data[matched_title]
                cover_map[game_title] = {
                    "thumbnail": info.get("thumbnail", ""),
                    "description": info.get("description", ""),
                    "matched_official_title": info.get("title", ""),
                }
                matched_count += 1
            else:
                unmatched_count += 1
    
    # 5. 输出结果
    logger.info("匹配完成: %d 匹配, %d 未匹配", matched_count, unmatched_count)
    
    # 保存映射文件
    with open(COVER_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(cover_map, f, ensure_ascii=False, indent=2)
    logger.info("封面映射已保存: %s", COVER_MAP_FILE)
    
    # 显示未匹配的游戏
    if unmatched_count > 0:
        logger.info("未匹配的游戏:")
        all_titles = set(cover_map.keys())
        for (ns, title), _ in ns_map.items():
            if title not in all_titles:
                logger.info("  - %s (ns=%s)", title, ns)
    
    # 显示匹配率
    print(f"\n{'='*60}")
    print(f"  回填结果")
    print(f"{'='*60}")
    print(f"  总游戏数:   {matched_count + unmatched_count}")
    print(f"  匹配成功:   {matched_count} ({matched_count * 100 // (matched_count + unmatched_count)}%)")
    print(f"  未匹配:     {unmatched_count}")
    print(f"  映射文件:   {COVER_MAP_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(backfill())

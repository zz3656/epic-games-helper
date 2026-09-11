#!/usr/bin/env python3
"""
回填历史游戏封面图（v2 增强版）

相比 v1（backfill_covers.py）的改进：
1. 单个 offer endpoint：直接 GET /catalog/api/shared/namespace/{ns}/offers/{offer_id}
   v1 用 namespace 分页 endpoint 在某些 ns 下 total=0（过期 offer 被设为 unsearchable）
   单个 offer endpoint 不受 unsearchable 影响，仍能返回 keyImages。
2. /content/productmapping 端点：对历史中没有 namespace 的游戏，先用 slug 反查 ns，
   然后再走单个 offer endpoint。
3. 容忍下架产品：下架游戏的 catalog API 已无数据，明确标记 unmatched，便于前端兜底。

覆盖策略：
- 现有 cover_map.json 中的匹配保留（matched_official_title 已被人工/算法确认过）
- 只对 v1 未覆盖的或缺失的 game 尝试补全
- 写新文件 cover_map_v2.json，最后覆盖 cover_map.json（保留备份）
"""
import asyncio
import base64
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ============= 配置 =============
ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "history.json"
COVER_MAP_FILE = ROOT / "logs" / "cover_map.json"        # 当前生效
COVER_MAP_V2_FILE = ROOT / "logs" / "cover_map_v2.json"  # 本次输出
BACKUP_FILE = COVER_MAP_FILE.with_suffix(".json.bak")

CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"

# Catalog API（需要 OAuth token）
TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
CATALOG_BASE = "https://catalog-public-service-prod06.ol.epicgames.com"

# Store Content API（productmapping 公开访问，但会被 Cloudflare 限流）
PRODUCT_MAPPING_URL = "https://store-content.ak.epicgames.com/api/content/productmapping"

# ============= OAuth token =============
def _get_token() -> str:
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


# ============= 工具函数 =============
def _slug_from_url(url: str) -> str:
    """从 store URL 提取 slug（去掉语言前缀和 /p/ 前缀）"""
    m = re.search(r"/p/([^/?#]+)", url)
    return m.group(1) if m else ""


def _slug_normalize(slug: str) -> str:
    """标准化 slug 以提高匹配率

    - URL 解码（处理 %xx 转义）
    - 去掉所有 unicode 撇号/引号（' ' ` \u2018 \u2019 \u201c \u201d）
    - 合并连续连字符
    """
    if not slug:
        return slug
    import urllib.parse
    s = urllib.parse.unquote(slug)
    # 去各种 unicode 引号
    s = re.sub(r"[\u2018\u2019\u201c\u201d'`\u2032\u2035]", "", s)
    # 合并连续 -
    s = re.sub(r"-+", "-", s)
    # 去首尾 -
    s = s.strip("-").lower()
    return s


def _pick_thumbnail(key_images: list) -> str:
    """从 keyImages 中挑选最佳封面 URL（与 epic_api._find_cover_image 顺序一致）"""
    preferred = ["Thumbnail", "OfferImageWide", "OfferImageTall", "DieselStoreFrontWide", "VaultClosed"]
    for p in preferred:
        for img in key_images:
            if img.get("type") == p and img.get("url"):
                return img["url"]
    if key_images and key_images[0].get("url"):
        return key_images[0]["url"]
    return ""


# ============= Catalog API 调用 =============
async def fetch_offer_by_id(
    client: httpx.AsyncClient,
    token: str,
    namespace: str,
    offer_id_short: str,
) -> Optional[dict]:
    """用单 offer endpoint 拉取单个游戏的封面/描述

    不受 unsearchable 标记影响，过期下架前/后短期数据都能拿到。
    """
    url = f"{CATALOG_BASE}/catalog/api/shared/namespace/{namespace}/offers/{offer_id_short}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except httpx.HTTPError as e:
        logger.warning("拉取 offer 失败 ns=%s id=%s err=%s", namespace[:8], offer_id_short[:8], e)
        return None


async def fetch_product_mapping(client: httpx.AsyncClient) -> Dict[str, str]:
    """拉取 Epic 商店的 slug → namespace 全量映射

    返回 {slug: namespace}。
    注意：此 endpoint 仅包含在售产品，已下架的游戏不会出现在这里。
    """
    try:
        resp = await client.get(
            PRODUCT_MAPPING_URL,
            params={"locale": "en-US"},  # 用 en-US 避免中文 locale 干扰
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            # mapping 是 {namespace: slug}，反转为 {slug: namespace}
            return {v: k for k, v in data.items() if v and k}
        logger.warning("productmapping 返回 %s", resp.status_code)
        return {}
    except httpx.HTTPError as e:
        logger.warning("productmapping 拉取失败: %s", e)
        return {}


# ============= 历史数据解析 =============
def load_unmatched_games() -> List[dict]:
    """从 history.json 提取所有未在 cover_map 中（或 image_url 为空）的游戏"""
    if not HISTORY_FILE.exists():
        logger.error("找不到 history.json: %s", HISTORY_FILE)
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    # 加载现有 cover_map（保留已有匹配）
    existing_map: Dict[str, dict] = {}
    if COVER_MAP_FILE.exists():
        try:
            with open(COVER_MAP_FILE, "r", encoding="utf-8") as f:
                existing_map = json.load(f)
        except Exception as e:
            logger.warning("读取 cover_map.json 失败: %s", e)

    games = []
    seen = set()
    for rec in records:
        for g in rec.get("games", []):
            title = g.get("title", "")
            if not title or title in seen:
                continue
            seen.add(title)

            has_image = bool(g.get("image_url"))
            in_cover_map = title in existing_map and existing_map[title].get("thumbnail")

            # 已经有封面 + 已在 cover_map 的，跳过（保留 v1 的匹配结果）
            if has_image and in_cover_map:
                continue
            # 有封面但 cover_map 缺失的，也补一次（确保两边一致）
            # 没封面的，必须补

            games.append({
                "title": title,
                "url": g.get("url", ""),
                "namespace": g.get("namespace", ""),
                "offer_id": g.get("offer_id", ""),  # 早期数据可能是纯 offer_id_short
                "offer_id_short": g.get("offer_id_short", ""),
                "image_url": g.get("image_url", ""),
                "end_date": g.get("end_date", ""),
            })

    return games


def extract_offer_id_short(game: dict) -> str:
    """从 game 提取纯 offer_id_short（无 namespace 前缀）"""
    if game.get("offer_id_short"):
        return game["offer_id_short"]
    offer_id = game.get("offer_id", "")
    # 如果是 namespace/short 格式，取后半
    if "/" in offer_id:
        return offer_id.split("/", 1)[1]
    # 否则假定就是纯 short
    return offer_id


# ============= 主流程 =============
async def backfill():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("=== 启动 v2 封面回填 ===")

    # 1. 加载现有 cover_map
    existing_map: Dict[str, dict] = {}
    if COVER_MAP_FILE.exists():
        try:
            with open(COVER_MAP_FILE, "r", encoding="utf-8") as f:
                existing_map = json.load(f)
            logger.info("现有 cover_map 含 %d 个匹配", len(existing_map))
        except Exception as e:
            logger.warning("读取 cover_map 失败: %s", e)

    # 2. 加载未匹配游戏
    games = load_unmatched_games()
    logger.info("需要尝试的游戏: %d 个", len(games))
    if not games:
        logger.info("所有游戏都有封面，无需回填")
        return

    # 3. 获取 token
    logger.info("获取 Catalog OAuth token...")
    token = await asyncio.to_thread(_get_token)
    logger.info("Token OK")

    # 4. 拉取 productmapping（异步，但只一次）
    logger.info("拉取 Epic productmapping...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        mapping = await fetch_product_mapping(client)
    logger.info("productmapping 含 %d 个 slug", len(mapping))

    # 4.1 标准化映射：同时保留原始 + 去前缀版本，以提高匹配率
    mapping_normalized = {}
    for slug, ns in mapping.items():
        norm = _slug_normalize(slug)
        mapping_normalized[norm] = ns
    logger.info("标准化后含 %d 个 slug", len(mapping_normalized))

    # 5. 分类：有 ns vs 无 ns
    has_ns_games = []
    no_ns_games = []
    for g in games:
        if g["namespace"] and extract_offer_id_short(g):
            has_ns_games.append(g)
        else:
            no_ns_games.append(g)
    logger.info("有 namespace: %d | 无 namespace: %d", len(has_ns_games), len(no_ns_games))

    # 6. 并发拉取所有 offer
    new_matches: Dict[str, dict] = {}
    unmatched: List[dict] = []
    semaphore = asyncio.Semaphore(8)

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def try_with_ns(game: dict, ns: str, tag: str = "") -> bool:
            """尝试以指定 ns 拉单个 offer。返回 True 表示成功。"""
            offer_id_short = extract_offer_id_short(game)
            if not offer_id_short:
                return False
            data = await fetch_offer_by_id(client, token, ns, offer_id_short)
            if data:
                thumbnail = _pick_thumbnail(data.get("keyImages", []))
                if thumbnail:
                    new_matches[game["title"]] = {
                        "thumbnail": thumbnail,
                        "description": data.get("description", "") or data.get("shortDescription", ""),
                        "matched_official_title": data.get("title", ""),
                    }
                    logger.info("✓ %s %s → %s", tag, game["title"], thumbnail[:60])
                    return True
            return False

        async def try_one(game: dict) -> None:
            async with semaphore:
                ns = game["namespace"]
                offer_id_short = extract_offer_id_short(game)

                # 策略 0：有 offer_id 但无 ns（fix_history_urls.py 补上的），用 egdata 反查 ns
                if offer_id_short and not ns:
                    try:
                        r = await client.get(
                            f"https://api.egdata.app/offers/{offer_id_short}",
                            timeout=15.0,
                        )
                        if r.status_code == 200:
                            d = r.json()
                            ns_from_eg = d.get("namespace") or ""
                            if ns_from_eg:
                                ns = ns_from_eg
                                game["namespace"] = ns  # 写入用于后续逻辑
                                logger.info("  %s: egdata 反查 ns=%s", game["title"], ns[:12])
                    except httpx.HTTPError as e:
                        logger.warning("egdata 反查 ns 失败: %s", e)

                # 策略 1：原 ns
                if ns and offer_id_short:
                    if await try_with_ns(game, ns, "有 ns"):
                        return
                    # 策略 2：fallback 到 productmapping 里的 ns
                    if game["url"]:
                        raw_slug = _slug_from_url(game["url"])
                        norm_slug = _slug_normalize(raw_slug)
                        mapped_ns = mapping.get(raw_slug) or mapping_normalized.get(norm_slug)
                        if mapped_ns and mapped_ns != ns:
                            if await try_with_ns(game, mapped_ns, "映射 ns"):
                                return

                # 策略 3：从 productmapping 反查 ns（适用于无 ns 的游戏）
                if game["url"]:
                    raw_slug = _slug_from_url(game["url"])
                    norm_slug = _slug_normalize(raw_slug)
                    # 先查原始 slug，再查标准化后 slug
                    mapped_ns = mapping.get(raw_slug) or mapping_normalized.get(norm_slug)
                    if mapped_ns:
                        # 此时游戏没有 offer_id_short（历史里是空的）
                        # 只能拿到 ns，拿不到 offer_id，无法直接查单个 offer
                        # 但好消息：productmapping 中的 ns 是仍在售游戏的 ns，这些游戏
                        # 在 /catalog/api/shared/namespace/{ns}/offers 分页中应该能找到
                        url = f"{CATALOG_BASE}/catalog/api/shared/namespace/{mapped_ns}/offers"
                        try:
                            resp = await client.get(
                                url,
                                params={"start": 0, "count": 200},
                                headers={"Authorization": f"Bearer {token}"},
                                timeout=30.0,
                            )
                            if resp.status_code == 200:
                                d = resp.json()
                                # 在 offers 列表里找标题匹配的游戏
                                for offer in d.get("elements", []):
                                    offer_title = offer.get("title", "").lower()
                                    game_title_lower = game["title"].lower()
                                    if offer_title == game_title_lower or game_title_lower in offer_title:
                                        thumbnail = _pick_thumbnail(offer.get("keyImages", []))
                                        if thumbnail:
                                            new_matches[game["title"]] = {
                                                "thumbnail": thumbnail,
                                                "description": offer.get("description", "") or offer.get("shortDescription", ""),
                                                "matched_official_title": offer.get("title", ""),
                                                "resolved_namespace": mapped_ns,
                                            }
                                            logger.info("✓ productmapping 匹配: %s → %s", game["title"], thumbnail[:60])
                                            return
                        except httpx.HTTPError as e:
                            logger.warning("拉 ns=%s offers 失败: %s", mapped_ns[:8], e)

                # 都失败
                unmatched.append(game)

        # 处理所有需要尝试的游戏
        tasks = [try_one(g) for g in games]
        await asyncio.gather(*tasks)

    logger.info("本轮新增匹配: %d", len(new_matches))
    logger.info("未能匹配: %d", len(unmatched))

    # 7. 合并到 cover_map
    final_map = dict(existing_map)
    final_map.update(new_matches)

    # 8. 写 v2 文件 + 备份 + 覆盖原文件
    with open(COVER_MAP_V2_FILE, "w", encoding="utf-8") as f:
        json.dump(final_map, f, ensure_ascii=False, indent=2)
    logger.info("写入 v2: %s (%d 条)", COVER_MAP_V2_FILE, len(final_map))

    if COVER_MAP_FILE.exists():
        shutil.copy(COVER_MAP_FILE, BACKUP_FILE)
        logger.info("已备份原 cover_map.json → %s", BACKUP_FILE)

    with open(COVER_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(final_map, f, ensure_ascii=False, indent=2)
    logger.info("✓ 已更新 cover_map.json")

    # 9. 输出统计
    print(f"\n{'='*60}")
    print(f"  v2 回填结果")
    print(f"{'='*60}")
    print(f"  原 cover_map 条目: {len(existing_map)}")
    print(f"  本轮新增匹配:     {len(new_matches)}")
    print(f"  最终 cover_map:   {len(final_map)}")
    print(f"  未能匹配（保留渐变封面）: {len(unmatched)}")
    if unmatched:
        print(f"\n  未匹配游戏（前 20）:")
        for g in unmatched[:20]:
            print(f"    - {g['title']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(backfill())

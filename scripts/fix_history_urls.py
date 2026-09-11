#!/usr/bin/env python3
"""
修复历史赠送游戏的"查看详情"URL

背景：history.json 里很多 url 的 slug 是无效的（hex32、megasale-mysterygame-...），
      拼出来的 /p/{slug} 在 Epic 商店会重定向到 not-found 页面。

数据来源（按优先级）：
1. egdata.app 的 /offers/{id}：返回 offerMappings[0].pageSlug 字段（最准确，含 hex 后缀）
2. egdata.app 的 /offers/{id}：productSlug 字段（兜底，但只适用于部分游戏）
3. 手动维护的 MANUAL_SLUGS 字典（针对 egdata 也没有 pageSlug 的早期游戏）
4. egdata.app 的 urlSlug 字段（仅在不是 hex32 / megasale 时使用）

输出：
- 更新 logs/history.json 中每个 game 的 url 字段
- 同时把修复结果写一份到 logs/url_fixes.json（方便审计/回滚）
- 备份原始 history.json 到 history.json.bak3
"""
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ============= 配置 =============
ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "history.json"
BACKUP_FILE = HISTORY_FILE.with_suffix(".json.bak3")
FIXES_FILE = ROOT / "logs" / "url_fixes.json"

EGDATA_BASE = "https://api.egdata.app"
EPIC_LANG = "zh-CN"  # 最终 URL 用 /zh-CN/p/ 前缀

# 手动维护的 pageSlug（针对 egdata.app 也没有 offerMappings 的早期游戏）
# 来源：第三方新闻稿、Epic 商店的 Google 索引、Epic 商店页面截图
# 格式：{ "游戏标题": "page-slug-with-6hex-suffix" }
MANUAL_SLUGS: Dict[str, str] = {
    "Alone With You": "alone-with-you-028a15",
    "Beacon Pines": "beacon-pines-629fc3",
    "Caravan SandWitch": "caravan-sandwitch-05ff58",
    "Rival Stars Horse Racing : Desktop Edition": "rival-stars-horse-racing-desktop-edition",
    "OTXO": "otxo",
    "Foretales": "foretales",
    "Luto": "luto",
    "Echo Generation: Midnight Edition": "echo-generation-midnight-edition",
    "Nova Lands": "nova-lands",
    "River City Girls 2": "river-city-girls-2",
    "I Have No Mouth, and I Must Scream": "i-have-no-mouth-and-i-must-scream",
    "Voidwrought": "voidwrought",
    "Citizen Sleeper": "citizen-sleeper",
    "ROBOBEAT": "robobeat",
    "Arranger: A Role-Puzzling Adventure": "arranger-a-role-puzzling-adventure",
    "Trash Goblin": "trash-goblin",
    "Oddsparks: An Automation Adventure": "oddsparks-an-automation-adventure",
    "DOOMBLADE": "doomblade",
    "Prop Sumo": "prop-sumo",
    "Clone Drone in the Danger Zone": "clone-drone-in-the-danger-zone",
    # mobile 专属免费游戏，完整 pageSlug 需要带 -android-<hex> 后缀
    # egdata 反查不完整，只能从 Epic 商店页面或 Google 索引中拿到
    "Faily Brakes 2": "faily-brakes-2-android-a5e0d1",
    "The Wreck": None,  # 已下架，Epic 找不到
    "Dumb Ways to Die": None,  # 已下架
    # 历史里早先还出现过（2025-10 等周的）但未在 cover_map 里
    # 这里只列能确认的
}

# 旧 catalog data 用 urlSlug 的早期数据中，urlSlug 是 hex32 格式，
# Epic 不接受这种 URL。识别规则：32位纯 hex。
_HEX32 = re.compile(r"^[a-f0-9]{32}$")
# mega sale 神秘游戏占位 slug，活动结束后页面失效
_MEGASALE = re.compile(r"^megasale-mysterygame-")
# 早期用 "urlSlug" 当 slug，但 urlSlug 是 Epic 内部的 "generalaudience" 等不公开字段
_GENERALAUDIENCE = re.compile(r"^[\w-]*generalaudience$")
# em-dash (—) / en-dash (–) 在 url slug 里会出现双转义问题
_EM_DASH = re.compile(r"[—–]")


def _is_invalid_slug(slug: str) -> bool:
    """判断 url slug 是否在 Epic 商店上无效

    以下情况视为无效：
    - 32位纯 hex（Epic catalog 内部 hash，页面不可访问）
    - megasale-mysterygame-*（神秘游戏活动占位，活动结束失效）
    - mysterygame2025-*（早期神秘游戏占位）
    - 以 'generalaudience' 结尾的 urlSlug（Epic 内部字段名，外部不可用）
    - 含撚号 (') / 哑单引号 ('s) 的 slug（Epic 不会保留撚号在 URL 里）
    - 含 em-dash / en-dash 的 slug（需要转义问题不一致）
    """
    if not slug:
        return True
    if _HEX32.match(slug):
        return True  # hex32，Epic 找不到
    if _MEGASALE.match(slug):
        return True  # 神秘游戏占位
    if slug.startswith("mysterygame"):
        return True
    if _GENERALAUDIENCE.match(slug):
        # 如 "cardpocalypsegeneralaudience", "mainegeneralaudience"
        return True
    if "'" in slug or _EM_DASH.search(slug):
        # 如 "evan's-remains"（页面里会跳到 not-found）
        return True
    return False


def _extract_hist_slug(url: str) -> str:
    m = re.search(r"/p/([^/?#]+)", url)
    return m.group(1) if m else ""


def _build_store_url(slug: str) -> str:
    """构造 Epic 商店的 zh-CN 商品页 URL"""
    return f"https://store.epicgames.com/{EPIC_LANG}/p/{slug}"


def _build_egdata_lookup(offer_id: str) -> Optional[dict]:
    """查询 egdata.app 拿 offer 详情（含 productSlug）"""
    try:
        resp = httpx.get(
            f"{EGDATA_BASE}/offers/{offer_id}",
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except httpx.HTTPError as e:
        logger.warning("egdata.app 拉取失败 offer_id=%s err=%s", offer_id[:8], e)
        return None


def _batch_resolve_slugs(slugs: List[str]) -> Dict[str, dict]:
    """批量用 egdata.app /offers/slugs 反查 page slug → offer_id

    返回 {slug: {id, namespace, slug}}
    """
    if not slugs:
        return {}
    try:
        resp = httpx.post(
            f"{EGDATA_BASE}/offers/slugs",
            json={"slugs": list(set(slugs))},
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {d["slug"]: d for d in data if d.get("id")}
        logger.warning("/offers/slugs 返回 %s", resp.status_code)
        return {}
    except httpx.HTTPError as e:
        logger.warning("egdata.app /offers/slugs 调用失败: %s", e)
        return {}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("=== 启动 history.json URL 修复 ===")

    if not HISTORY_FILE.exists():
        logger.error("找不到 history.json: %s", HISTORY_FILE)
        sys.exit(1)

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    logger.info("加载 history.json 共 %d 条记录", len(history))

    # 收集所有游戏（去重）
    all_games: Dict[str, dict] = {}  # title → game data
    for rec in history:
        for g in rec.get("games", []):
            t = g.get("title", "")
            if t and t not in all_games:
                all_games[t] = g
    logger.info("共 %d 个唯一游戏", len(all_games))

    # 分类
    needs_fix: Dict[str, dict] = {}  # 需要修复
    already_valid: List[str] = []
    for title, game in all_games.items():
        hist_slug = _extract_hist_slug(game.get("url", ""))
        if _is_invalid_slug(hist_slug):
            needs_fix[title] = game
        else:
            already_valid.append(title)
    logger.info("需要修复: %d | 已有有效 slug: %d", len(needs_fix), len(already_valid))

    if not needs_fix:
        logger.info("所有 URL 都有效，无需修复")
        return

    # 预处理：对 needs_fix 中无 offer_id 的游戏，用历史 url slug 反查 egdata.app
    # 这能补上 scheduler 早期漏存的 offer_id 情况（如 Evan\\'s Remains）
    needs_slug_resolve = [t for t, g in needs_fix.items() if not g.get("offer_id")]
    if needs_slug_resolve:
        slugs_to_query = []
        slug_normalize_map = {}  # 原 slug → 去擦号后的 slug
        for t in needs_slug_resolve:
            slug = _extract_hist_slug(needs_fix[t].get("url", ""))
            if slug:
                slugs_to_query.append(slug)
                # 去 unicode 擦号后的变体（egdata /offers/slugs 不接受擦号）
                normalized = slug.replace("'", "").replace("'", "").replace("’", "")
                # 合并连续连字符
                import re as _re
                normalized = _re.sub(r"-+", "-", normalized).strip("-")
                if normalized != slug:
                    slugs_to_query.append(normalized)
                    slug_normalize_map[slug] = normalized
        logger.info("批量反查 %d 个无 offer_id 的游戏 url slug...", len(slugs_to_query))
        slug_to_offer = _batch_resolve_slugs(slugs_to_query)
        for t in needs_slug_resolve:
            slug = _extract_hist_slug(needs_fix[t].get("url", ""))
            # 优先用原 slug 反查，失败则用标准化 slug
            offer = slug_to_offer.get(slug) or slug_to_offer.get(slug_normalize_map.get(slug, ""))
            if offer and offer.get("id"):
                # 补上 offer_id 后，后续逻辑能走 offerMappings.pageSlug
                needs_fix[t]["offer_id"] = offer["id"]
                logger.info("  url slug 反查: %s -> offer_id=%s", t, offer["id"][:12])

    # 预处理：对 needs_fix 中“历史 url slug 能反查到但被 _is_invalid_slug 漏过”的
    # 额外用变体反查（如 broken-sword--reforged 去双连字符、dumb-ways-to-die-2-the-games 去后缀）
    # 这一步是针对 _is_invalid_slug 判断不全面但 Epic 也不接受的 slug
    # 示例：broken-sword--reforged（双连字符，Epic 拼接成单连字符）
    # 示例：dumb-ways-to-die-2-the-games（Epic 不喜欢 ": The Games" 后缀）
    extra_variants_map = {
        # title -> [变体 slug 列表]
        "Broken Sword : Reforged": ["broken-sword-reforged"],  # 去双连字符
        "Dumb Ways to Die 2: The Games": ["dumb-ways-to-die-2"],  # 去 : The Games
        "Faily Brakes 2": ["faily-brakes-2-android"],  # mobile 变体
    }
    for title, variants in extra_variants_map.items():
        if title in needs_fix:
            offers = _batch_resolve_slugs(variants)
            for v in variants:
                o = offers.get(v)
                if o and o.get("id"):
                    needs_fix[title]["offer_id"] = o["id"]
                    logger.info("  变体 slug 反查: %s (%s) -> offer_id=%s", title, v, o["id"][:12])
                    break

    # 预处理：对 all_games 中“url slug 看着合法但可能不对”的游戏，主动验证
    # 如 Broken Sword / Dumb Ways to Die 2 / Faily Brakes 2（url slug 看起来有效但 Epic 404）
    # 我们用历史 url slug 反查 egdata.app /offers/slugs，拿 pageSlug 后对比修复
    validate_titles = []
    for title, game in all_games.items():
        if title in already_valid:
            hist_slug = _extract_hist_slug(game.get("url", ""))
            # 启发式检测：slug 看起来“奇异”（有 “generalaudience”、重复、前缀过长、em-dash、双连字符）
            if (
                "generalaudience" in hist_slug
                or hist_slug.count("world-of-warships") > 1
                or "—" in hist_slug
                or "–" in hist_slug
                or hist_slug.endswith("the-games")
                or "--" in hist_slug
            ):
                validate_titles.append(title)

    # 补充：对所有 already_valid 游戏中“url slug 是简单游戏名且无 namespace/offer_id”的验证
    # 这些多是 mobile 专属免费游戏，PC url slug 404，需要换为 mobile pageSlug
    for title, game in all_games.items():
        if title in already_valid and title not in validate_titles:
            hist_slug = _extract_hist_slug(game.get("url", ""))
            ns = game.get("namespace", "")
            oid = game.get("offer_id", "")
            # 启发式：有 url slug 但无 namespace + offer_id，slug 看着像简单游戏名（无 hex 后缀）
            if not ns and not oid and hist_slug:
                # 无 hex 后缀（不是 pageSlug 格式）
                if not _re.search(r"-[a-f0-9]{6,8}$", hist_slug):
                    validate_titles.append(title)

    # 增加：对所有 already_valid 游戏中“url slug 能在 egdata 反查但不一致”的
    # 这种通常是 mobile 专属游戏（url slug 是 PC 版但实际 404）
    for title, game in all_games.items():
        if title in already_valid and title not in validate_titles:
            hist_slug = _extract_hist_slug(game.get("url", ""))
            # 启发式：slug 是游戏名本身（没 hex 后缀）且是历史中近期的免费游戏
            # 这种情况 Epic 通常是 mobile 专属，PC slug 404
            if (
                game.get("end_date", "").startswith("2099")  # 异常数据：end_date 在很远的未来（mobile 专属特征）
            ):
                validate_titles.append(title)
    if validate_titles:
        logger.info("主动验证 %d 个游戏（url slug 看着合法但可能不对）", len(validate_titles))
        for title in validate_titles:
            game = all_games[title]
            hist_slug = _extract_hist_slug(game.get("url", ""))
            # 用历史 url slug 反查 egdata.app /offers/slugs
            offers = _batch_resolve_slugs([hist_slug])
            o = offers.get(hist_slug)
            if not o or not o.get("id"):
                # 变体重试：去双连字符 / 去 ": The Games" 后缀 / 加 -android
                variants = []
                if "--" in hist_slug:
                    variants.append(hist_slug.replace("--", "-"))
                if hist_slug.endswith("-the-games"):
                    variants.append(hist_slug[:-len("-the-games")])
                if "android" not in hist_slug and "iphone" not in hist_slug:
                    variants.append(f"{hist_slug}-android")
                if variants:
                    offers2 = _batch_resolve_slugs(variants)
                    for v in variants:
                        o2 = offers2.get(v)
                        if o2 and o2.get("id"):
                            o = o2
                            break
            if not o or not o.get("id"):
                # 最后一招：手动维护的 MANUAL_SLUGS 兑底
                if title in MANUAL_SLUGS and MANUAL_SLUGS[title]:
                    needs_fix[title] = game
                    already_valid.remove(title)
                    logger.info("  %s: 使用 MANUAL_SLUGS 兑底: %s", title, MANUAL_SLUGS[title])
                    continue
                logger.info("  %s: 反查仍然失败", title)
                continue
            # 拿 offer 详情，取 pageSlug
            data = _build_egdata_lookup(o["id"])
            if not data:
                continue
            new_slug = None
            om = data.get("offerMappings") or []
            if om and len(om) > 0:
                ps = om[0].get("pageSlug")
                if ps:
                    new_slug = ps
            if not new_slug:
                ps = data.get("productSlug")
                if ps:
                    new_slug = ps.split("/")[0]
            if new_slug and new_slug != hist_slug:
                needs_fix[title] = game
                needs_fix[title]["offer_id"] = o["id"]
                already_valid.remove(title)
                logger.info("  发现不一致: %s (%s -> %s)", title, hist_slug[:40], new_slug)

    # 逐个游戏尝试修复
    fixes: Dict[str, dict] = {}  # title → {old_url, new_url, source, new_slug}
    for title, game in needs_fix.items():
        old_url = game.get("url", "")
        old_slug = _extract_hist_slug(old_url)
        offer_id = game.get("offer_id", "")
        new_slug: Optional[str] = None
        source: Optional[str] = None

        # 优先级 1: egdata.app offerMappings[0].pageSlug（最准确，含 hex 后缀）
        if offer_id:
            data = _build_egdata_lookup(offer_id)
            if data:
                om = data.get("offerMappings") or []
                if om and isinstance(om, list) and len(om) > 0:
                    ps = om[0].get("pageSlug")
                    if ps and not _is_invalid_slug(ps):
                        new_slug = ps
                        source = "egdata offerMappings.pageSlug"

        # 优先级 2: egdata.app productSlug
        if not new_slug and offer_id:
            data = data if "data" in dir() else _build_egdata_lookup(offer_id)
            if data:
                ps = data.get("productSlug")
                if ps:
                    slug_only = ps.split("/")[0]
                    if not _is_invalid_slug(slug_only):
                        new_slug = slug_only
                        source = "egdata productSlug"

        # 优先级 3: 手动维护（针对 egdata 也没 pageSlug 的早期游戏）
        if not new_slug and title in MANUAL_SLUGS and MANUAL_SLUGS[title]:
            new_slug = MANUAL_SLUGS[title]
            source = "manual"
            # 如果游戏还有 offer_id，但手册里写的是 hardcoded pageSlug，
            # 主动用 egdata 反查以填充 namespace，供 backfill_covers_v2.py 使用
            if offer_id and not game.get("namespace"):
                # 拿手册 pageSlug 查 offer
                try:
                    offers = _batch_resolve_slugs([new_slug])
                    o = offers.get(new_slug)
                    if o and o.get("namespace"):
                        # 补充 namespace 到 history.json
                        for rec in history:
                            for hg in rec.get("games", []):
                                if hg.get("title") == title and not hg.get("namespace"):
                                    hg["namespace"] = o["namespace"]
                                    logger.info("  为 %s 补充 namespace=%s", title, o["namespace"][:12])
                except Exception:
                    pass

        # 优先级 4: egdata.app urlSlug（兑底，但要确保不是 hex32 / megasale）
        if not new_slug and offer_id:
            data = data if "data" in dir() else _build_egdata_lookup(offer_id)
            if data:
                us = data.get("urlSlug", "")
                if us and not _is_invalid_slug(us):
                    new_slug = us
                    source = "egdata urlSlug"

        if new_slug:
            new_url = _build_store_url(new_slug)
            fixes[title] = {
                "old_url": old_url,
                "old_slug": old_slug,
                "new_url": new_url,
                "new_slug": new_slug,
                "source": source,
            }
            logger.info("✓ %s: %s → %s (%s)", title, old_slug[:40], new_slug, source)
        else:
            logger.info("✗ %s: 无法修复 (offer_id=%s)", title, offer_id[:12])

    logger.info("本轮可修复: %d", len(fixes))

    # 应用修复：更新 history.json
    updated = 0
    for rec in history:
        for g in rec.get("games", []):
            t = g.get("title", "")
            if t in fixes:
                old = g.get("url", "")
                g["url"] = fixes[t]["new_url"]
                if old != fixes[t]["new_url"]:
                    updated += 1

    # 备份原文件
    if HISTORY_FILE.exists():
        shutil.copy(HISTORY_FILE, BACKUP_FILE)
        logger.info("已备份原 history.json → %s", BACKUP_FILE)

    # 写回 history.json
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.info("✓ 已更新 history.json (更新了 %d 个 game 引用)", updated)

    # 写 url_fixes.json
    with open(FIXES_FILE, "w", encoding="utf-8") as f:
        json.dump(fixes, f, ensure_ascii=False, indent=2)
    logger.info("✓ 修复明细写入 %s", FIXES_FILE)

    # 输出统计
    by_source = {}
    for f in fixes.values():
        by_source.setdefault(f["source"], 0)
        by_source[f["source"]] += 1

    print(f"\n{'='*60}")
    print(f"  URL 修复结果")
    print(f"{'='*60}")
    print(f"  历史中唯一游戏数:     {len(all_games)}")
    print(f"  已有有效 slug:        {len(already_valid)}")
    print(f"  本轮已修复:           {len(fixes)}")
    print(f"  未能修复:             {len(needs_fix) - len(fixes)}")
    if by_source:
        print(f"\n  按来源分布:")
        for src, count in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"    {src:25s} {count}")
    still_broken = [t for t in needs_fix if t not in fixes]
    if still_broken:
        print(f"\n  仍未修复（建议手动补充 MANUAL_SLUGS）:")
        for t in still_broken[:20]:
            old_slug = _extract_hist_slug(needs_fix[t].get("url", ""))
            print(f"    - {t} (slug={old_slug[:30]})")
        if len(still_broken) > 20:
            print(f"    ... 还有 {len(still_broken) - 20} 个")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

"""
Epic Games 游戏抓取与领取逻辑（从 claimer.py 拆出，控制单文件行数）

包含：
- fetch_free_games: 从商店首页抓取本周主推的免费游戏
- claim_one: 访问单个游戏页并尝试领取
"""
import asyncio
import logging
import re
from typing import TYPE_CHECKING, List

from playwright.async_api import Page, TimeoutError as PWTimeout

if TYPE_CHECKING:
    from app.claimer import EpicClaimer

logger = logging.getLogger(__name__)


def _is_coming_soon(page_text: str) -> bool:
    """检测页面是否包含“即将推出 / 还未到免费领取时间”"""
    # 明确状态词
    coming_soon_keywords = ["即将推出", "Coming Soon", "Upcoming", "Free on", "免费于", "将在"]
    for kw in coming_soon_keywords:
        if kw in page_text:
            return True
    # 包含日期格式：9月10日 - 9月17日 / 9月10日 23:00 / Sep 10 - Sep 17
    if re.search(r'\d{1,2}月\d{1,2}日\s*[-~]', page_text):
        return True
    return False


async def fetch_free_games(claimer: "EpicClaimer", page: Page) -> List:
    from app.claimer import FreeGame  # runtime import to avoid circular dependency

    """访问商店首页，抓取本周主推免费游戏（首页推荐区）"""
    games = []
    try:
        # 使用首页而非 free-games 页，首页推荐区只显示本周免费游戏
        await page.goto("https://store.epicgames.com/zh-CN", wait_until="domcontentloaded", timeout=60000)
    except PWTimeout:
        logger.error("访问商店首页超时")
        return games

    # 等待首页加载
    try:
        await page.wait_for_selector('[data-testid="featured"]', timeout=30000)
    except PWTimeout:
        logger.warning("未找到 featured 区域，尝试备用选择器")

    # 通过 JS 从首页推荐区提取免费游戏
    games_data = await page.evaluate("""
    () => {
        const results = [];

        // 查找首页推荐轮播中带有“免费”标签的游戏卡片
        const selectors = [
            // data-path 属性指向游戏页的卡片
            '[data-path*="/p/"]',
            // 通用的游戏卡片链接
            'a[href*="/p/"]',
        ];

        const seen = new Set();

        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(a => {
                const href = a.href;
                if (!href || seen.has(href)) return;
                if (!/\\/(p|free-games)\\/[a-z0-9-]+/i.test(href)) return;
                seen.add(href);

                const text = (a.innerText || '').trim();
                const ariaLabel = (a.getAttribute('aria-label') || '').trim();
                const combined = text + ' ' + ariaLabel;

                // 只保留当前可领取的（"免费"且未"即将推出/Coming Soon"）
                const isFree = /免费|Free|免费下载/i.test(combined);
                const isComingSoon = /即将推出|Coming Soon|Upcoming/i.test(combined);

                if (isFree && !isComingSoon) {
                    const title = ariaLabel ||
                        a.querySelector('[class*="Title"]')?.innerText?.trim() ||
                        a.querySelector('[class*="Title"]')?.textContent?.trim() ||
                        text || '';
                    if (title) {
                        results.push({ title, url: href });
                    }
                }
            });
        }

        return results;
    }
    """)

    for item in games_data or []:
        games.append(FreeGame(title=item.get("title", "未知游戏"), url=item.get("url", "")))

    # 去重
    seen = set()
    unique = []
    for g in games:
        if g.url in seen:
            continue
        seen.add(g.url)
        unique.append(g)
    return unique


async def claim_one(claimer: "EpicClaimer", page: Page, url: str) -> tuple:
    """访问游戏页并尝试领取。返回 (status, message)"""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except PWTimeout:
        return ("failed", "页面访问超时")

    # 等待按钮出现
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass

    # 检查是否已拥有
    page_text = await claimer._get_page_text(page)
    for owned in claimer.ALREADY_OWNED_TEXT:
        if owned in page_text:
            return ("already_claimed", f"已拥有: {owned}")

    # 检查是否未开始（即将推出）
    if _is_coming_soon(page_text):
        return ("not_started", "游戏还未免费，暂不领取")

    # 点击获取按钮
    clicked = await claimer._click_first_available(page, claimer.GET_BUTTON_SELECTORS)
    if not clicked:
        return ("not_free", "未找到'获取'按钮，可能不是免费游戏或已结束")

    # 等待弹窗/二次确认
    await asyncio.sleep(1.5)
    # 点击下单/接受
    await claimer._click_first_available(page, claimer.PLACE_ORDER_BUTTON_SELECTORS)

    # 等待成功提示（Epic 通常会显示"已加入库"或返回 store）
    try:
        await page.wait_for_function(
            """() => {
                const text = document.body.innerText || '';
                return /已添加|已加入库|Added to Library|Owned|已拥有/.test(text);
            }""",
            timeout=20000,
        )
        return ("claimed", "已成功领取")
    except PWTimeout:
        # 兜底：再等几秒
        await asyncio.sleep(3)
        text = await claimer._get_page_text(page)
        if any(owned in text for owned in claimer.ALREADY_OWNED_TEXT):
            return ("already_claimed", "领取后已拥有")
        return ("failed", "未检测到成功提示")

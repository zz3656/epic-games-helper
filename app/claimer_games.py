"""
Epic Games 游戏抓取与领取逻辑（从 claimer.py 拆出，控制单文件行数）

包含：
- fetch_free_games: 从商店页抓取所有可领取的免费游戏
- claim_one: 访问单个游戏页并尝试领取
"""
import asyncio
import logging
from typing import TYPE_CHECKING, List

from playwright.async_api import Page, TimeoutError as PWTimeout

if TYPE_CHECKING:
    from app.claimer import EpicClaimer

logger = logging.getLogger(__name__)


async def fetch_free_games(claimer: "EpicClaimer", page: Page) -> List:
    from app.claimer import FreeGame  # runtime import to avoid circular dependency

    """访问免费游戏页，解析当前可领取的游戏"""
    games = []
    try:
        await page.goto(claimer.STORE_URL, wait_until="domcontentloaded", timeout=60000)
    except PWTimeout:
        logger.error("访问商店页超时")
        return games

    # 等待游戏卡片加载
    try:
        await page.wait_for_selector(
            'a[href*="/free-games/"], a[href*="/p/"]', timeout=30000
        )
    except PWTimeout:
        logger.warning("未找到免费游戏卡片")

    # 通过 JS 抓取所有可领取的游戏链接
    hrefs = await page.evaluate("""
    () => {
        const results = [];
        const links = document.querySelectorAll('a[href*="/p/"], a[href*="/free-games/"]');
        const seen = new Set();
        for (const a of links) {
            const href = a.href;
            if (seen.has(href)) continue;
            seen.add(href);
            if (/\\/(p|free-games)\\/[a-z0-9-]+/i.test(href)) {
                const title = (
                    a.getAttribute('aria-label') ||
                    a.querySelector('span')?.innerText ||
                    a.innerText ||
                    ''
                ).trim();
                if (title) results.push({title, url: href});
            }
        }
        return results;
    }
    """)
    seen = set()
    for item in hrefs or []:
        url = item.get("url", "")
        if url in seen:
            continue
        seen.add(url)
        games.append(FreeGame(title=item.get("title", "未知游戏"), url=url))
    return games


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

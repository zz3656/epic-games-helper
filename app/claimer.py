"""
Epic Games 自动领取核心逻辑（主入口、登录、工具方法）

游戏抓取与领取逻辑见 claimer_games.py（拆分以控制行数）

隐私设计要点：
- 账号密码仅以函数参数形式传入
- 领取流程结束后立即从内存中清除引用
- 不写入任何持久化存储
- 不打印/记录完整密码
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, List, Optional

from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page,
    TimeoutError as PWTimeout,
)

from app.claimer_games import fetch_free_games, claim_one

logger = logging.getLogger(__name__)


@dataclass
class FreeGame:
    title: str
    url: str
    status: str = "pending"          # pending / claimed / failed / already_claimed / not_free
    message: str = ""


@dataclass
class ClaimResult:
    success: bool
    username: str                    # 脱敏后的用户名（仅用于日志展示）
    games: List[FreeGame] = field(default_factory=list)
    error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    screenshot_path: Optional[str] = None


async def _emit(callback, step: str, status: str):
    """异步调用进度回调"""
    try:
        coro = callback(step, status)
        if asyncio.iscoroutine(coro):
            await coro
    except Exception:
        pass  # 进度回调失败不应影响主流程


def _mask_username(username: str) -> str:
    """用户名脱敏：保留首末字符，中间替换为 *"""
    if not username or len(username) <= 2:
        return "*" * len(username) if username else ""
    return username[0] + "*" * (len(username) - 2) + username[-1]


def _mask_password(_: str) -> str:
    """密码永远脱敏"""
    return "******"


class EpicClaimer:
    """
    Epic Games 领取器

    用法：
        async with EpicClaimer(headless=True) as claimer:
            result = await claimer.run(username, password)
    """

    # 登录页面选择器（Epic 经常改版，需以宽松选择器 + 多重 fallback）
    LOGIN_IFRAME_SELECTOR = "iframe[name^='account']"
    EMAIL_INPUT_SELECTORS = [
        'input#email',
        'input[name="email"]',
        'input[type="email"]',
        'input[autocomplete="username"]',
    ]
    PASSWORD_INPUT_SELECTORS = [
        'input#password',
        'input[name="password"]',
        'input[type="password"]',
        'input[autocomplete="current-password"]',
    ]
    SUBMIT_BUTTON_SELECTORS = [
        'button#login',
        'button[type="submit"]',
        'button:has-text("登录")',
        'button:has-text("Log In")',
        'button:has-text("Sign In")',
    ]

    # 领取按钮选择器
    GET_BUTTON_SELECTORS = [
        'button[data-testid="purchase-cta-button"]',
        'button:has-text("获取")',
        'button:has-text("免费获取")',
        'button:has-text("Get")',
        'button:has-text("Free")',
    ]
    PLACE_ORDER_BUTTON_SELECTORS = [
        'button:has-text("下单")',
        'button:has-text("Place Order")',
        'button:has-text("接受")',
        'button:has-text("Accept")',
        'button:has-text("I Agree")',
    ]
    ALREADY_OWNED_TEXT = ["已在库中", "Owned", "已拥有", "In Library"]

    def __init__(self, headless: bool = True, screenshot_dir: str = "/app/screenshots",
                 on_progress: Optional[Callable] = None):
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self._playwright = None
        self._browser: Optional[Browser] = None
        # 进度回调: callable(claim_id, step, status)
        self._on_progress = on_progress
        # 关键：把账号密码以局部变量保存，with 块结束时立即清空
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    def _emit_progress(self, step: str, status: str):
        """发出进度事件（异步，不阻塞主流程）"""
        if self._on_progress:
            try:
                coro = self._on_progress(step, status)
                if asyncio.iscoroutine(coro):
                    asyncio.create_task(coro)
            except Exception:
                pass  # 进度回调失败不应影响主流程

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        logger.info("Browser launched (headless=%s)", self.headless)

    async def close(self):
        # 关键：清理敏感数据
        self._username = None
        self._password = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning("Error stopping playwright: %s", e)

    async def run(self, username: str, password: str,
                  on_progress: Optional[Callable] = None) -> ClaimResult:
        """主入口：登录 -> 抓取免费游戏 -> 逐个领取
        
        Args:
            username: 账号
            password: 密码
            on_progress: 进度回调 (step, status) -> None/Coroutine
        """
        started = datetime.now().isoformat(timespec="seconds")
        result = ClaimResult(
            success=False,
            username=_mask_username(username),
            started_at=started,
        )

        # 仅在内存中保存
        self._username = username
        self._password = password
        # 优先使用传入的回调
        progress_fn = on_progress or self._on_progress

        if not username or not password:
            result.error = "账号或密码不能为空"
            return result

        context: Optional[BrowserContext] = None
        try:
            if progress_fn:
                await _emit(progress_fn, "正在启动浏览器…", "active")

            context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
            )
            page = await context.new_page()

            # 1) 登录
            if progress_fn:
                await _emit(progress_fn, "正在登录…", "active")
            login_ok = await self._login(page)
            if not login_ok:
                result.error = "登录失败：可能账号密码错误，或 Epic 登录页结构变化"
                result.screenshot_path = await self._save_screenshot(page, "login_failed")
                if progress_fn:
                    await _emit(progress_fn, "登录失败", "done")
                return result
            if progress_fn:
                await _emit(progress_fn, "登录成功", "done")
            logger.info("[%s] 登录成功", result.username)

            # 2) 抓取免费游戏列表
            if progress_fn:
                await _emit(progress_fn, "正在获取免费游戏列表…", "active")
            games = await fetch_free_games(self, page)
            if progress_fn:
                await _emit(progress_fn, f"发现 {len(games)} 款免费游戏", "done")
            logger.info("[%s] 发现 %d 款免费游戏", result.username, len(games))
            result.games = games

            if not games:
                result.success = True  # 流程成功，只是没游戏
                result.error = "本周暂无免费游戏"
                return result

            # 3) 逐个领取
            for i, game in enumerate(games, 1):
                if progress_fn:
                    await _emit(progress_fn, f"正在领取 [{i}/{len(games)}]: {game.title}", "active")
                logger.info("[%s] 正在领取: %s", result.username, game.title)
                game.status, game.message = await claim_one(self, page, game.url)
                status_icon = "✅" if game.status in ("claimed", "already_claimed") else "❌"
                if progress_fn:
                    await _emit(
                        progress_fn,
                        f"{status_icon} {game.title}: {game.message}",
                        "done",
                    )
                logger.info(
                    "[%s] %s -> %s (%s)",
                    result.username, game.title, game.status, game.message,
                )

            result.success = all(
                g.status in ("claimed", "already_claimed") for g in games
            )

        except Exception as e:
            logger.exception("领取流程异常")
            result.error = f"异常: {type(e).__name__}: {e}"
            if context:
                page = context.pages[0] if context.pages else None
                if page:
                    result.screenshot_path = await self._save_screenshot(page, "exception")
            if progress_fn:
                await _emit(progress_fn, f"异常: {e}", "done")
        finally:
            # 关键：关闭 context，确保 cookie/会话也被丢弃
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            # 清空敏感字段
            self._username = None
            self._password = None

        result.finished_at = datetime.now().isoformat(timespec="seconds")
        return result

    # ============== 登录 ==============
    async def _login(self, page: Page) -> bool:
        """执行登录流程"""
        try:
            await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        except PWTimeout:
            logger.error("访问登录页超时")
            return False

        # Epic 登录页通常会把表单放在 iframe 里，先尝试切到 iframe
        iframe = None
        try:
            iframe = await page.wait_for_selector(
                self.LOGIN_IFRAME_SELECTOR, timeout=5000, state="attached"
            )
        except PWTimeout:
            logger.info("未发现登录 iframe，尝试直接在主页面定位输入框")

        target: Page = page
        if iframe:
            frame = await iframe.content_frame()
            if frame:
                target = frame
                logger.info("已切换到登录 iframe")

        # 输入邮箱
        email_ok = await self._fill_first_available(
            target, self.EMAIL_INPUT_SELECTORS, self._username
        )
        if not email_ok:
            logger.error("找不到邮箱输入框")
            return False

        # 输入密码
        pwd_ok = await self._fill_first_available(
            target, self.PASSWORD_INPUT_SELECTORS, self._password
        )
        if not pwd_ok:
            logger.error("找不到密码输入框")
            return False

        # 点击登录
        submit_ok = await self._click_first_available(target, self.SUBMIT_BUTTON_SELECTORS)
        if not submit_ok:
            logger.error("找不到登录按钮")
            return False

        # 等待登录完成：跳转到 store 或账号中心
        try:
            await page.wait_for_url(
                lambda url: ("store.epicgames.com" in url or "epicgames.com/account" in url),
                timeout=30000,
            )
            return True
        except PWTimeout:
            # 检查是否出现账号菜单（某些场景下 URL 不变）
            try:
                await page.wait_for_selector(
                    '[data-testid="user-accountexposed"]', timeout=8000
                )
                return True
            except PWTimeout:
                # 检查是否有错误提示
                err = await self._get_text_safe(
                    target,
                    '[role="alert"], .error, [data-testid="error"], '
                    '[data-testid="login-error"], [class*="ErrorMessage"], '
                    '[class*="error"]',
                )
                if err:
                    logger.error("登录错误提示: %s", err)
                    return False
                # 未检测到成功迹象，视为登录失败
                logger.error("登录超时，未跳转到首页且未检测到账号菜单")
                return False

    # ============== 工具方法 ==============
    async def _fill_first_available(self, page: Page, selectors: List[str], value: str) -> bool:
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.fill(value)
                    return True
            except Exception:
                continue
        return False

    async def _click_first_available(self, page: Page, selectors: List[str]) -> bool:
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=2500, state="visible")
                if el:
                    await el.click()
                    return True
            except Exception:
                continue
        return False

    async def _get_text_safe(self, page: Page, selector: str) -> str:
        try:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text() or "").strip()
        except Exception:
            pass
        return ""

    async def _get_page_text(self, page: Page) -> str:
        try:
            return (await page.evaluate("() => document.body.innerText")) or ""
        except Exception:
            return ""

    async def _save_screenshot(self, page: Page, tag: str) -> Optional[str]:
        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.screenshot_dir, f"{tag}_{ts}.png")
            await page.screenshot(path=path, full_page=False)
            return path
        except Exception as e:
            logger.warning("截图失败: %s", e)
            return None

    # URL 常量
    @property
    def STORE_URL(self):
        return "https://store.epicgames.com/zh-CN/free-games"

    @property
    def LOGIN_URL(self):
        return "https://www.epicgames.com/id/login"
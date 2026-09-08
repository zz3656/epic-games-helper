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
from app.claimer_login import LoginHandler, LoginStatus

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
    login_status: str = ""           # LoginStatus 之一（SUCCESS / INVALID_CREDENTIALS / 等）


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

    # 领取按钮选择器
    GET_BUTTON_SELECTORS = [
        'button[data-testid="purchase-cta-button"]',
        'button:has-text("获取")',
        'button:has-text("免费获取")',
        'button:has-text("Get")',
        'button:has-text("Free")',
        'button:has-text("免费下载")',
        'button[class*="purchase"]',
        'button[aria-label*="Get"]',
        'button[aria-label*="Free"]',
        'a[data-testid="purchase-cta-button"]',
    ]
    PLACE_ORDER_BUTTON_SELECTORS = [
        'button:has-text("下单")',
        'button:has-text("Place Order")',
        'button:has-text("接受")',
        'button:has-text("Accept")',
        'button:has-text("I Agree")',
        'button[class*="confirm"]',
        'button[aria-label*="Place Order"]',
        'button[aria-label*="Accept"]',
    ]
    ALREADY_OWNED_TEXT = ["已在库中", "Owned", "已拥有", "In Library", "已在库"]

    # 不是免费的标识（游戏过期、需购买等）
    NOT_FREE_TEXTS = [
        "Purchase", "Buy Now", "立即购买", "价格", "$", "€", "¥",
        "Unavailable", "不在提供", "不可领取",
    ]

    def __init__(self, headless: bool = True, screenshot_dir: str = "/app/screenshots",
                 on_progress: Optional[Callable] = None):
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self._playwright = None
        self._browser: Optional[Browser] = None
        # 进度回调: callable(claim_id, step, status)
        self._on_progress = on_progress
        # 登录处理器（拆分到 claimer_login.py）
        self._login_handler = LoginHandler(self)
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
                  on_progress: Optional[Callable] = None,
                  verification_code: Optional[str] = None) -> ClaimResult:
        """主入口：登录 -> 抓取免费游戏 -> 逐个领取
        
        Args:
            username: 账号
            password: 密码
            on_progress: 进度回调 (step, status) -> None/Coroutine
            verification_code: 邮箱验证码（如果已知）
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

            # 1) 登录（关键步骤：登录失败则终止后续领取）
            if progress_fn:
                await _emit(progress_fn, "🔐 正在登录 Epic…", "active")
            login_result = await self._login_handler.login(page, verification_code)

            if login_result.status == LoginStatus.NEEDS_VERIFICATION:
                result.error = "需要邮箱验证：Epic 要求邮箱验证码。请检查邮箱获取验证码后重新提交，或在本地手动登录一次以信任本设备"
                result.screenshot_path = login_result.screenshot_tag and await self._save_screenshot(
                    page, login_result.screenshot_tag
                )
                result.login_status = LoginStatus.NEEDS_VERIFICATION
                if progress_fn:
                    await _emit(progress_fn, "🔐 需要邮箱验证", "done")
                return result

            if login_result.status != LoginStatus.SUCCESS:
                # 登录失败 -> 硬终止，后续步骤不执行
                result.error = login_result.reason
                result.screenshot_path = login_result.screenshot_tag and await self._save_screenshot(
                    page, login_result.screenshot_tag
                )
                result.login_status = login_result.status
                if progress_fn:
                    await _emit(progress_fn, f"🔒 登录失败：{login_result.reason}", "done")
                logger.error("[%s] 登录失败: %s，终止后续流程", result.username, login_result.reason)
                return result

            if progress_fn:
                await _emit(progress_fn, "✅ 登录成功", "done")
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
    # 二步验证输入框选择器（Epic 会要求邮箱验证码）
    VERIFICATION_CODE_SELECTORS = [
        'input#code',
        'input[name="code"]',
        'input[name="verificationCode"]',
        'input[id*="code"]',
        'input[autocomplete="one-time-code"]',
        'input[type="text"][name*="otp"]',
        'input[type="text"][inputmode="numeric"]',
    ]
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
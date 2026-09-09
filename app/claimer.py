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
        from app.claimer_browser import build_launch_kwargs
        self._playwright = await async_playwright().start()
        launch_kwargs = build_launch_kwargs(self.headless)
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        logger.info("Browser launched (headless=%s, mode=%s)", self.headless, "new" if self.headless else "visible")

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

            # 真实化浏览器指纹：使用最新的 Chrome 141 + Windows 11 UA
            # 避免使用 macOS UA 与服务器 Linux 环境不一致
            # 关键：UA、Platform、sec-ch-* 头需要一致
            context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                screen={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/141.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                    "sec-ch-ua": '"Chromium";v="141", "Not_A Brand";v="24", "Google Chrome";v="141"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                },
                permissions=["geolocation"],
                color_scheme="light",
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
            )
            # 注入 stealth 脚本：避免被 hCaptcha/Epic 检测为机器人
            # 基于 puppeteer-extra-plugin-stealth 思路，实现以下反检测项：
            # 1. navigator.webdriver 隐藏
            # 2. chrome runtime 伪装
            # 3. playwright 全局变量清理
            # 4. plugins/mimeTypes 伪装
            # 5. languages 伪装
            # 6. permissions.query 伪装
            # 7. WebGL vendor/renderer 伪装
            # 8. iframe contentWindow 伪装
            # 9. Notification 伪装
            # 10. hairline / 触控点伪装
            # 11. CDP 检测的 Runtime.enable 痕迹
            # 12. 启用 console.log 避免被沙箱检测
            await context.add_init_script("""
                (function() {
                    'use strict';
                    const _origQuery = window.navigator.permissions && window.navigator.permissions.query;

                    // 1. navigator.webdriver
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });

                    // 2. chrome runtime
                    if (!window.chrome) {
                        window.chrome = { runtime: {}, loadTimes: () => ({}), csi: () => ({}), app: { isInstalled: false } };
                    } else {
                        if (!window.chrome.runtime) window.chrome.runtime = {};
                        if (!window.chrome.loadTimes) window.chrome.loadTimes = () => ({});
                        if (!window.chrome.csi) window.chrome.csi = () => ({});
                    }

                    // 3. 删除 Playwright 注入的全局变量
                    try { delete window.__playwright; } catch (e) {}
                    try { delete window.__pwInitScripts; } catch (e) {}
                    try { delete window.__pwScripts; } catch (e) {}
                    try { delete window.__pw_manual__; } catch (e) {}

                    // 4. plugins / mimeTypes
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            const arr = [
                                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                            ];
                            arr.item = (i) => arr[i];
                            arr.namedItem = (n) => arr.find(p => p.name === n);
                            arr.refresh = () => {};
                            return arr;
                        },
                        configurable: true,
                    });
                    Object.defineProperty(navigator, 'mimeTypes', {
                        get: () => {
                            const arr = [
                                { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: { name: 'Chrome PDF Plugin' } },
                            ];
                            arr.item = (i) => arr[i];
                            arr.namedItem = (n) => arr.find(p => p.type === n);
                            return arr;
                        },
                        configurable: true,
                    });

                    // 5. languages
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'], configurable: true });
                    Object.defineProperty(navigator, 'language', { get: () => 'zh-CN', configurable: true });

                    // 6. permissions.query
                    if (_origQuery) {
                        window.navigator.permissions.query = (parameters) =>
                            parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            _origQuery(parameters);
                    }

                    // 7. WebGL vendor/renderer
                    const modifyParameter = (ctx) => {
                        const origGetParameter = ctx.getParameter;
                        ctx.getParameter = function(parameter) {
                            if (parameter === 37445) return 'Intel Inc.';
                            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                            if (parameter === 37447) return 'WebKit';
                            return origGetParameter.call(this, parameter);
                        };
                        const origGetExtension = ctx.getExtension;
                        ctx.getExtension = function(name) { return null; };
                    };
                    try { modifyParameter(WebGLRenderingContext.prototype); } catch (e) {}
                    try { modifyParameter(WebGL2RenderingContext.prototype); } catch (e) {}

                    // 8. iframe contentWindow
                    try {
                        const elementDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
                        Object.defineProperty(HTMLDivElement.prototype, 'offsetHeight', { ...elementDescriptor, get: function() { return 1; } });
                    } catch (e) {}

                    // 9. Notification
                    try {
                        Object.defineProperty(Notification, 'permission', { get: () => 'default', configurable: true });
                    } catch (e) {}

                    // 10. hairline / 触控点
                    try {
                        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0, configurable: true });
                    } catch (e) {}

                    // 11. 隐藏 CDP/Runtime.evaluate 痕迹
                    try {
                        const origError = console.error;
                        console.error = function(...args) {
                            const s = args.join(' ');
                            if (s.includes('Protocol Error') || s.includes('Session closed')) return;
                            return origError.apply(this, args);
                        };
                    } catch (e) {}

                    // 12. 添加 Connection API
                    try {
                        Object.defineProperty(navigator, 'connection', {
                            get: () => ({
                                effectiveType: '4g', rtt: 50, downlink: 10, saveData: false,
                            }),
                            configurable: true,
                        });
                    } catch (e) {}

                    // 13. 隐藏自动化特征 - 误判检测
                    try {
                        const origToString = Function.prototype.toString;
                        Function.prototype.toString = function() {
                            if (this === navigator.permissions.query) {
                                return 'function query() { [native code] }';
                            }
                            return origToString.call(this);
                        };
                    } catch (e) {}

                    // 14. 隐藏 iframe 中可能的 hCaptcha 检测
                    try {
                        if (window.top !== window.self) {
                            Object.defineProperty(window, 'top', { get: () => window.self });
                        }
                    } catch (e) {}

                    // 15. 伪装 navigator.platform（与 UA 一致）
                    try {
                        Object.defineProperty(navigator, 'platform', { get: () => 'Win32', configurable: true });
                        Object.defineProperty(navigator, 'oscpu', { get: () => 'Windows NT 10.0; Win64; x64', configurable: true });
                    } catch (e) {}

                    // 16. 伪装 hardwareConcurrency / deviceMemory
                    try {
                        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
                        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });
                    } catch (e) {}

                    // 17. 隐藏 headless 痕迹
                    try {
                        // 解决 hCaptcha 检查 navigator.webdriver 以外的 API
                        if (window.outerWidth === 0 && window.outerHeight === 0) {
                            Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
                            Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight });
                        }
                    } catch (e) {}

                    // 18. 修复 Permissions API 签名
                    try {
                        const origToString = Function.prototype.toString;
                        const _funcToString = origToString.bind(Function.prototype.toString);
                        const _originalPermissionsQuery = navigator.permissions.__proto__.query;
                        navigator.permissions.__proto__.query = function(...args) {
                            const result = _originalPermissionsQuery.apply(this, args);
                            // 返回原始 Promise 不要被检测
                            return result;
                        };
                        navigator.permissions.__proto__.query.toString = function() {
                            return 'function query() { [native code] }';
                        };
                    } catch (e) {}
                })();
            """)
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
        # 先尝试 CSS 选择器
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=2500, state="visible")
                if el:
                    await el.fill(value)
                    logger.info("填充字段成功: %s", sel)
                    return True
            except Exception:
                continue
        # 备选：用 JS 按语义查找（仅针对邮箱/密码）
        if value and isinstance(value, str) and "@" in value and len(value) > 5:
            # 邮箱：使用 type=email 或 autocomplete=username
            try:
                el = await page.evaluate_handle("""
                () => document.querySelector('input[type="email"], input[autocomplete="username"], input[id*="email" i], input[name*="email" i]')
                """)
                if el:
                    await el.fill(value)
                    logger.info("使用语义选择器填充邮箱")
                    return True
            except Exception:
                pass
        else:
            # 密码：使用 type=password 且不是 confirm
            try:
                el = await page.evaluate_handle("""
                () => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    // 选择第一个 password（不是确认密码）
                    return inputs[0];
                }
                """)
                if el:
                    await el.fill(value)
                    logger.info("使用语义选择器填充密码")
                    return True
            except Exception:
                pass
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
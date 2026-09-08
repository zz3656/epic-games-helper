"""
Epic Games 登录流程（从 claimer.py 拆出，控制单文件行数）

包含：
- login: 执行登录流程，返回精细化的失败原因
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)


# 登录结果分类（精细化失败原因）
class LoginStatus:
    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"   # 账号或密码错误
    ACCOUNT_LOCKED = "account_locked"             # 账号被锁
    RATE_LIMIT = "rate_limit"                     # 频繁登录被限
    CAPTCHA_REQUIRED = "captcha_required"         # 需要图形验证码
    NETWORK_ERROR = "network_error"               # 网络问题
    PAGE_CHANGED = "page_changed"                 # Epic 登录页结构变化
    NEEDS_VERIFICATION = "needs_verification"     # 需要邮箱/二步验证
    UNKNOWN = "unknown"                           # 未知错误


@dataclass
class LoginResult:
    """登录结果"""
    status: str            # LoginStatus 之一
    reason: str            # 详细原因描述（中文）
    screenshot_tag: str    # 截图标签


class LoginHandler:
    """封装 Epic 登录流程"""

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

    VERIFICATION_CODE_SELECTORS = [
        'input#code',
        'input[name="code"]',
        'input[name="verificationCode"]',
        'input[id*="code"]',
        'input[autocomplete="one-time-code"]',
        'input[type="text"][name*="otp"]',
        'input[type="text"][inputmode="numeric"]',
    ]
    VERIFICATION_PROMPT_TEXTS = [
        "Enter the code we sent to",
        "Enter the security code",
        "We sent a code to",
        "Verify it's you",
        "Check your email",
        "输入发送到您邮箱中的验证码",
        "请输入验证码",
        "验证您的身份",
        "两步验证",
        "邮箱验证",
    ]

    # 精细化错误关键词分类
    ERROR_PATTERNS = {
        # 账号/密码错误
        LoginStatus.INVALID_CREDENTIALS: [
            # 中文
            "密码错误", "密码不正确", "密码无效", "密码有误",
            "账号不存在", "账号无效", "账号错误",
            "用户名或密码", "邮箱或密码", "邮箱或密码错误",
            "邮箱和密码", "邮件地址或密码", "电子邮件地址或密码不正确",
            "密码与账号不匹配", "账号或密码有误",
            # 英文（Epic 实际使用）
            "invalid credentials", "invalid password", "invalid email",
            "incorrect password", "incorrect email", "incorrect username",
            "invalid login", "invalid sign in", "invalid signin",
            "wrong password", "wrong email", "wrong credentials",
            "do not match", "doesn't match", "not recognized",
            "your email or password", "email or password is incorrect",
            "your password is incorrect", "your email is incorrect",
            "sign in failed", "login failed", "登录失败",
            "credentials", "incorrect email or password",
            "email address or password is incorrect",
            "please check your email and password",
        ],
        # 账号被锁定
        LoginStatus.ACCOUNT_LOCKED: [
            "账号已被锁定", "账号已锁定", "账号被禁用", "账号已禁用",
            "账户锁定", "账户已冻结", "账户被禁用",
            "account locked", "account disabled", "account suspended",
            "locked out", "too many failed", "已暂停", "永久禁用",
            "your account has been", "account is locked",
        ],
        # 频率限制
        LoginStatus.RATE_LIMIT: [
            "尝试次数过多", "频繁登录", "操作过于频繁", "请稍后再试",
            "too many attempts", "too many requests", "rate limit",
            "try again later", "too many login", "暂时无法",
            "slow down", "请过几分钟", "rate limited",
            "throttled", "try again in",
        ],
        # 图形验证码
        LoginStatus.CAPTCHA_REQUIRED: [
            "captcha", "验证码", "hCaptcha", "hcaptcha", "recaptcha",
            "reCAPTCHA", "are you human", "请完成验证", "human verification",
        ],
        # 验证提示
        LoginStatus.NEEDS_VERIFICATION: [
            "Enter the code", "Verify", "Check your email",
            "Two-factor", "两步验证", "邮箱验证",
        ],
    }

    def __init__(self, parent):
        self.parent = parent

    async def _try_solve_hcaptcha(self, page, target) -> bool:
        """尝试自动点击 hCaptcha checkbox

        hCaptcha 包含嵌套 iframe，需先切到 host frame 再切到 challenge frame。
        简单 checkbox 点击可能触发图片挑战 — 那需要图像识别，无法自动完成。
        返回 True 表示成功点击，False 表示失败。
        """
        try:
            iframe_selectors = [
                'iframe[src*="hcaptcha.com"][src*="checkbox"]',
                'iframe[src*="hcaptcha.com"]',
            ]
            for iframe_sel in iframe_selectors:
                iframe_handle = await page.query_selector(iframe_sel)
                if not iframe_handle:
                    continue
                frame = await iframe_handle.content_frame()
                if not frame:
                    continue
                checkbox_selectors = [
                    '#checkbox',
                    '.checkmark',
                    '[id*="checkbox"]',
                    'div[role="checkbox"]',
                ]
                for cb_sel in checkbox_selectors:
                    try:
                        cb = await frame.query_selector(cb_sel)
                        if cb:
                            await cb.click()
                            logger.info("hCaptcha checkbox 已点击: %s", cb_sel)
                            return True
                    except Exception:
                        continue
            return False
        except Exception as e:
            logger.warning("自动点击 hCaptcha 失败: %s", e)
            return False

    def _classify_error(self, page_text: str, current_url: str) -> LoginResult:
        """根据页面文本和 URL 分类失败原因"""
        text_lower = page_text.lower()

        # 按优先级检查各类错误
        for status, keywords in self.ERROR_PATTERNS.items():
            for kw in keywords:
                if kw.lower() in text_lower or kw in page_text:
                    reason_map = {
                        LoginStatus.INVALID_CREDENTIALS: "账号或密码错误，请检查后重试",
                        LoginStatus.ACCOUNT_LOCKED: "账号被锁定或禁用，请联系 Epic 客服解锁",
                        LoginStatus.RATE_LIMIT: "登录尝试过于频繁，请等待几分钟后再试",
                        LoginStatus.CAPTCHA_REQUIRED: "Epic 要求完成图形验证码，请先在浏览器手动登录一次以通过验证",
                        LoginStatus.NEEDS_VERIFICATION: "需要邮箱/二步验证",
                    }
                    return LoginResult(
                        status=status,
                        reason=reason_map.get(status, f"登录失败: {kw}"),
                        screenshot_tag=f"login_{status}",
                    )

        # 没有匹配到具体错误关键词
        return LoginResult(
            status=LoginStatus.UNKNOWN,
            reason="登录失败，原因不明",
            screenshot_tag="login_unknown",
        )

    async def login(self, page: Page, verification_code: Optional[str] = None) -> LoginResult:
        """执行登录流程，返回精细化的 LoginResult

        Returns:
            LoginResult: status 字段为 LoginStatus 之一
        """
        # 1) 访问登录页
        try:
            await page.goto(
                self.parent.LOGIN_URL, wait_until="domcontentloaded", timeout=60000
            )
        except PWTimeout:
            logger.error("访问登录页超时")
            return LoginResult(
                status=LoginStatus.NETWORK_ERROR,
                reason="无法访问 Epic 登录页（网络超时或 DNS 解析失败）",
                screenshot_tag="login_network_error",
            )

        # 2) 切换到登录 iframe
        iframe = None
        try:
            iframe = await page.wait_for_selector(
                self.LOGIN_IFRAME_SELECTOR, timeout=5000, state="attached"
            )
        except PWTimeout:
            logger.info("未发现登录 iframe")

        target: Page = page
        if iframe:
            try:
                frame = await iframe.content_frame()
                if frame:
                    target = frame
                    logger.info("已切换到登录 iframe")
            except Exception as e:
                logger.warning("切换 iframe 失败: %s", e)

        # 3) 如果提供验证码且页面处于验证步骤，填入
        if verification_code:
            page_text = await self.parent._get_page_text(page)
            if any(p in page_text for p in self.VERIFICATION_PROMPT_TEXTS):
                logger.info("检测到验证页面，填入验证码")
                if await self.parent._fill_first_available(
                    target, self.VERIFICATION_CODE_SELECTORS, verification_code
                ):
                    submit_ok = await self.parent._click_first_available(
                        target,
                        self.SUBMIT_BUTTON_SELECTORS + [
                            'button:has-text("Verify")',
                            'button:has-text("验证")',
                            'button:has-text("确认")',
                        ],
                    )
                    if not submit_ok:
                        logger.error("找不到验证码提交按钮")
                        return LoginResult(
                            status=LoginStatus.PAGE_CHANGED,
                            reason="找不到验证码提交按钮，Epic 登录页结构可能已变化",
                            screenshot_tag="login_page_changed",
                        )

        # 4) 输入邮箱
        email_ok = await self.parent._fill_first_available(
            target, self.EMAIL_INPUT_SELECTORS, self.parent._username
        )
        if not email_ok:
            logger.error("找不到邮箱输入框")
            await self.parent._save_screenshot(page, "login_page_changed")
            return LoginResult(
                status=LoginStatus.PAGE_CHANGED,
                reason="找不到邮箱输入框，Epic 登录页结构可能已变化",
                screenshot_tag="login_page_changed",
            )

        # 5) 输入密码
        pwd_ok = await self.parent._fill_first_available(
            target, self.PASSWORD_INPUT_SELECTORS, self.parent._password
        )
        if not pwd_ok:
            logger.error("找不到密码输入框")
            await self.parent._save_screenshot(page, "login_page_changed")
            return LoginResult(
                status=LoginStatus.PAGE_CHANGED,
                reason="找不到密码输入框，Epic 登录页结构可能已变化",
                screenshot_tag="login_page_changed",
            )

        # 6) 点击登录按钮
        submit_ok = await self.parent._click_first_available(
            target, self.SUBMIT_BUTTON_SELECTORS
        )
        if not submit_ok:
            logger.error("找不到登录按钮")
            await self.parent._save_screenshot(page, "login_page_changed")
            return LoginResult(
                status=LoginStatus.PAGE_CHANGED,
                reason="找不到登录按钮，Epic 登录页结构可能已变化",
                screenshot_tag="login_page_changed",
            )

        # 7) 点击登录后立即抓取错误状态（Epic 错误提示是 toast，几秒后消失）
        # 先等 2-3 秒让 Epic 响应（点击后页面状态稳定）
        await asyncio.sleep(3)

        # 抓取点击后立即的错误信息
        immediate_text = await self.parent._get_page_text(page)
        immediate_url = page.url
        # 保存点击后的截图（包含 Epic 错误提示）
        await self.parent._save_screenshot(page, "login_after_submit")

        # 8) 等待响应（多轮轮询）
        for attempt_idx in range(3):
            try:
                await page.wait_for_url(
                    lambda url: (
                        "store.epicgames.com" in url
                        or "epicgames.com/account" in url
                    ),
                    timeout=8000,
                )
                logger.info("登录成功（URL 跳转）")
                return LoginResult(
                    status=LoginStatus.SUCCESS,
                    reason="登录成功",
                    screenshot_tag="",
                )
            except PWTimeout:
                pass

            # 检查账号菜单
            try:
                await page.wait_for_selector(
                    '[data-testid="user-accountexposed"]', timeout=3000
                )
                logger.info("登录成功（账号菜单）")
                return LoginResult(
                    status=LoginStatus.SUCCESS,
                    reason="登录成功",
                    screenshot_tag="",
                )
            except PWTimeout:
                pass

            current_url = page.url
            page_text = await self.parent._get_page_text(page)

            # 合并第一次抓取的文本（捕获初始 toast 错误）
            combined_text = page_text + " " + immediate_text

            # 检查邮箱验证（单独处理）
            for prompt in self.VERIFICATION_PROMPT_TEXTS:
                if prompt in combined_text:
                    logger.warning("检测到邮箱验证: %s", prompt)
                    await self.parent._save_screenshot(page, "verification_required")
                    return LoginResult(
                        status=LoginStatus.NEEDS_VERIFICATION,
                        reason="Epic 要求邮箱验证码，请检查邮箱获取",
                        screenshot_tag="verification_required",
                    )

            # 检查 hCaptcha 等图形验证码
            has_captcha = await page.evaluate("""
            () => {
                return !!(
                    document.querySelector('iframe[src*="hcaptcha"]') ||
                    document.querySelector('iframe[src*="recaptcha"]') ||
                    document.querySelector('[class*="captcha"]') ||
                    document.querySelector('[id*="captcha"]') ||
                    document.querySelector('.h-captcha') ||
                    document.querySelector('#hcap-script') ||
                    document.querySelector('[data-hcaptcha-widget-id]')
                );
            }
            """)
            if has_captcha:
                logger.warning("检测到 hCaptcha，尝试自动点击验证 checkbox")
                # 尝试自动点击 hCaptcha checkbox
                captcha_clicked = await self._try_solve_hcaptcha(page, target)
                if captcha_clicked:
                    # 点击后等一段时间看看是否解决
                    await asyncio.sleep(5)
                    # 再次检查：是否还存在验证码表单
                    still_captcha = await page.evaluate("""
                    () => !!document.querySelector('iframe[src*="hcaptcha"]')
                    """)
                    if not still_captcha:
                        logger.info("hCaptcha 自动解决成功")
                        # 验证后可能需要重新点击登录
                        await self.parent._click_first_available(
                            target, self.SUBMIT_BUTTON_SELECTORS
                        )
                        await asyncio.sleep(2)
                        continue  # 重新检查结果
                # 自动解决失败，提示用户手动处理
                logger.warning("hCaptcha 自动解决失败，需手动处理")
                await self.parent._save_screenshot(page, "login_captcha")
                return LoginResult(
                    status=LoginStatus.CAPTCHA_REQUIRED,
                    reason="Epic 要求完成图形验证码 (hCaptcha)。可设置 HEADLESS=false 以可见模式运行手动验证，或等待几分钟后重试",
                    screenshot_tag="login_captcha",
                )

            # URL 仍停留在登录页 + 仍存在表单 -> 登录失败（用精细分类）
            if "id.epicgames.com" in current_url and attempt_idx >= 1:
                still_has_form = await page.evaluate("""
                () => !!document.querySelector('input[type="password"], input[name="password"]')
                """)
                if still_has_form:
                    error_result = self._classify_error(combined_text, current_url)
                    await self.parent._save_screenshot(page, error_result.screenshot_tag)
                    logger.error("登录失败: %s (关键词匹配)", error_result.reason)
                    if not error_result.reason or error_result.status == LoginStatus.UNKNOWN:
                        # 将抓取到的部分文本也记录到 reason
                        preview = (combined_text or "")[:200].replace("\n", " ")
                        logger.error("页面文本预览: %s", preview)
                        error_result = LoginResult(
                            status=LoginStatus.UNKNOWN,
                            reason=f"登录失败，原因未知。页面提示: {preview[:80] or '(空)'}",
                            screenshot_tag="login_unknown",
                        )
                    return error_result

            await asyncio.sleep(2)

        # 超时未检测到成功迹象
        await self.parent._save_screenshot(page, "login_unknown")
        preview = (immediate_text or "")[:200].replace("\n", " ")
        return LoginResult(
            status=LoginStatus.UNKNOWN,
            reason=f"登录超时，Epic 未跳转。页面提示: {preview[:80] or '(空)'}",
            screenshot_tag="login_unknown",
        )
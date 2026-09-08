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
            "密码错误", "密码不正确", "密码无效",
            "账号不存在", "账号无效", "账号错误",
            "用户名或密码", "邮箱或密码",
            "invalid credentials", "invalid password", "invalid email",
            "incorrect password", "incorrect email", "incorrect username",
            "invalid login", "wrong password", "wrong email",
            "do not match", "doesn't match", "not recognized",
            "电子邮件地址或密码不正确",
        ],
        # 账号被锁定
        LoginStatus.ACCOUNT_LOCKED: [
            "账号已被锁定", "账号已锁定", "账号被禁用", "账号已禁用",
            "账户锁定", "账户已冻结", "账户被禁用",
            "account locked", "account disabled", "account suspended",
            "locked out", "too many failed", "已暂停", "永久禁用",
        ],
        # 频率限制
        LoginStatus.RATE_LIMIT: [
            "尝试次数过多", "频繁登录", "操作过于频繁", "请稍后再试",
            "too many attempts", "too many requests", "rate limit",
            "try again later", "too many login", "暂时无法",
            "slow down", "请过几分钟",
        ],
        # 图形验证码
        LoginStatus.CAPTCHA_REQUIRED: [
            "captcha", "验证码", "hCaptcha", "hcaptcha", "recaptcha",
            "reCAPTCHA", "are you human", "请完成验证",
        ],
        # 验证提示
        LoginStatus.NEEDS_VERIFICATION: [
            "Enter the code", "Verify", "Check your email",
            "Two-factor", "两步验证", "邮箱验证",
        ],
    }

    def __init__(self, parent):
        self.parent = parent

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

        # 7) 等待响应
        for attempt_idx in range(3):
            try:
                await page.wait_for_url(
                    lambda url: (
                        "store.epicgames.com" in url
                        or "epicgames.com/account" in url
                    ),
                    timeout=15000,
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

            # 检查邮箱验证（单独处理）
            for prompt in self.VERIFICATION_PROMPT_TEXTS:
                if prompt in page_text:
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
                    document.querySelector('#hcap-script')
                );
            }
            """)
            if has_captcha:
                logger.warning("检测到图形验证码")
                await self.parent._save_screenshot(page, "login_captcha")
                return LoginResult(
                    status=LoginStatus.CAPTCHA_REQUIRED,
                    reason="Epic 要求完成图形验证码，请先在浏览器手动登录一次以通过验证",
                    screenshot_tag="login_captcha",
                )

            # URL 仍停留在登录页 + 仍存在表单 -> 登录失败（用精细分类）
            if "id.epicgames.com" in current_url and attempt_idx >= 1:
                still_has_form = await page.evaluate("""
                () => !!document.querySelector('input[type="password"], input[name="password"]')
                """)
                if still_has_form:
                    error_result = self._classify_error(page_text, current_url)
                    await self.parent._save_screenshot(page, error_result.screenshot_tag)
                    logger.error("登录失败: %s (关键词匹配)", error_result.reason)
                    return error_result

            await asyncio.sleep(3)

        # 超时未检测到成功迹象
        await self.parent._save_screenshot(page, "login_unknown")
        return LoginResult(
            status=LoginStatus.UNKNOWN,
            reason="登录超时，未检测到成功迹象（Epic 登录页可能改版）",
            screenshot_tag="login_unknown",
        )
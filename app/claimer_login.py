"""
Epic Games 登录流程（从 claimer.py 拆出，控制单文件行数）

包含：
- _login: 执行登录流程（含邮箱验证检测）
"""
import asyncio
import logging
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)


class LoginHandler:
    """封装 Epic 登录流程

    通过组合（而非继承）由 EpicClaimer 调用，避免循环依赖。
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

    # 二步验证输入框选择器
    VERIFICATION_CODE_SELECTORS = [
        'input#code',
        'input[name="code"]',
        'input[name="verificationCode"]',
        'input[id*="code"]',
        'input[autocomplete="one-time-code"]',
        'input[type="text"][name*="otp"]',
        'input[type="text"][inputmode="numeric"]',
    ]
    # 验证页面提示文案
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

    def __init__(self, parent):
        self.parent = parent  # EpicClaimer 实例

    async def login(self, page: Page, verification_code: Optional[str] = None) -> str:
        """执行登录流程

        Returns:
            "success" - 登录成功
            "failed" - 登录失败（密码错误等）
            "needs_verification" - 需要邮箱验证码
        """
        try:
            await page.goto(self.parent.LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        except PWTimeout:
            logger.error("访问登录页超时")
            return "failed"

        # Epic 登录页通常会把表单放在 iframe 里
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

        # 如果提供了验证码且页面已处于验证步骤，直接填入
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
                        return "failed"

        # 输入邮箱
        email_ok = await self.parent._fill_first_available(
            target, self.EMAIL_INPUT_SELECTORS, self.parent._username
        )
        if not email_ok:
            logger.error("找不到邮箱输入框")
            return "failed"

        # 输入密码
        pwd_ok = await self.parent._fill_first_available(
            target, self.PASSWORD_INPUT_SELECTORS, self.parent._password
        )
        if not pwd_ok:
            logger.error("找不到密码输入框")
            return "failed"

        # 点击登录
        submit_ok = await self.parent._click_first_available(
            target, self.SUBMIT_BUTTON_SELECTORS
        )
        if not submit_ok:
            logger.error("找不到登录按钮")
            return "failed"

        # 等待响应：4 种情况
        # 1. 跳转到 store 或账号中心 -> 登录成功
        # 2. 停留在登录页，出现错误提示 -> 登录失败
        # 3. 跳转到验证页面，需要输入邮箱验证码 -> needs_verification
        # 4. 什么都没发生（超时）-> 登录失败
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
                return "success"
            except PWTimeout:
                pass

            # 检查账号菜单
            try:
                await page.wait_for_selector(
                    '[data-testid="user-accountexposed"]', timeout=3000
                )
                logger.info("登录成功（账号菜单）")
                return "success"
            except PWTimeout:
                pass

            # 获取当前 URL 和页面文本
            current_url = page.url
            page_text = await self.parent._get_page_text(page)

            # 检查是否需要邮箱验证
            for prompt in self.VERIFICATION_PROMPT_TEXTS:
                if prompt in page_text:
                    logger.warning("检测到邮箱验证: %s", prompt)
                    await self.parent._save_screenshot(page, "verification_required")
                    return "needs_verification"

            # 检查错误提示（多种选择器 + 关键文字）
            error_text = await self.parent._get_text_safe(
                target,
                '[role="alert"], .error, [data-testid="error"], '
                '[data-testid="login-error"], [class*="ErrorMessage"], '
                '[class*="error"], [class*="Error"], [aria-live="assertive"]',
            )
            # 显式的错误关键词（Epic 错误提示中常见）
            error_keywords = [
                "密码错误", "不正确", "invalid", "incorrect", "wrong",
                "无法登录", "登录失败", "Unable", "try again",
                "doesn't match", "do not match", "not recognized",
            ]
            has_error = error_text and any(kw in error_text for kw in error_keywords)
            if error_text and has_error:
                logger.error("登录错误提示: %s", error_text)
                await self.parent._save_screenshot(page, "login_failed")
                return "failed"

            # 如果 URL 还停留在 id.epicgames.com/login 且多次轮询后仍未跳转，视为登录失败
            if "id.epicgames.com" in current_url and attempt_idx >= 1:
                logger.warning("URL 仍停留在登录页 (尝试 %d): %s", attempt_idx + 1, current_url)
                # 检查页面是否仍然包含登录表单（说明未跳转，未登录成功）
                still_has_form = await page.evaluate("""
                () => {
                    return !!document.querySelector('input[type="password"], input[name="password"]');
                }
                """)
                if still_has_form:
                    logger.error("登录未跳转且仍存在密码输入框，判定为登录失败")
                    await self.parent._save_screenshot(page, "login_failed")
                    return "failed"

            # 兜底：等待再试
            await asyncio.sleep(3)

        logger.error("登录超时（多轮轮询未检测到成功迹象）")
        await self.parent._save_screenshot(page, "login_unknown")
        return "failed"
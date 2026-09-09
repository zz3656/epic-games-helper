"""
Epic Games 登录后状态判断（从 claimer_login.py 拆出）

包含：
- check_post_submit_state: 提交登录后的状态检测
- detect_hcaptcha_in_text: 从页面文本判断是否 hCaptcha
"""
import logging
from typing import Optional

from playwright.async_api import Page

from app.claimer_login import LoginResult, LoginStatus

logger = logging.getLogger(__name__)


# hCaptcha 文本指示器
# 注意：不能包含 "继续"（Epic 第一阶段点邮箱后点“继续”是正常流程）
HCAPTCHA_TEXT_INDICATORS = [
    "verify you are human",
    "hcaptcha", "hCaptcha",
    "are you human", "i'm not a robot",
    "请完成验证",
    "点击以下方块",
    "请选择所有包含",
    "select all images",
    "正在进行人机验证",
    "human verification",
    "证明你不是机器人",
]


async def check_post_submit_state(page: Page, parent, immediate_text: str) -> LoginResult:
    """提交登录后，检查最终状态

    Args:
        page: Playwright page 对象
        parent: EpicClaimer 实例（用于截图）
        immediate_text: 点击登录后第一时间抓取的页面文本

    Returns:
        LoginResult: 根据最终页面状态返回
    """
    # 检查页面文本中是否包含 hCaptcha 关键词
    if detect_hcaptcha_in_text(immediate_text):
        await parent._save_screenshot(page, "login_captcha")
        logger.warning("根据页面文本检测到 hCaptcha")
        return LoginResult(
            status=LoginStatus.CAPTCHA_REQUIRED,
            reason="页面检测到 hCaptcha 验证提示。如设置了 ENABLE_VNC=true，请通过 noVNC (6080 端口) 手动验证；否则等待几分钟后重试",
            screenshot_tag="login_captcha",
        )

    # 未检测到 hCaptcha，返回 unknown
    await parent._save_screenshot(page, "login_unknown")
    preview = (immediate_text or "")[:200].replace("\n", " ")
    return LoginResult(
        status=LoginStatus.UNKNOWN,
        reason=f"登录超时，Epic 未跳转。页面提示: {preview[:80] or '(空)'}",
        screenshot_tag="login_unknown",
    )


def detect_hcaptcha_in_text(text: str) -> bool:
    """从页面文本判断是否 hCaptcha"""
    if not text:
        return False
    text_lower = text.lower()
    for indicator in HCAPTCHA_TEXT_INDICATORS:
        if indicator.lower() in text_lower or indicator in text:
            return True
    return False


async def has_hcaptcha_iframe(page: Page, target: Optional[Page] = None) -> bool:
    """检查页面或 target 中是否有 hCaptcha iframe"""
    for context in [page, target] if target else [page]:
        if context is None:
            continue
        try:
            found = await context.evaluate("""
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
            if found:
                return True
        except Exception:
            pass
    return False
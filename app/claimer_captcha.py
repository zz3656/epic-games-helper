"""
Epic Games hCaptcha 处理（从 claimer_login.py 拆出）

包含：
- _try_solve_hcaptcha: 自动点击 hCaptcha checkbox
- wait_for_manual_captcha: 等待用户通过 VNC 手动解决
"""
import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def try_solve_hcaptcha(page: Page, target: Page) -> bool:
    """尝试自动点击 hCaptcha checkbox

    hCaptcha 可能位于主页面或登录 iframe 中。
    返回 True 表示成功点击，False 表示失败。
    """
    # 尝试从主页和 target 两个 context 查找
    for context_name, context in [("page", page), ("target", target)]:
        try:
            iframe_selectors = [
                'iframe[src*="hcaptcha.com"][src*="checkbox"]',
                'iframe[src*="hcaptcha.com"]',
                'iframe[src*="hcaptcha"]',
            ]
            for iframe_sel in iframe_selectors:
                iframe_handle = await context.query_selector(iframe_sel)
                if not iframe_handle:
                    continue
                frame = await iframe_handle.content_frame()
                if not frame:
                    continue
                # 点击 checkbox
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
                            logger.info("hCaptcha checkbox 已点击: %s (%s)", cb_sel, context_name)
                            return True
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("在 %s 中点击 hCaptcha 失败: %s", context_name, e)
    return False


async def wait_for_manual_captcha_solve(page: Page, timeout_seconds: int = 120) -> bool:
    """等待用户通过 VNC 手动解决 hCaptcha

    当 ENABLE_VNC=true 时启用。期间每 5 秒检查 hCaptcha 是否消失。
    返回 True 表示 hCaptcha 已被解决。
    """
    interval = 5
    max_checks = timeout_seconds // interval
    for wait_idx in range(max_checks):
        await asyncio.sleep(interval)
        # 检查 hCaptcha 是否被解决
        still_captcha = await page.evaluate("""
        () => !!document.querySelector('iframe[src*="hcaptcha"]')
        """)
        # 检查是否已离开登录页（成功）
        if "id.epicgames.com" not in page.url:
            logger.info("VNC 手动验证后页面已跳转")
            return True
        if not still_captcha:
            logger.info("用户手动解决了 hCaptcha")
            return True
        if wait_idx % 6 == 0:  # 每30秒记录一次
            logger.info("VNC 等待用户解决 hCaptcha... (%d/%d 秒)",
                        wait_idx * interval, timeout_seconds)
    return False


def is_vnc_enabled() -> bool:
    """检查是否启用 VNC"""
    return os.getenv("ENABLE_VNC", "false").lower() == "true"
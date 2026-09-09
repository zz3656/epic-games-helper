"""
Epic Games hCaptcha 处理

包含：
- try_solve_hcaptcha: 自动处理 hCaptcha（点击 checkbox + 等待验证）
- has_hcaptcha: 检查是否存在 hCaptcha
"""
import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def has_hcaptcha(page: Page) -> bool:
    """检查页面是否有 hCaptcha"""
    try:
        return bool(await page.evaluate("""
        () => !!document.querySelector('iframe[src*="hcaptcha"]')
        """))
    except Exception:
        return False


async def try_solve_hcaptcha(page: Page) -> bool:
    """自动处理 hCaptcha

    流程：
    1. 找到 hCaptcha iframe 中的 checkbox 并点击
    2. 等待 hCaptcha 完成验证（iframe 消失）
    3. 返回 True 表示自动处理成功，False 表示需要人工介入

    注意：hCaptcha 有时不需要手动验证（低风险场景），
    点击 checkbox 后 hCaptcha 会自动完成验证并消失。
    """
    try:
        iframe_selectors = [
            'iframe[src*="hcaptcha.com"][src*="checkbox"]',
            'iframe[src*="hcaptcha.com"]',
            'iframe[src*="hcaptcha"]',
        ]
        for iframe_sel in iframe_selectors:
            iframe_handle = await page.query_selector(iframe_sel)
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
                        logger.info("hCaptcha checkbox 已点击: %s", cb_sel)
                        return True
                except Exception:
                    continue
    except Exception as e:
        logger.warning("点击 hCaptcha checkbox 失败: %s", e)
    return False


async def wait_for_hcaptcha_auto_resolve(page: Page, timeout_seconds: int = 15) -> bool:
    """等待 hCaptcha 自动解决（低风险场景）

    在 VNC 未启用时，自动点击 checkbox 后等待 hCaptcha 完成验证。
    hCaptcha 验证通过后，iframe 会被移除。
    """
    interval = 1
    for _ in range(timeout_seconds):
        await asyncio.sleep(interval)
        still_captcha = await page.evaluate("""
        () => !!document.querySelector('iframe[src*="hcaptcha"]')
        """)
        if not still_captcha:
            logger.info("hCaptcha 自动验证通过")
            return True
    logger.warning("hCaptcha 自动验证超时 (%d秒)，需要人工介入", timeout_seconds)
    return False


def is_vnc_enabled() -> bool:
    """检查是否启用 VNC"""
    return os.getenv("ENABLE_VNC", "false").lower() == "true"

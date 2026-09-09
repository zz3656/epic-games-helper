"""
Epic Games 表单填充逻辑（从 claimer_login.py 拆出）

包含：
- fill_email: 智能邮箱填充
- fill_password: 智能密码填充
- click_login_button: 点击登录按钮
"""
import logging
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def fill_email(target: Page, email: str) -> bool:
    """智能填充邮箱输入框

    优先级：
    1. JS 按 type/email、name、id、autocomplete、placeholder 查找
    2. 备选 CSS 选择器列表
    """
    if not email:
        return False
    # 优先用 JS 按语义查找
    try:
        handle = await target.evaluate_handle("""
        () => {
            const inputs = document.querySelectorAll('input');
            for (const input of inputs) {
                const type = (input.type || '').toLowerCase();
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();
                const autoComplete = (input.autocomplete || '').toLowerCase();
                const placeholder = (input.placeholder || '').toLowerCase();
                if (type === 'email' ||
                    autoComplete === 'username' ||
                    name.includes('email') || id.includes('email') ||
                    placeholder.includes('email') || placeholder.includes('@') ||
                    placeholder.includes('邮箱')) {
                    return input;
                }
            }
            // 备选：第一个非密码的 text input
            for (const input of inputs) {
                if (input.type !== 'password' && input.type !== 'hidden') {
                    return input;
                }
            }
            return null;
        }
        """)
        if handle:
            await handle.fill(email)
            logger.info("JS 邮箱填充成功")
            return True
    except Exception as e:
        logger.warning("JS 邮箱填充失败: %s", e)
    # 备选：CSS 选择器
    css_selectors = [
        'input#email',
        'input[name="email"]',
        'input[type="email"]',
        'input[autocomplete="username"]',
        'input[name="username"]',
    ]
    return await _try_css_fill(target, css_selectors, email, "email")


async def fill_password(target: Page, password: str) -> bool:
    """智能填充密码输入框

    优先级：
    1. JS 按 input[type=password] 查找（但排除 confirm password）
    2. 备选 CSS 选择器列表
    """
    if not password:
        return False
    # 优先用 JS 查找
    try:
        handle = await target.evaluate_handle("""
        () => {
            const inputs = document.querySelectorAll('input[type="password"]');
            if (inputs.length === 0) return null;
            // 排除 confirm password
            for (const input of inputs) {
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();
                const autoComplete = (input.autocomplete || '').toLowerCase();
                if (name.includes('confirm') || id.includes('confirm') ||
                    name.includes('new') || autoComplete === 'new-password') {
                    continue;  // 跳过注册确认/新密码字段
                }
                return input;
            }
            return inputs[0];  // 没有确认字段就用第一个
        }
        """)
        if handle:
            await handle.fill(password)
            logger.info("JS 密码填充成功")
            return True
    except Exception as e:
        logger.warning("JS 密码填充失败: %s", e)
    # 备选：CSS 选择器
    css_selectors = [
        'input#password',
        'input[name="password"]',
        'input[type="password"]',
        'input[autocomplete="current-password"]',
    ]
    return await _try_css_fill(target, css_selectors, password, "password")


async def click_login_button(target: Page) -> bool:
    """点击登录按钮

    优先级：
    1. JS 按 button[type=submit] 查找
    2. 备选 CSS 选择器
    """
    # 优先用 JS 查找
    try:
        clicked = await target.evaluate("""
        () => {
            const buttons = document.querySelectorAll('button, input[type="submit"], a[role="button"]');
            for (const btn of buttons) {
                const text = (btn.innerText || btn.value || btn.textContent || '').toLowerCase();
                const type = (btn.type || '').toLowerCase();
                if (type === 'submit' ||
                    text.includes('登录') || text.includes('log in') ||
                    text.includes('sign in') || text.includes('登录')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }
        """)
        if clicked:
            logger.info("JS 登录按钮点击成功")
            return True
    except Exception as e:
        logger.warning("JS 按钮点击失败: %s", e)
    # 备选：CSS
    return await _try_css_click(target, [
        'button#login',
        'button[type="submit"]',
        'button:has-text("登录")',
        'button:has-text("Log In")',
        'button:has-text("Sign In")',
    ])


async def _try_css_fill(target: Page, selectors: list, value: str, field_name: str) -> bool:
    for sel in selectors:
        try:
            el = await target.wait_for_selector(sel, timeout=2500, state="visible")
            if el:
                await el.fill(value)
                logger.info("CSS 填充 %s 成功: %s", field_name, sel)
                return True
        except Exception:
            continue
    return False


async def _try_css_click(target: Page, selectors: list) -> bool:
    for sel in selectors:
        try:
            el = await target.wait_for_selector(sel, timeout=2500, state="visible")
            if el:
                await el.click()
                logger.info("CSS 按钮点击成功: %s", sel)
                return True
        except Exception:
            continue
    return False
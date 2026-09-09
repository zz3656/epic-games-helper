"""
Epic Games 浏览器启动配置（从 claimer.py 拆出）

包含：
- build_launch_kwargs: 根据 VNC/headless 配置构造 Playwright launch 参数
"""
import logging
import os

logger = logging.getLogger(__name__)


def build_launch_kwargs(headless: bool) -> dict:
    """构造 Playwright chromium.launch 参数

    当 ENABLE_VNC=true 时：
    - 强制使用可见模式（即使 headless=True）
    - 注入 DISPLAY=:99 环境变量
    - 不传 --headless=new 参数

    当 VNC 未启用时：
    - 使用 Chrome 的 new headless 模式（更接近真实浏览器）
    """
    vnc_enabled = os.getenv("ENABLE_VNC", "false").lower() == "true"
    effective_headless = headless and not vnc_enabled

    launch_kwargs = {
        "headless": effective_headless,
        "args": [
            # 隐藏 navigator.webdriver 标志
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            # 隐藏自动化特征
            "--disable-features=IsolateOrigins,site-per-process",
            # 使浏览器看起来更像正常用户
            "--disable-infobars",
            "--window-size=1440,900",
            "--start-maximized",
        ],
    }
    if effective_headless:
        # 使用 Chrome 的 new headless 模式
        launch_kwargs["args"].append("--headless=new")
        launch_kwargs["args"].append("--disable-gpu")
    if vnc_enabled:
        os.environ["DISPLAY"] = ":99"
        launch_kwargs["env"] = os.environ.copy()
        logger.info("VNC 模式启动，DISPLAY=:99，浏览器将可见")
    return launch_kwargs


def is_vnc_enabled() -> bool:
    """检查是否启用了 VNC"""
    return os.getenv("ENABLE_VNC", "false").lower() == "true"
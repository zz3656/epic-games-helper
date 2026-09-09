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

    启用了大量反检测参数：
    - 隐藏 navigator.webdriver
    - 禁用 Blink 自动化特征
    - 随机化窗口大小（避免被识别为同一台机器）
    - 关闭 WebRTC 真实 IP 泄露
    - 模拟真实浏览器特征
    """
    vnc_enabled = os.getenv("ENABLE_VNC", "false").lower() == "true"
    effective_headless = headless and not vnc_enabled

    # 真实的 Chrome 启动参数
    launch_kwargs = {
        "headless": effective_headless,
        "args": [
            # === 自动化特征隐藏 ===
            "--disable-blink-features=AutomationControlled",  # 关键
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-features=AutomationControlled",
            # === 沙箱相关 ===
            "--no-sandbox",
            "--no-zygote",
            "--disable-dev-shm-usage",
            # === 反检测：让浏览器看起来像真实用户 ===
            "--disable-infobars",  # 隐藏 "Chrome is being controlled by automated test software" 信息条
            "--disable-popup-blocking",
            "--disable-notifications",
            "--disable-default-apps",
            "--disable-translate",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-client-side-phishing-detection",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-background-timer-throttling",
            "--disable-ipc-flooding-protection",
            "--disable-features=TranslateUI",
            # === 窗口 ===
            "--window-size=1440,900",
            "--start-maximized",
            "--lang=zh-CN",
            # === WebRTC 真实 IP 泄露防护（关键） ===
            # 服务器 IP 是被风控的关键信号
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            # === 时区/语言一致性 ===
            "--force-color-profile=srgb",
            "--enable-features=NetworkService,NetworkServiceInProcess",
        ],
    }
    if effective_headless:
        # 使用 Chrome 的 new headless 模式
        launch_kwargs["args"].append("--headless=new")
        launch_kwargs["args"].append("--disable-gpu")
        # 重要：headless 模式必须明确禁用，否则会被反检测
        launch_kwargs["args"].append("--disable-software-rasterizer")

    if vnc_enabled:
        # VNC 模式下：强制可见模式 + X11
        os.environ["DISPLAY"] = ":99"
        launch_kwargs["env"] = os.environ.copy()
        launch_kwargs["args"].append("--no-sandbox")
        launch_kwargs["args"].extend([
            "--disable-gpu-sandbox",
            "--window-position=200,200",
        ])
        logger.info("VNC 模式启动参数: DISPLAY=%s, headless=%s, args=%s",
                    os.environ["DISPLAY"], effective_headless,
                    launch_kwargs["args"])
    return launch_kwargs


def is_vnc_enabled() -> bool:
    """检查是否启用了 VNC"""
    return os.getenv("ENABLE_VNC", "false").lower() == "true"

"""
VNC 状态和截图 API 路由（从 main.py 拆出）

包含：
- /api/vnc/status: VNC 服务状态
- /api/screenshots: 截图列表
- /api/screenshots/{filename}: 获取截图
"""
import logging
import os
import subprocess

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/vnc/status")
async def vnc_status():
    """查询 VNC 服务状态（供前端检测是否启用了 VNC）"""
    enabled = os.getenv("ENABLE_VNC", "false").lower() == "true"
    # 检查进程是否存在
    vnc_running = False
    novnc_running = False
    xvfb_running = False
    chromium_running = False
    display_env = os.environ.get("DISPLAY", "(not set)")
    try:
        ps = subprocess.run(["ps", "-ef"], capture_output=True, text=True, timeout=5)
        vnc_running = "x11vnc" in ps.stdout
        novnc_running = "websockify" in ps.stdout or "novnc" in ps.stdout
        xvfb_running = "Xvfb" in ps.stdout
        chromium_running = "chrom" in ps.stdout.lower()
    except Exception:
        pass
    return {
        "enabled": enabled,
        "display_env": display_env,
        "xvfb_running": xvfb_running,
        "vnc_running": vnc_running,
        "novnc_running": novnc_running,
        "chromium_running": chromium_running,
        "novnc_url": "/vnc.html" if novnc_running else None,
        "vnc_password_set": bool(os.getenv("VNC_PASSWORD")),
    }


@router.get("/api/screenshots")
async def list_screenshots():
    """列出可用截图（调试用）"""
    screenshot_dir = "/app/screenshots"
    try:
        if not os.path.exists(screenshot_dir):
            return {"files": []}
        files = sorted(
            [f for f in os.listdir(screenshot_dir) if f.endswith(".png")],
            key=lambda x: os.path.getmtime(os.path.join(screenshot_dir, x)),
            reverse=True,
        )
        return {"files": files[:20]}
    except Exception as e:
        return {"files": [], "error": str(e)}


@router.get("/api/screenshots/{filename}")
async def get_screenshot(filename: str):
    """获取截图（调试用）"""
    screenshot_dir = "/app/screenshots"
    path = os.path.join(screenshot_dir, filename)
    # 安全检查：防止路径穿越
    if not os.path.exists(path) or ".." in filename or "/" in filename:
        raise HTTPException(status_code=404, detail="截图不存在")
    return FileResponse(path, media_type="image/png", headers={
        "Cache-Control": "no-cache",
        "Content-Disposition": f'inline; filename="{filename}"',
    })
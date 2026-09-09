"""
VNC WebSocket 代理（从 main.py 拆出）

通过 FastAPI WebSocket 把浏览器 noVNC 请求代理到本地 x11vnc 5900 端口。
这样用户只需要暴露 8000 端口就能使用 VNC。

WebSocket URL: ws://host:8000/vnc-ws
"""
import asyncio
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/vnc-ws")
async def vnc_websocket_proxy(websocket: WebSocket):
    """VNC WebSocket 代理

    接收浏览器的 noVNC 连接，转发到本地 x11vnc 5900 端口。
    """
    await websocket.accept()
    target_host = "127.0.0.1"
    target_port = 5900
    logger.info("VNC WebSocket 代理连接: %s -> %s:%s",
                websocket.client, target_host, target_port)

    # 连接到 x11vnc
    try:
        reader, writer = await asyncio.open_connection(target_host, target_port)
    except Exception as e:
        logger.error("无法连接到 x11vnc %s:%s: %s", target_host, target_port, e)
        await websocket.close(code=1011, reason=f"Cannot connect to VNC server: {e}")
        return

    async def ws_to_vnc():
        """WebSocket -> VNC"""
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except WebSocketDisconnect:
            logger.info("WebSocket 断开")
        except Exception as e:
            logger.warning("ws_to_vnc 错误: %s", e)
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def vnc_to_ws():
        """VNC -> WebSocket"""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    logger.info("VNC 连接关闭")
                    break
                await websocket.send_bytes(data)
        except Exception as e:
            logger.warning("vnc_to_ws 错误: %s", e)
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # 并发双向传输
    try:
        await asyncio.gather(ws_to_vnc(), vnc_to_ws(), return_exceptions=True)
    finally:
        try:
            writer.close()
        except Exception:
            pass
        logger.info("VNC WebSocket 代理连接结束")
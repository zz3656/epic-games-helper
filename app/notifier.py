"""
Webhook 通知推送（可选启用）

支持多种推送渠道：
- Bark（iOS 推送，免费，推荐）
- Server 酱（微信推送）
- Telegram Bot
- 通用 Webhook（自定义 URL）

通过环境变量启用：
- NOTIFY_WEBHOOK_TYPE=bark|serverchan|telegram|generic
- NOTIFY_WEBHOOK_URL=https://...
- NOTIFY_WEBHOOK_TOKEN=...（Bark 的 device key 或 Telegram 的 bot token 等）

如果未配置 NOTIFY_WEBHOOK_URL，则跳过推送（仅写入 history）。
"""
import asyncio
import json
import logging
import os
import urllib.parse
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    """Webhook 推送器

    支持的渠道（通过 NOTIFY_WEBHOOK_TYPE 选择）：
    - bark:       Bark iOS 推送（推荐）。URL = https://api.day.app/{key}
    - serverchan: Server 酱（微信）。URL = https://sctapi.ftqq.com/{sendkey}.send
    - telegram:   Telegram Bot。URL = https://api.telegram.org/bot{token}/sendMessage
    - generic:    通用 webhook，POST JSON {title, body, games}
    """

    def __init__(self):
        self.type = (os.getenv("NOTIFY_WEBHOOK_TYPE") or "").strip().lower()
        self.url = (os.getenv("NOTIFY_WEBHOOK_URL") or "").strip()
        self.token = (os.getenv("NOTIFY_WEBHOOK_TOKEN") or "").strip()
        # 可选：消息签名（防止伪造）
        self.sign_key = (os.getenv("NOTIFY_SIGN_KEY") or "").strip()

    @property
    def enabled(self) -> bool:
        """是否启用推送（需要 type 和 url 都有）"""
        return bool(self.type) and bool(self.url)

    async def send(self, title: str, body: str, games: Optional[List[dict]] = None,
                   level: str = "active", icon: str = "🎮") -> bool:
        """推送通知

        Args:
            title: 通知标题
            body: 通知正文
            games: 游戏列表（每个含 title, url, original_price, end_date）
            level: bark 的 level（active/timeSensitive/passive）
            icon: bark 的 icon emoji

        Returns:
            是否推送成功
        """
        if not self.enabled:
            logger.info("Webhook 未配置，跳过推送")
            return False

        if games is None:
            games = []

        try:
            if self.type == "bark":
                return await self._send_bark(title, body, games, level, icon)
            elif self.type == "serverchan":
                return await self._send_serverchan(title, body, games)
            elif self.type == "telegram":
                return await self._send_telegram(title, body, games)
            elif self.type == "generic":
                return await self._send_generic(title, body, games)
            else:
                logger.warning("未知的 webhook 类型: %s", self.type)
                return False
        except Exception as e:
            logger.exception("Webhook 推送失败: %s", e)
            return False

    # ==================== 各渠道实现 ====================

    async def _send_bark(self, title: str, body: str, games: List[dict],
                         level: str, icon: str) -> bool:
        """Bark 推送（iOS 推送，免费）

        URL 格式：https://api.day.app/{device_key}/{title}/{body}?icon=...&level=...&group=...
        """
        # Bark URL 直接拼接路径
        device_key = self.token or self.url.rstrip("/").split("/")[-1]
        if not device_key or device_key == self.url:
            logger.error("Bark 配置错误：缺少 device key（设置 NOTIFY_WEBHOOK_TOKEN）")
            return False

        # URL encode 参数
        encoded_title = urllib.parse.quote(title, safe="")
        encoded_body = urllib.parse.quote(body, safe="")

        # 拼接游戏信息到 body
        full_body = body
        if games:
            full_body += "\n\n"
            for g in games[:5]:  # Bark 推送最多列 5 个
                title_g = g.get("title", "")
                price = g.get("original_price", "")
                end = g.get("end_date", "")[:10] if g.get("end_date") else ""
                full_body += f"🎁 {title_g}"
                if price:
                    full_body += f" ({price} → 免费)"
                if end:
                    full_body += f" 截止 {end}"
                full_body += "\n"

        encoded_body = urllib.parse.quote(full_body, safe="")
        push_url = f"https://api.day.app/{device_key}/{encoded_title}/{encoded_body}"

        # 添加 query 参数
        params = []
        params.append(f"icon={icon}")
        params.append(f"level={level}")
        params.append("group=epic-games")
        if len(games) > 5:
            params.append(f"isArchive=1")
        push_url += "?" + "&".join(params)

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(push_url)
            if resp.status_code == 200:
                data = resp.json() if resp.text else {}
                if data.get("code") == 200:
                    logger.info("Bark 推送成功: %s", title)
                    return True
                else:
                    logger.warning("Bark 推送失败: %s", data)
                    return False
            else:
                logger.warning("Bark 推送 HTTP %s: %s", resp.status_code, resp.text[:200])
                return False

    async def _send_serverchan(self, title: str, body: str, games: List[dict]) -> bool:
        """Server 酱推送（微信推送）

        URL 格式：https://sctapi.ftqq.com/{sendkey}.send
        POST: title=...&desp=...
        """
        sendkey = self.token or self.url.rstrip("/").split("/")[-1].replace(".send", "")
        if not sendkey:
            logger.error("Server 酱配置错误：缺少 send key（设置 NOTIFY_WEBHOOK_TOKEN）")
            return False

        # 拼接游戏信息到 desp（markdown 格式）
        desp = body
        if games:
            desp += "\n\n### 本周免费游戏\n\n"
            for g in games[:8]:
                title_g = g.get("title", "")
                url = g.get("url", "")
                price = g.get("original_price", "")
                end = g.get("end_date", "")[:10] if g.get("end_date") else ""
                desp += f"- 🎁 **{title_g}**"
                if price:
                    desp += f" ({price} → 免费)"
                if end:
                    desp += f"  截止 `{end}`"
                if url:
                    desp += f"\n  [前往领取]({url})"
                desp += "\n"

        push_url = f"https://sctapi.ftqq.com/{sendkey}.send"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(push_url, data={"title": title, "desp": desp})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    logger.info("Server 酱推送成功: %s", title)
                    return True
                else:
                    logger.warning("Server 酱推送失败: %s", data)
                    return False
            else:
                logger.warning("Server 酱推送 HTTP %s: %s", resp.status_code, resp.text[:200])
                return False

    async def _send_telegram(self, title: str, body: str, games: List[dict]) -> bool:
        """Telegram Bot 推送

        URL 格式：https://api.telegram.org/bot{token}/sendMessage
        POST: chat_id=...&text=...&parse_mode=MarkdownV2
        """
        bot_token = self.token
        chat_id = self.url.split("/")[-1] if self.url else ""  # 用 url 当 chat_id
        if not bot_token or not chat_id:
            logger.error("Telegram 配置错误：需要 token + chat_id")
            return False

        # 拼接游戏信息
        text = f"*{title}*\n\n{body}"
        if games:
            text += "\n\n*本周免费游戏：*\n"
            for g in games[:8]:
                title_g = g.get("title", "")
                url = g.get("url", "")
                price = g.get("original_price", "")
                end = g.get("end_date", "")[:10] if g.get("end_date") else ""
                text += f"• {title_g}"
                if price:
                    text += f" ({price} → 免费)"
                if end:
                    text += f" 截止 {end}"
                if url:
                    text += f"\n  [领取]({url})"
                text += "\n"

        # 转义 MarkdownV2 特殊字符
        # 简单实现：仅在纯文本前加反斜杠
        # 用户体验更重要，让 Markdown 解析失败时自动降级为纯文本
        text_plain = text.replace("*", "").replace("[", "").replace("]", "").replace("`", "")

        push_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(push_url, json={
                "chat_id": chat_id,
                "text": text_plain,
                "disable_web_page_preview": True,
            })
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info("Telegram 推送成功: %s", title)
                    return True
                else:
                    logger.warning("Telegram 推送失败: %s", data)
                    return False
            else:
                logger.warning("Telegram 推送 HTTP %s: %s", resp.status_code, resp.text[:200])
                return False

    async def _send_generic(self, title: str, body: str, games: List[dict]) -> bool:
        """通用 Webhook

        POST JSON 到 NOTIFY_WEBHOOK_URL：
        {
            "title": "...",
            "body": "...",
            "games": [{"title": "...", "url": "...", "original_price": "...", "end_date": "..."}],
            "timestamp": "2026-09-11T00:05:00+08:00"
        }
        """
        payload = {
            "title": title,
            "body": body,
            "games": games,
            "timestamp": asyncio.get_event_loop().time(),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.url, json=payload)
            if resp.status_code in (200, 201, 202, 204):
                logger.info("Generic webhook 推送成功: %s", title)
                return True
            else:
                logger.warning("Generic webhook 推送 HTTP %s: %s", resp.status_code, resp.text[:200])
                return False
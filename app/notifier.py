"""
Webhook 通知推送（可选启用）

支持多种推送渠道：
- Bark（iOS 推送，免费，推荐）
- Server 酱（微信推送）
- PushPlus（微信/钉钉/飞书等，免费，推荐）
- Telegram Bot（频道/群组，免费）
- 通用 Webhook（自定义 URL）

通过环境变量启用：
- NOTIFY_WEBHOOK_TYPE=bark|serverchan|pushplus|telegram|generic
- NOTIFY_WEBHOOK_URL=https://...
- NOTIFY_WEBHOOK_TOKEN=...（各渠道的 key/token）

各渠道配置指南：

1. Bark（iOS 推送）
   下载 Bark App → 获取 device key → 配置如下：
   NOTIFY_WEBHOOK_TYPE=bark
   NOTIFY_WEBHOOK_TOKEN=YourDeviceKey

2. PushPlus（微信推送，推荐）
   访问 http://www.pushplus.plus → 注册获取 token → 配置如下：
   NOTIFY_WEBHOOK_TYPE=pushplus
   NOTIFY_WEBHOOK_TOKEN=YourPushPlusToken

3. Server 酱（微信推送）
   访问 https://sct.ftqq.com → 注册获取 sendkey → 配置如下：
   NOTIFY_WEBHOOK_TYPE=serverchan
   NOTIFY_WEBHOOK_TOKEN=YourServerChanSendKey

4. Telegram Bot
   通过 @BotFather 创建 bot → 获取 token → 添加 bot 到频道/群组
   获取 chat_id（@MissRose_Bot 输入 /info）→ 配置如下：
   NOTIFY_WEBHOOK_TYPE=telegram
   NOTIFY_WEBHOOK_URL=https://api.telegram.org/bot{token}/sendMessage
   NOTIFY_WEBHOOK_TOKEN={chat_id}

5. 通用 Webhook
   NOTIFY_WEBHOOK_TYPE=generic
   NOTIFY_WEBHOOK_URL=https://your-server.com/webhook

如果未配置，则跳过推送（仅写入 history）。
"""
import logging
import os
import urllib.parse
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    """Webhook 推送器

    支持的渠道（通过 NOTIFY_WEBHOOK_TYPE 选择）：
    - bark:       Bark iOS 推送。URL = https://api.day.app/{key}
    - serverchan: Server 酱（微信）。URL = https://sctapi.ftqq.com/{sendkey}.send
    - pushplus:   PushPlus 多渠道推送。Token = 官方 token
    - telegram:   Telegram Bot。URL = https://api.telegram.org/bot{token}/sendMessage
    - generic:    通用 webhook，POST JSON {title, body, games}
    """

    def __init__(self):
        self.type = (os.getenv("NOTIFY_WEBHOOK_TYPE") or "").strip().lower()
        self.url = (os.getenv("NOTIFY_WEBHOOK_URL") or "").strip()
        self.token = (os.getenv("NOTIFY_WEBHOOK_TOKEN") or "").strip()
        # PushPlus 专用：推送方式（wechat/email/webhook/bark/sms/voice）
        self.pushplus_channel = os.getenv("PUSHPLUS_CHANNEL", "wechat").strip().lower()
        # Telegram 专用：chat_id（如 url 未包含）
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    @property
    def enabled(self) -> bool:
        """是否启用推送"""
        return bool(self.type)

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
            elif self.type == "pushplus":
                return await self._send_pushplus(title, body, games)
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

    # ==================== 构建游戏列表文本 ====================

    @staticmethod
    def _build_games_text(games: List[dict], max_count: int = 8) -> str:
        """构建游戏列表文本（各渠道通用）"""
        lines = []
        for g in games[:max_count]:
            title = g.get("title", "")
            price = g.get("original_price", "")
            end = g.get("end_date", "")[:10] if g.get("end_date") else ""
            url = g.get("url", "")
            line = f"- 🎮 **{title}**"
            if price:
                line += f" `({price}→免费)`"
            if end:
                line += f" 截止 {end}"
            if url:
                line += f"\n  [前往领取]({url})"
            lines.append(line)
        return "\n".join(lines)

    # ==================== 各渠道实现 ====================

    async def _send_bark(self, title: str, body: str, games: List[dict],
                         level: str, icon: str) -> bool:
        """Bark 推送（iOS 推送，免费）

        URL 格式：https://api.day.app/{device_key}/{title}/{body}
        """
        device_key = self.token or self.url.rstrip("/").split("/")[-1]
        if not device_key or device_key == self.url:
            logger.error("Bark 配置错误：缺少 device key（设置 NOTIFY_WEBHOOK_TOKEN）")
            return False

        encoded_title = urllib.parse.quote(title, safe="")
        full_body = body
        if games:
            full_body += "\n\n" + self._build_games_text(games, 5)

        encoded_body = urllib.parse.quote(full_body, safe="")
        push_url = f"https://api.day.app/{device_key}/{encoded_title}/{encoded_body}"

        params = []
        params.append(f"icon={icon}")
        params.append(f"level={level}")
        params.append("group=epic-games")
        if len(games) > 5:
            params.append("isArchive=1")
        push_url += "?" + "&".join(params)

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(push_url)
            if resp.status_code == 200:
                data = resp.json() if resp.text else {}
                if data.get("code") == 200:
                    logger.info("Bark 推送成功: %s", title)
                    return True
                logger.warning("Bark 推送失败: %s", data)
                return False
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

        desp = body
        if games:
            desp += "\n\n### 本周免费游戏\n\n" + self._build_games_text(games, 8)

        push_url = f"https://sctapi.ftqq.com/{sendkey}.send"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(push_url, data={"title": title, "desp": desp})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    logger.info("Server 酱推送成功: %s", title)
                    return True
                logger.warning("Server 酱推送失败: %s", data)
                return False
            logger.warning("Server 酱推送 HTTP %s: %s", resp.status_code, resp.text[:200])
            return False

    async def _send_pushplus(self, title: str, body: str, games: List[dict]) -> bool:
        """PushPlus 推送（微信/邮件/钉钉/飞书等，免费）

        官方 API：https://www.pushplus.plus/send
        POST JSON: {"token": "xxx", "title": "xxx", "content": "xxx", "template": "markdown", "channel": "wechat"}
        """
        if not self.token:
            logger.error("PushPlus 配置错误：缺少 token（设置 NOTIFY_WEBHOOK_TOKEN）")
            return False

        content = body
        if games:
            content += "\n\n---\n本周免费游戏：\n"
            for g in games[:10]:
                title_g = g.get("title", "")
                price = g.get("original_price", "")
                end = g.get("end_date", "")[:10] if g.get("end_date") else ""
                url = g.get("url", "")
                line = f"- {title_g}"
                if price:
                    line += f" `({price}→免费)`"
                if end:
                    line += f" 截止{end}"
                if url:
                    line += f"\n  [领取]({url})"
                content += line + "\n"

        payload = {
            "token": self.token,
            "title": title,
            "content": content,
            "template": "markdown",
            "channel": self.pushplus_channel,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://www.pushplus.plus/send",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 200:
                    logger.info("PushPlus 推送成功 (%s): %s", self.pushplus_channel, title)
                    return True
                logger.warning("PushPlus 推送失败: %s", data)
                return False
            logger.warning("PushPlus 推送 HTTP %s: %s", resp.status_code, resp.text[:200])
            return False

    async def _send_telegram(self, title: str, body: str, games: List[dict]) -> bool:
        """Telegram Bot 推送

        需要配置：
        - NOTIFY_WEBHOOK_URL = https://api.telegram.org/bot{token}/sendMessage
        - NOTIFY_WEBHOOK_TOKEN = {chat_id}
        或通过环境变量：
        - TELEGRAM_CHAT_ID = {chat_id}
        """
        bot_token = self.url.replace("https://api.telegram.org/bot", "").split("/")[0] if self.url else ""
        chat_id = self.token or self.telegram_chat_id

        if not bot_token or not chat_id:
            logger.error(
                "Telegram 配置错误：需要 bot token + chat_id\n"
                "  NOTIFY_WEBHOOK_URL=https://api.telegram.org/bot{token}/sendMessage\n"
                "  NOTIFY_WEBHOOK_TOKEN={chat_id}"
            )
            return False

        text = f"*{title}*\n\n{body}"
        if games:
            text += "\n\n*本周免费游戏：*\n"
            for g in games[:10]:
                title_g = g.get("title", "")
                url = g.get("url", "")
                price = g.get("original_price", "")
                end = g.get("end_date", "")[:10] if g.get("end_date") else ""
                line = f"- {title_g}"
                if price:
                    line += f" `({price}→免费)`"
                if end:
                    line += f" 截止 {end}"
                if url:
                    line += f" [领取]({url})"
                text += line + "\n"

        push_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(push_url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            })
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info("Telegram 推送成功: %s", title)
                    return True
                # MarkdownV2 特殊字符可能转义失败，降级为纯文本重试
                if "Bad Request" in str(data):
                    logger.info("Telegram MarkdownV2 转义失败，降级为纯文本重试")
                    text_plain = text.replace("*", "").replace("_", "").replace("[", "").replace("]", "")
                    text_plain = text_plain.replace("`", "").replace("~", "")
                    resp = await client.post(push_url, json={
                        "chat_id": chat_id,
                        "text": text_plain,
                        "parse_mode": "MarkdownV2",
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            logger.info("Telegram 推送成功（纯文本降级）: %s", title)
                            return True
                logger.warning("Telegram 推送失败: %s", data)
                return False
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
            "timestamp": int(time.time()),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.url, json=payload)
            if resp.status_code in (200, 201, 202, 204):
                logger.info("Generic webhook 推送成功: %s", title)
                return True
            logger.warning("Generic webhook HTTP %s: %s", resp.status_code, resp.text[:200])
            return False

"""
Webhook 通知推送（可选启用）

支持多种推送渠道：
- Server 酱（微信推送）
- Telegram Bot（频道/群组，免费）

通过全局环境变量启用（与用户配置共存，互不干扰）：
- NOTIFY_WEBHOOK_TYPE=serverchan|telegram
- NOTIFY_WEBHOOK_URL=https://...
- NOTIFY_WEBHOOK_TOKEN=...（各渠道的 key/token）

各渠道配置指南：

1. Server 酱（微信推送）
   访问 https://sct.ftqq.com → 注册获取 SendKey → 配置如下：
   NOTIFY_WEBHOOK_TYPE=serverchan
   NOTIFY_WEBHOOK_TOKEN=SCTxxxxxxxxxx

2. Telegram Bot
   通过 @BotFather 创建 bot → 获取 token → 添加 bot 到频道/群组
   获取 chat_id（@MissRose_Bot 输入 /info）→ 配置如下：
   NOTIFY_WEBHOOK_TYPE=telegram
   NOTIFY_WEBHOOK_URL=https://api.telegram.org/bot{token}/sendMessage
   NOTIFY_WEBHOOK_TOKEN={chat_id}

如果未配置，则跳过推送（仅写入 history）。
"""
import logging
import os
import time
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    """Webhook 推送器

    支持的渠道（通过 NOTIFY_WEBHOOK_TYPE 或 user_push_config.type 选择）：
    - serverchan: Server 酱（微信）。URL = https://sctapi.ftqq.com/{sendkey}.send
    - telegram:   Telegram Bot。URL = https://api.telegram.org/bot{token}/sendMessage
    """

    VALID_TYPES = ["serverchan", "telegram"]

    def __init__(self, user_push_config: Optional[dict] = None):
        """初始化 Notifier

        Args:
            user_push_config: 用户推送配置（来自 user_store）
                              如果为 None，则使用全局环境变量
        """
        if user_push_config:
            # 使用用户配置
            self.type = (user_push_config.get("type") or "").strip().lower()
            self.url = (user_push_config.get("url") or "").strip()
            self.token = (user_push_config.get("token") or "").strip()
            self.pushplus_channel = (user_push_config.get("channel") or "wechat").strip().lower()
            self.telegram_chat_id = ""
        else:
            # 使用全局环境变量
            self.type = (os.getenv("NOTIFY_WEBHOOK_TYPE") or "").strip().lower()
            self.url = (os.getenv("NOTIFY_WEBHOOK_URL") or "").strip()
            self.token = (os.getenv("NOTIFY_WEBHOOK_TOKEN") or "").strip()
            self.pushplus_channel = os.getenv("PUSHPLUS_CHANNEL", "wechat").strip().lower()
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
            level: bark 的 level（active/timeSensitive/passive），仅 bark 使用
            icon: bark 的 icon emoji，仅 bark 使用

        Returns:
            是否推送成功
        """
        success, _ = await self.send_with_detail(title, body, games, level, icon)
        return success

    async def send_with_detail(self, title: str, body: str, games: Optional[List[dict]] = None,
                                level: str = "active", icon: str = "🎮") -> tuple:
        """推送通知，返回 (success: bool, detail: str)

        Returns:
            (是否成功, 错误详情字符串) — 失败时 detail 包含具体错误信息，成功时为空
        """
        if not self.enabled:
            logger.info("Webhook 未配置，跳过推送")
            return False, "Webhook 未配置"

        if games is None:
            games = []

        try:
            if self.type == "serverchan":
                return await self._send_serverchan(title, body, games)
            elif self.type == "telegram":
                return await self._send_telegram(title, body, games)
            else:
                logger.warning("未知的 webhook 类型: %s", self.type)
                return False, f"不支持的推送渠道类型: {self.type}"
        except Exception as e:
            logger.exception("Webhook 推送失败: %s", e)
            return False, f"推送异常: {e}"

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

    async def _send_serverchan(self, title: str, body: str, games: List[dict]) -> tuple:
        """Server 酱推送（微信推送）

        URL 格式：https://sctapi.ftqq.com/{sendkey}.send
        POST: title=...&desp=...
        """
        sendkey = self.token or self.url.rstrip("/").split("/")[-1].replace(".send", "")
        if not sendkey:
            logger.error("Server 酱配置错误：缺少 send key（设置 NOTIFY_WEBHOOK_TOKEN）")
            return False, "Server 酱配置错误：缺少 send key"

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
                    return True, ""
                detail = data.get("message", str(data))
                logger.warning("Server 酱推送失败: %s", data)
                return False, f"Server 酱返回错误: {detail}"
            logger.warning("Server 酱推送 HTTP %s: %s", resp.status_code, resp.text[:200])
            return False, f"Server 酱 HTTP {resp.status_code}: {resp.text[:200]}"

    async def _send_telegram(self, title: str, body: str, games: List[dict]) -> tuple:
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
            return False, "Telegram 配置错误：缺少 bot token 或 chat_id"

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
                    return True, ""
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
                            return True, ""
                detail = data.get("description", str(data))
                logger.warning("Telegram 推送失败: %s", data)
                return False, f"Telegram 返回错误: {detail}"
            logger.warning("Telegram 推送 HTTP %s: %s", resp.status_code, resp.text[:200])
            return False, f"Telegram HTTP {resp.status_code}: {resp.text[:200]}"

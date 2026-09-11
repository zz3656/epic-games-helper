"""
定时调度：每周五 0:05（北京时间）检查 Epic 本周免费游戏 + 推送通知

工作流程：
1. 拉取 Epic 本周免费游戏
2. 拉取下周预告
3. 对比 history.json 中上一周记录
4. 如果本周游戏有变化（新游戏 / 替换），触发 webhook 推送
5. 把本周免费游戏写入 history.json（让"每周赠送记录"区域可见）

Webhook 推送可选：
- Bark（iOS）
- Server 酱（微信）
- Telegram Bot
- 通用 Webhook

不配置 webhook 时，定时任务仍然运行，只是不会推送通知。
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config, DAY_MAP
from app.credential_store import CredentialStore
from app.epic_api import EpicAPIClient, DeviceAuthCredentials
from app.notifier import Notifier
from app.result import ClaimResult, FreeGame
from app.storage import ResultStore

logger = logging.getLogger(__name__)


class ClaimScheduler:
    """管理定时任务（周五 0:05 检查 + webhook 推送）"""

    def __init__(
        self,
        config: Config,
        store: ResultStore,
        credential_store: CredentialStore,
        auto_claim_enabled: bool = False,
    ):
        self.config = config
        self.store = store
        self.cred_store = credential_store
        self.auto_claim_enabled = auto_claim_enabled  # 已废弃，保留仅为兼容
        self.scheduler = AsyncIOScheduler(timezone=config.timezone)
        self._lock = asyncio.Lock()
        self.notifier = Notifier()
        # 上次检查的 fingerprint（用于检测游戏是否有变化）
        self._last_fingerprint: Optional[str] = None
        # 上一周的 fingerprint（从 history.json 加载）
        self._previous_fingerprint: Optional[str] = None
        # 已写入历史的当前周（避免重复写入）
        self._last_week_id: Optional[str] = None

    def start(self):
        day = DAY_MAP.get(self.config.schedule_day, "fri")
        trigger = CronTrigger(
            day_of_week=day,
            hour=self.config.schedule_hour,
            minute=self.config.schedule_minute,
            timezone=self.config.timezone,
        )
        self.scheduler.add_job(
            self._run_scheduled_job,
            trigger=trigger,
            id="epic_weekly_check",
            name="Epic 每周免费游戏检查 + 通知",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()

        # 启动时立即加载上一次 fingerprint（避免首次运行误报"新游戏"）
        self._previous_fingerprint = self._load_previous_fingerprint()
        next_run = self.scheduler.get_job("epic_weekly_check").next_run_time
        logger.info(
            "定时任务已启动：每周 %s %02d:%02d (%s) | 下次运行：%s | 通知：%s",
            day, self.config.schedule_hour, self.config.schedule_minute,
            self.config.timezone,
            next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "未知",
            "已启用" if self.notifier.enabled else "未配置 webhook",
        )

    def enable_auto_claim(self, enabled: bool):
        """已废弃：保留仅为兼容。Epic 无法通过纯 API 自动领取。"""
        self.auto_claim_enabled = enabled

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("调度器已关闭")

    def get_next_run_time(self) -> Optional[str]:
        """获取下次运行时间（用于 API 暴露给前端）"""
        job = self.scheduler.get_job("epic_weekly_check")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return None

    # ============================================
    # 定时任务主流程
    # ============================================

    async def _run_scheduled_job(self):
        """周五 0:05 触发：拉取本周免费游戏 + 检测变化 + 推送 + 写入历史"""
        if self._lock.locked():
            logger.warning("定时任务：已有任务执行中，跳过本次")
            return

        async with self._lock:
            logger.info("=" * 60)
            logger.info("⏰ 定时任务开始：检查本周 Epic 免费游戏")
            logger.info("=" * 60)

            try:
                async with EpicAPIClient() as client:
                    # 1. 拉取本周免费 + 下周预告
                    games, upcoming = await client.fetch_free_games()

                    logger.info(
                        "本周免费：%d 款 | 下周预告：%d 款",
                        len(games), len(upcoming),
                    )

                    if not games:
                        logger.warning("本周暂无免费游戏（可能 Epic API 临时故障）")
                        return

                    # 2. 计算 fingerprint（用于检测变化）
                    current_fingerprint = self._compute_fingerprint(games)

                    if current_fingerprint == self._previous_fingerprint:
                        logger.info(
                            "本周游戏与上次记录一致，无需推送通知 "
                            "(games=%s)",
                            [g.title for g in games],
                        )
                        return

                    logger.info(
                        "🆕 检测到新的免费游戏（或游戏列表变化）"
                    )

                    # 3. 写入历史记录（仅当不是同一周时写入）
                    week_id = datetime.now().strftime("%Y-W%V")
                    if week_id != self._last_week_id:
                        self._record_to_history(games, upcoming, notified=True)
                        self._last_week_id = week_id

                    # 4. 推送通知（仅当有 webhook 时）
                    if self.notifier.enabled:
                        await self._send_notification(games, upcoming)
                    else:
                        logger.info(
                            "未配置 webhook，跳过推送 "
                            "（如需推送，请配置 NOTIFY_WEBHOOK_TYPE/URL/TOKEN）"
                        )

                    # 5. 更新 fingerprint
                    self._previous_fingerprint = current_fingerprint
                    self._last_fingerprint = current_fingerprint

            except Exception as e:
                logger.exception("定时任务执行异常: %s", e)

            logger.info("=" * 60)
            logger.info("⏰ 定时任务结束")
            logger.info("=" * 60)

    # ============================================
    # 工具方法
    # ============================================

    @staticmethod
    def _compute_fingerprint(games) -> str:
        """计算本周免费游戏的 fingerprint（按 offer_id_short 排序后哈希）"""
        # 用 offer_id_short + namespace 作为唯一标识
        ids = sorted(f"{g.namespace}/{g.offer_id_short}" for g in games if g.offer_id_short)
        raw = "|".join(ids)
        return hashlib.md5(raw.encode()).hexdigest()

    def _load_previous_fingerprint(self) -> Optional[str]:
        """从 history.json 加载上一次的游戏 fingerprint

        查找最新一条 notified=True 的记录，同时获取其 week_id。
        """
        try:
            history_file = Path(self.store.file_path)
            if not history_file.exists():
                return None
            with open(history_file, "r", encoding="utf-8") as f:
                records = json.load(f)

            for record in reversed(records):
                if record.get("notified") and record.get("games"):
                    games = record.get("games", [])
                    if games:
                        ids = sorted(g.get("offer_id", "") for g in games if g.get("offer_id"))
                        if ids:
                            raw = "|".join(ids)
                            logger.info("从历史加载上一次 fingerprint：%d 款游戏", len(ids))
                            week_id = record.get("week_id")
                            if week_id:
                                self._last_week_id = week_id
                            return hashlib.md5(raw.encode()).hexdigest()
            return None
        except Exception as e:
            logger.warning("加载历史 fingerprint 失败: %s", e)
            return None

    def _record_to_history(self, games, upcoming, notified: bool):
        """把本周免费游戏（含下周预告）写入 history.json

        只保存游戏清单数据，不保存状态/消息（因为我们不自动领取，状态无意义）。

        注意：这里不判断“是否已过期”，过期判断在 /api/history 接口中按 expires_at 过滤。
        这样保留一条原始记录，便于重启后 fingerprint 对比，同时前端可以展示尚未过期的记录
        （例如本周刚开始免费的游戏在“现在免费”区与“历史赠送”区都能看到，不重复）。
        """
        started_at = datetime.now().isoformat(timespec="seconds")
        finished_at = started_at

        # 把 FreeGame 转 dict
        games_data = []
        for g in games:
            games_data.append({
                "title": g.title,
                "url": g.url,
                "offer_id": g.offer_id,
                "namespace": g.namespace,
                "offer_id_short": g.offer_id_short,
                "image_url": g.image_url,
                "description": g.description,
                "end_date": g.end_date,
                "original_price": g.original_price,
            })

        upcoming_data = []
        for u in upcoming:
            upcoming_data.append({
                "title": u.title,
                "url": u.url,
                "offer_id": u.offer_id,
                "namespace": u.namespace,
                "offer_id_short": u.offer_id_short,
                "image_url": u.image_url,
                "description": u.description,
                "end_date": u.end_date,
                "original_price": u.original_price,
            })

        # expires_at: 这条记录里所有“本周免费”游戏中最晚的 end_date。
        # 下周预告 (upcoming) 不参与，因为预告的 end_date 在更远的未来，会让记录
        # 始终不过期。上游 /api/history 过滤时依据该字段判断“是否仍在免费期”。
        expires_at = ""
        end_dates = [g.end_date for g in games if g.end_date]
        if end_dates:
            try:
                expires_at = max(end_dates)
            except Exception:
                expires_at = end_dates[0]

        # 直接构造 dict 写入 history.json（不通过 ClaimResult，避免 dataclass 限制）
        record = {
            "success": True,
            "username": "scheduler",
            "error": None,
            "started_at": started_at,
            "finished_at": finished_at,
            "screenshot_path": None,
            "notified": notified,
            "type": "weekly_check",
            "week_id": datetime.now().strftime("%Y-W%V"),
            "expires_at": expires_at,  # 本周免费游戏中最晚的 end_date（决定何时出现在历史）
            "games": games_data,
            "upcoming_games": upcoming_data,
        }

        # 用 store.add 但需绕过 dataclass 限制
        # 直接操作 deque + flush
        try:
            with self.store._lock:
                from collections import deque
                self.store._records.append(record)
                # 保留最近 100 条（避免覆盖之前的领取记录）
                if len(self.store._records) > 100:
                    # deque 已经 maxlen=50，先临时放大再收缩
                    while len(self.store._records) > 100:
                        self.store._records.popleft()
                self.store._flush()
            logger.info(
                "已写入历史：%d 款本周免费 + %d 款下周预告 (week_id=%s, notified=%s)",
                len(games_data), len(upcoming_data),
                record["week_id"], notified,
            )
        except Exception as e:
            logger.exception("写入历史失败: %s", e)

    async def _send_notification(self, games, upcoming):
        """构造推送内容并发送"""
        # 推送的 games dict 列表（限制字段避免传输过大）
        push_games = []
        for g in games:
            push_games.append({
                "title": g.title,
                "url": g.url,
                "original_price": g.original_price,
                "end_date": g.end_date,
            })

        # 标题：🎮 Epic 本周免费游戏
        title = f"🎮 Epic 本周 {len(games)} 款免费游戏"
        # 正文
        lines = [f"📅 本周免费领取（截至 {games[0].end_date[:10] if games[0].end_date else '本周结束'}）"]
        for g in games:
            price_part = f" {g.original_price} → 免费" if g.original_price else ""
            lines.append(f"• {g.title}{price_part}")
        if upcoming:
            lines.append("")
            lines.append(f"📅 下周预告：{', '.join(u.title for u in upcoming)}")
        body = "\n".join(lines)

        sent = await self.notifier.send(
            title=title,
            body=body,
            games=push_games,
            level="timeSensitive",
            icon="🎮",
        )
        if sent:
            logger.info("📲 推送通知已发送")
        else:
            logger.warning("📲 推送通知失败")


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]
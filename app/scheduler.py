"""
定时调度：每周触发自动领取（纯 API 模式）

使用 Device Auth token + Epic HTTP API，完全无浏览器、无 hCaptcha。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config, DAY_MAP
from app.credential_store import CredentialStore
from app.epic_api import EpicAPIClient, DeviceAuthCredentials, FreeGame
from app.result import ClaimResult
from app.storage import ResultStore

logger = logging.getLogger(__name__)


class ClaimScheduler:
    """管理定时任务与并发锁"""

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
        self.auto_claim_enabled = auto_claim_enabled
        self.scheduler = AsyncIOScheduler(timezone=config.timezone)
        self._lock = asyncio.Lock()
        self._last_result: Optional[Any] = None
        self._on_progress: Optional[Callable] = None

    def start(self):
        day = DAY_MAP.get(self.config.schedule_day, "thu")
        trigger = CronTrigger(
            day_of_week=day,
            hour=self.config.schedule_hour,
            minute=self.config.schedule_minute,
            timezone=self.config.timezone,
        )
        self.scheduler.add_job(
            self._run_scheduled_job,
            trigger=trigger,
            id="epic_weekly_claim",
            name="Epic 每周自动领取",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        logger.info(
            "定时任务已启动：每周 %s %02d:%02d (%s) | 自动领取: %s",
            day, self.config.schedule_hour, self.config.schedule_minute,
            self.config.timezone,
            "已启用" if self.auto_claim_enabled else "未启用",
        )

    def enable_auto_claim(self, enabled: bool):
        """开启/关闭自动领取"""
        self.auto_claim_enabled = enabled
        logger.info("自动领取已 %s", "开启" if enabled else "关闭")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("调度器已关闭")

    async def _run_scheduled_job(self):
        """定时任务入口"""
        if not self.auto_claim_enabled:
            logger.info("定时任务触发，但自动领取未启用，跳过")
            return

        device_auth = self.cred_store.load_device_auth()
        if not device_auth:
            logger.warning("定时任务触发，但未配置 device auth，跳过")
            return

        if self._lock.locked():
            logger.warning("定时任务：已有任务执行中，跳过本次")
            return

        async with self._lock:
            logger.info("定时任务：用户 DeviceAuth:%s***",
                        _mask(device_auth.account_id))
            result = await self._execute_with_device_auth(device_auth)
            self._last_result = result
            self.store.add(result)

    async def _execute_with_device_auth(
        self, credentials: DeviceAuthCredentials,
    ) -> ClaimResult:
        """使用 device auth token 通过 API 领取免费游戏（无需浏览器）"""
        started = datetime.now().isoformat(timespec="seconds")
        result = ClaimResult(
            success=False,
            username=f"DeviceAuth:{credentials.account_id[:6]}***",
            started_at=started,
        )

        try:
            async with EpicAPIClient() as client:
                # 1) 获取免费游戏列表
                await self._on_progress_callback(
                    "📦 获取本周免费游戏列表...", "active"
                )
                free_games = await client.fetch_free_games()

                if not free_games:
                    logger.info("本周暂无免费游戏")
                    result.success = True
                    result.error = "本周暂无免费游戏"
                    result.finished_at = datetime.now().isoformat(timespec="seconds")
                    await self._on_progress_callback(
                        "本周暂无免费游戏", "done"
                    )
                    return result

                await self._on_progress_callback(
                    f"发现 {len(free_games)} 款免费游戏", "done"
                )
                result.games = [
                    FreeGame(title=g.title, url=g.url, offer_id=g.offer_id)
                    for g in free_games
                ]

                # 2) 逐个领取
                for i, game in enumerate(result.games, 1):
                    await self._on_progress_callback(
                        f"🎯 领取 [{i}/{len(result.games)}]: {game.title}",
                        "active",
                    )
                    logger.info("领取游戏: %s (offer_id=%s)", game.title, game.offer_id)
                    status, message = await client.claim_game(credentials, game)

                    # 更新游戏状态
                    for fg in free_games:
                        if fg.offer_id == game.offer_id:
                            fg.status = status
                            fg.message = message
                            break

                    status_icon = "✅" if status in ("claimed", "already_claimed") else "👉" if status == "needs_manual" else "❌"
                    await self._on_progress_callback(
                        f"{status_icon} {game.title}: {message}", "done"
                    )

                # 同步游戏状态到 result
                result.games = [
                    FreeGame(title=g.title, url=g.url, offer_id=g.offer_id,
                             status=g.status, message=g.message)
                    for g in free_games
                ]

                result.success = all(
                    g.status in ("claimed", "already_claimed", "needs_manual")
                    for g in result.games
                )

        except Exception as e:
            logger.exception("Device Auth 领取流程异常")
            result.error = f"执行异常: {type(e).__name__}: {e}"
            await self._on_progress_callback(f"异常: {e}", "done")

        result.finished_at = datetime.now().isoformat(timespec="seconds")
        return result

    async def _on_progress_callback(self, step: str, status: str):
        """统一进度回调入口"""
        if self._on_progress:
            try:
                coro = self._on_progress(step, status)
                if asyncio.iscoroutine(coro):
                    await coro
            except Exception as e:
                logger.warning("进度回调失败: %s", e)


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]

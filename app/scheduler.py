"""定时调度：每周触发自动领取（支持凭证持久化模式）"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.claimer import EpicClaimer, ClaimResult
from app.config import Config, DAY_MAP
from app.credential_store import CredentialStore, StoredCredential
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
        self._last_result: Optional[ClaimResult] = None

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

    async def run_now(self, username: str, password: str) -> ClaimResult:
        """手动触发一次领取"""
        if self._lock.locked():
            return ClaimResult(
                success=False, username=username,
                error="已有任务正在执行，请稍后再试",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
        async with self._lock:
            result = await self._execute(username, password)
            self._last_result = result
            self.store.add(result)
            return result

    async def _run_scheduled_job(self):
        """定时任务入口：从凭证存储加载并执行"""
        if not self.auto_claim_enabled:
            logger.info("定时任务触发，但自动领取未启用，跳过")
            return

        cred = self.cred_store.load()
        if not cred:
            logger.warning("定时任务触发，但未配置凭证，跳过")
            return

        username = cred.username
        password = cred.password
        try:
            if self._lock.locked():
                logger.warning("定时任务：已有任务执行中，跳过本次")
                return
            async with self._lock:
                logger.info("定时任务开始：用户 %s", _mask(username))
                result = await self._execute(username, password)
                self._last_result = result
                self.store.add(result)
        finally:
            # 清空凭证引用
            cred.clear()
            username = None
            password = None

    async def _execute(self, username: str, password: str) -> ClaimResult:
        """实际执行领取流程"""
        logger.info("执行领取任务，用户: %s", _mask(username))
        try:
            async with EpicClaimer(
                headless=self.config.headless,
                screenshot_dir="/app/screenshots",
            ) as claimer:
                result = await claimer.run(username, password)
                logger.info(
                    "任务完成: success=%s, games=%d, error=%s",
                    result.success, len(result.games), result.error,
                )
                return result
        except Exception as e:
            logger.exception("任务执行异常")
            return ClaimResult(
                success=False, username=_mask(username),
                error=f"执行异常: {type(e).__name__}: {e}",
                started_at=datetime.now().isoformat(timespec="seconds"),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        finally:
            # 防御性清空
            password = None  # noqa: F841


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]
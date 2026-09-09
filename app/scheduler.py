"""
定时调度：每周触发自动领取

支持两种认证模式（自动选择）：
1. Device Auth（优先）：纯 HTTP API，无浏览器、无 hCaptcha
2. 账号密码（降级）：Playwright 自动登录 + 浏览器领取

Device Auth 流程：
- 用户在 Web UI 申请 device code
- 在任意浏览器完成 Epic 授权
- 工具获得永不过期的 device auth token
- 后续领取直接调用 Epic API
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.claimer import EpicClaimer, ClaimResult, FreeGame
from app.config import Config, DAY_MAP
from app.credential_store import CredentialStore, StoredCredential
from app.epic_api import EpicAPIClient, DeviceAuthCredentials
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

    async def run_now(self, username: str, password: str,
                       on_progress: Optional[Callable] = None,
                       verification_code: Optional[str] = None) -> ClaimResult:
        """手动触发一次领取（使用账号密码）"""
        if self._lock.locked():
            return ClaimResult(
                success=False, username=username,
                error="已有任务正在执行，请稍后再试",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
        self._on_progress = on_progress
        async with self._lock:
            result = await self._execute(username, password, verification_code=verification_code)
            self._last_result = result
            self.store.add(result)
            return result

    async def _run_scheduled_job(self):
        """定时任务入口：自动选择认证方式"""
        if not self.auto_claim_enabled:
            logger.info("定时任务触发，但自动领取未启用，跳过")
            return

        if self._lock.locked():
            logger.warning("定时任务：已有任务执行中，跳过本次")
            return

        async with self._lock:
            # 优先用 device auth（无需密码、无浏览器、无 hCaptcha）
            device_auth = self.cred_store.load_device_auth()
            if device_auth:
                logger.info("定时任务：使用 Device Auth 模式（无浏览器）")
                await self._on_progress_callback("🔑 使用 Device Auth 模式领取...", "active")
                result = await self._execute_with_device_auth(device_auth)
            else:
                # 降级到账号密码 + Playwright
                cred = self.cred_store.load()
                if not cred:
                    logger.warning("定时任务触发，但未配置任何凭证，跳过")
                    return
                username = cred.username
                password = cred.password
                try:
                    logger.info("定时任务：使用账号密码模式（Playwright）: 用户 %s", _mask(username))
                    result = await self._execute(username, password)
                finally:
                    cred.clear()

            self._last_result = result
            self.store.add(result)

    async def _execute_with_device_auth(self, credentials: DeviceAuthCredentials) -> ClaimResult:
        """使用 device auth token 通过 API 领取免费游戏（无需浏览器）"""
        started = datetime.now().isoformat(timespec="seconds")
        result = ClaimResult(
            success=False,
            username=f"DeviceAuth:{credentials.account_id[:6]}***",
            started_at=started,
        )

        try:
            async with EpicAPIClient() as client:
                # 1) 获取免费游戏列表（公开 API，无需登录）
                await self._on_progress_callback("📦 获取本周免费游戏列表...", "active")
                free_games = await client.fetch_free_games()

                if not free_games:
                    logger.info("本周暂无免费游戏")
                    result.success = True
                    result.error = "本周暂无免费游戏"
                    result.finished_at = datetime.now().isoformat(timespec="seconds")
                    await self._on_progress_callback("本周暂无免费游戏", "done")
                    return result

                await self._on_progress_callback(f"发现 {len(free_games)} 款免费游戏", "done")
                result.games = [
                    FreeGame(title=g.title, url=g.url, offer_id=g.offer_id)
                    for g in free_games
                ]

                # 2) 逐个领取
                for i, game in enumerate(result.games, 1):
                    await self._on_progress_callback(
                        f"🎯 领取 [{i}/{len(result.games)}]: {game.title}", "active"
                    )
                    logger.info("领取游戏: %s (offer_id=%s)", game.title, game.offer_id)
                    status, message = await client.claim_game(credentials, game)

                    # 更新 game 状态
                    for fg in free_games:
                        if fg.offer_id == game.offer_id:
                            fg.status = status
                            fg.message = message
                            break

                    status_icon = "✅" if status in ("claimed", "already_claimed") else "❌"
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
                    g.status in ("claimed", "already_claimed")
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

    async def _execute(self, username: str, password: str,
                         verification_code: Optional[str] = None) -> ClaimResult:
        """实际执行领取流程（Playwright 模式）"""
        logger.info("执行领取任务（Playwright 模式），用户: %s", _mask(username))
        started = datetime.now().isoformat(timespec="seconds")
        result = ClaimResult(
            success=False,
            username=_mask(username),
            started_at=started,
        )
        try:
            async with EpicClaimer(
                headless=self.config.headless,
                screenshot_dir="/app/screenshots",
                on_progress=self._on_progress,
            ) as claimer:
                result = await claimer.run(username, password, verification_code=verification_code)

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
                started_at=started,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        finally:
            password = None  # noqa: F841


def _mask(u: str) -> str:
    if not u:
        return ""
    if len(u) <= 2:
        return "*" * len(u)
    return u[0] + "*" * (len(u) - 2) + u[-1]

"""配置管理 - 仅从环境变量读取调度相关配置，绝不读取账号密码"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # 调度配置
    schedule_day: str       # mon/tue/wed/thu/fri/sat/sun
    schedule_hour: int      # 0-23
    schedule_minute: int    # 0-59
    timezone: str           # 时区

    # 浏览器配置
    headless: bool

    # 日志级别
    log_level: str

    # Epic Games 相关 URL
    epic_store_url: str = "https://store.epicgames.com/zh-CN/free-games"
    epic_login_url: str = "https://www.epicgames.com/id/login"

    # 任务互斥：单实例运行
    max_concurrent_jobs: int = 1


def load_config() -> Config:
    return Config(
        # Epic Games 免费游戏在 北京时间每周五 0:00 更新
        # 设为周五 0:05 避开高峰期
        schedule_day=os.getenv("SCHEDULE_DAY", "fri").lower(),
        schedule_hour=int(os.getenv("SCHEDULE_HOUR", "0")),
        schedule_minute=int(os.getenv("SCHEDULE_MINUTE", "5")),
        timezone=os.getenv("TZ", "Asia/Shanghai"),
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )


# 周几字符串 -> APScheduler 内部 day_of_week
DAY_MAP = {
    "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
    "fri": "fri", "sat": "sat", "sun": "sun",
}

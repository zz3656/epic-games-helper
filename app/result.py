"""
领取结果数据模型（从 claimer.py 拆出）
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class FreeGame:
    """免费游戏"""
    title: str
    url: str
    offer_id: str = ""
    status: str = "pending"
    message: str = ""


@dataclass
class ClaimResult:
    """领取结果"""
    success: bool
    username: str  # 脱敏后的用户名（仅用于日志展示）
    games: List[FreeGame] = field(default_factory=list)
    error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    screenshot_path: Optional[str] = None
    login_status: str = ""

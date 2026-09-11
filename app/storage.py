"""
仅持久化领取结果（不含账号密码）的存储模块

账号密码永远不进入此存储。
"""
import json
import logging
import os
import threading
from collections import deque
from typing import List

from app.result import ClaimResult

logger = logging.getLogger(__name__)

MAX_RECORDS = 50  # 最多保留最近 50 条结果


class ResultStore:
    """线程/协程安全的内存 + 文件记录器

    注意：写入文件时使用自定义 to_safe_dict()，确保不会意外写入敏感字段。
    """

    def __init__(self, file_path: str = "/app/logs/history.json"):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._records: deque = deque(maxlen=MAX_RECORDS)
        self._load()

    def _load(self):
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                self._records.append(item)
        except Exception as e:
            logger.warning("加载历史记录失败: %s", e)

    def add(self, result: ClaimResult):
        record = self._to_safe_dict(result)
        with self._lock:
            self._records.append(record)
            self._flush()

    def list(self) -> List[dict]:
        with self._lock:
            return list(self._records)

    def latest(self) -> dict:
        with self._lock:
            if not self._records:
                return {}
            return self._records[-1]

    def _flush(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(list(self._records), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存历史记录失败: %s", e)

    @staticmethod
    def _to_safe_dict(result: ClaimResult) -> dict:
        """显式白名单字段，绝不序列化任何密码相关属性

        注意：游戏对象的所有展示字段（封面/描述/价格/时间等）都需要保留，
        否则前端历史记录页面无法正确渲染封面和介绍。
        """
        return {
            "success": result.success,
            "username": result.username,   # 已被脱敏
            "error": result.error,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "screenshot_path": result.screenshot_path,
            "games": [
                {
                    "title": g.title,
                    "url": g.url,
                    "offer_id": g.offer_id,
                    "offer_id_short": getattr(g, "offer_id_short", ""),
                    "namespace": getattr(g, "namespace", ""),
                    "image_url": getattr(g, "image_url", ""),
                    "description": getattr(g, "description", ""),
                    "start_date": getattr(g, "start_date", ""),
                    "end_date": getattr(g, "end_date", ""),
                    "original_price": getattr(g, "original_price", ""),
                    "status": g.status,
                    "message": g.message,
                }
                for g in result.games
            ],
        }

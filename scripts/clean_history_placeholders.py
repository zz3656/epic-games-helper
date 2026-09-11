#!/usr/bin/env python3
"""
清理 history.json 中的占位符数据

历史背景：
- 早期版本的代码没有把 image_url / description 写入 history.json，
  导致历史记录里 image_url 是空字符串，description 是 "已赠送 · 历史免费游戏" 这种占位符。
- Epic 公开 API 不提供已结束活动的历史游戏元数据，所以无法回填。
- 本脚本只清理明显的占位符描述，避免显示无语义文案。

用法：
    python scripts/clean_history_placeholders.py
"""
import json
import os
import re
import sys
from pathlib import Path

# 项目根目录（脚本所在目录的父目录）
ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "history.json"

# 占位描述正则（与前端 cleanDescription 保持一致）
PLACEHOLDER_DESC_RE = re.compile(
    r"^(已赠送[\s\S]*历史[\s\S]*免费[\s\S]*|历史[\s\S]*免费[\s\S]*游戏?)$",
    re.IGNORECASE,
)


def clean_description(desc: str) -> str:
    if not desc:
        return ""
    s = str(desc).strip()
    if not s:
        return ""
    if PLACEHOLDER_DESC_RE.match(s):
        return ""
    return s


def main():
    if not HISTORY_FILE.exists():
        print(f"❌ 找不到历史文件: {HISTORY_FILE}")
        return 1

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"📊 共 {len(records)} 条历史记录")

    total_games = 0
    placeholder_cleaned = 0
    image_url_missing = 0

    for rec in records:
        games = rec.get("games", [])
        for g in games:
            total_games += 1
            old_desc = g.get("description", "")
            new_desc = clean_description(old_desc)
            if old_desc != new_desc:
                g["description"] = new_desc
                placeholder_cleaned += 1
            if not g.get("image_url"):
                image_url_missing += 1

        upcoming = rec.get("upcoming_games", [])
        for u in upcoming:
            total_games += 1
            old_desc = u.get("description", "")
            new_desc = clean_description(old_desc)
            if old_desc != new_desc:
                u["description"] = new_desc
                placeholder_cleaned += 1
            if not u.get("image_url"):
                image_url_missing += 1

    # 备份
    backup_path = HISTORY_FILE.with_suffix(".json.bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"💾 备份已保存: {backup_path}")

    # 写回
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"✅ 已清理 {placeholder_cleaned} 条占位符描述（剩余 {total_games - placeholder_cleaned} 条真实描述）")
    print(f"⚠️  仍有 {image_url_missing} 个游戏缺少封面（Epic 不提供历史数据，前端将显示渐变文字封面）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

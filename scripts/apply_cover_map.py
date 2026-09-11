#!/usr/bin/env python3
"""
将 cover_map.json 回填到 history.json

从 cover_map.json 读取匹配好的封面图和描述，
更新 history.json 中对应游戏的 image_url 和 description。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "history.json"
COVER_MAP_FILE = ROOT / "logs" / "cover_map.json"


def main():
    if not COVER_MAP_FILE.exists():
        print(f"❌ 找不到映射文件: {COVER_MAP_FILE}")
        return 1
    
    if not HISTORY_FILE.exists():
        print(f"❌ 找不到历史文件: {HISTORY_FILE}")
        return 1
    
    with open(COVER_MAP_FILE, "r", encoding="utf-8") as f:
        cover_map = json.load(f)
    
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    
    print(f"📊 映射文件包含 {len(cover_map)} 个游戏的封面和描述")
    
    updated = 0
    for rec in records:
        for g in rec.get("games", []):
            title = g.get("title", "")
            if title in cover_map:
                old_desc = g.get("description", "")
                old_img = g.get("image_url", "")
                new_img = cover_map[title]["thumbnail"]
                new_desc = cover_map[title]["description"]
                
                if new_img and not old_img:
                    g["image_url"] = new_img
                    updated += 1
                if new_desc and not old_desc:
                    g["description"] = new_desc
                    # 不计数 description 更新，因为历史清理脚本已经清空了
        
        # 也更新 upcoming_games
        for u in rec.get("upcoming_games", []):
            title = u.get("title", "")
            if title in cover_map:
                new_img = cover_map[title]["thumbnail"]
                new_desc = cover_map[title]["description"]
                if new_img and not u.get("image_url"):
                    u["image_url"] = new_img
                    updated += 1
                if new_desc and not u.get("description"):
                    u["description"] = new_desc
    
    # 备份
    backup = HISTORY_FILE.with_suffix(".json.bak2")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"💾 备份已保存: {backup}")
    
    # 写回
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 回填完成: 更新了 {updated} 个游戏的封面图")
    
    # 验证
    with_opening = sum(1 for rec in records for g in rec.get("games", []) if g.get("image_url"))
    with_desc = sum(1 for rec in records for g in rec.get("games", []) if g.get("description"))
    total = sum(len(rec.get("games", [])) for rec in records)
    print(f"📊 验证: {total} 个游戏记录")
    print(f"  有封面图: {with_opening} / {total} ({with_opening * 100 // total}%)")
    print(f"  有描述:   {with_desc} / {total} ({with_desc * 100 // total}%)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

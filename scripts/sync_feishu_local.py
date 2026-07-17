"""飞书 → 本地同步：把飞书多维表格里的导师/学生真实数据，快照成本地 JSON
（与 data/mentors.json / students.json 同格式），供离线演示 / 真实数据调试。

写入 data/real_mentors.json / data/real_students.json（不覆盖 mock 假数据）。
这两个文件已加入 .gitignore，不会进 Git（含真实导师画像/行业/城市，勿提交）。

用法：
    python scripts/sync_feishu_local.py
"""
from __future__ import annotations
import dataclasses
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # AI_CAMP 根
sys.path.insert(0, HERE)

from matching.loader import FeishuLoader

CONFIG_DIR = os.path.join(HERE, "config")
DATA_DIR = os.path.join(HERE, "data")


def _load_cfg():
    with open(os.path.join(CONFIG_DIR, "feishu.json"), encoding="utf-8") as f:
        return json.load(f)


def _dump(objs, path):
    # dataclass → dict，结构与 data/mentors.json 天然对齐，LocalLoader 可直接读回
    with open(path, "w", encoding="utf-8") as f:
        json.dump([dataclasses.asdict(o) for o in objs], f, ensure_ascii=False, indent=2)


def main():
    cfg = _load_cfg()
    fl = FeishuLoader(cfg["app_id"], cfg["app_secret"], cfg["tables"], cfg.get("base_url", ""))

    mentors = fl.load_mentors()
    students = fl.load_students()

    mp = os.path.join(DATA_DIR, "real_mentors.json")
    sp = os.path.join(DATA_DIR, "real_students.json")
    _dump(mentors, mp)
    _dump(students, sp)

    print("已同步飞书真实数据到本地快照：")
    print("  导师 %d 位 → %s" % (len(mentors), os.path.relpath(mp, HERE)))
    print("  学生 %d 位 → %s" % (len(students), os.path.relpath(sp, HERE)))
    if fl.mentor_missing_columns:
        print("  ⚠️ 飞书导师表缺列：%s（地区维度已用城市兜底，建议补列）"
              % "、".join(fl.mentor_missing_columns))
    print("（real_*.json 已 gitignore，不会进 Git）")


if __name__ == "__main__":
    main()

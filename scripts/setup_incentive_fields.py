"""给飞书导师表加激励体系字段（幂等：已存在的列自动跳过）。

新增 4 列（NUMBER=2）：
  累计服务学生数 / 好评率 / 组织贡献分 / 当前星级
（"累计服务时长"暂不加——加载时回退已有的"已用时长"列。）

运行：python scripts/setup_incentive_fields.py
"""
from __future__ import annotations
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # AI_CAMP 根
sys.path.insert(0, HERE)

from matching.loader import FeishuLoader  # noqa: E402

# (列名, 飞书字段类型)  类型：2=NUMBER
FIELDS = [
    ("累计服务学生数", 2),
    ("好评率", 2),
    ("组织贡献分", 2),
    ("当前星级", 2),
]


def main():
    cfg = json.load(open(os.path.join(HERE, "config", "feishu.json"), encoding="utf-8"))
    fl = FeishuLoader(cfg["app_id"], cfg["app_secret"], cfg["tables"], cfg.get("base_url", ""))
    t = cfg["tables"]["mentor"]
    at, tid = t["app_token"], t["table_id"]

    existing = set(fl._field_types(at, tid).keys())
    print("导师表现有列 %d 个。" % len(existing))
    for name, ftype in FIELDS:
        if name in existing:
            print("  · 跳过（已存在）：%s" % name)
            continue
        ok = fl._ensure_field(at, tid, name, ftype)
        print(("  ✅ 已添加：%s" if ok else "  ❌ 失败：%s") % name)
    print("完成。运营现在可在飞书导师表里填：累计服务学生数 / 好评率 / 组织贡献分。")


if __name__ == "__main__":
    main()

"""把飞书三个多维表格的字段结构对齐软件现状（幂等：已存在的列自动跳过）。

- 导师表：补激励(5)+招募(3)=8 列
    累计服务时长 / 累计服务学生数 / 好评率 / 组织贡献分 / 当前星级
    资质类型 / 毕业院校 / 工作年限
- 匹配表：补各维度得分列（行业/需求/服务/地区/性格/画像 得分）
- 学生表：检查核心字段是否齐全（应已齐）

运行：python scripts/sync_feishu_schema.py
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

from matching.loader import FeishuLoader, DIM_SHORT  # noqa: E402

# (列名, 飞书字段类型)  类型: 1=文本, 2=数字
MENTOR_ADD = [
    ("累计服务时长", 2), ("累计服务学生数", 2), ("好评率", 2),
    ("组织贡献分", 2), ("当前星级", 2),
    ("资质类型", 1), ("毕业院校", 1), ("工作年限", 2),
    ("所在机构", 1), ("服务状态", 1), ("导师级别", 1),
]
MATCH_ADD = [(label + "得分", 2) for label in DIM_SHORT.values()]  # 行业得分/需求得分…
STUDENT_EXPECTED = ["学生ID", "年级", "地区", "性别", "感兴趣方向", "需求类型",
                    "性格", "要求同性别", "要求同地区", "紧迫度"]


def ensure_fields(fl, kind, fields):
    t = fl.tables[kind]
    at, tid = t["app_token"], t["table_id"]
    existing = set(fl._field_types(at, tid).keys())
    added = 0
    for name, ftype in fields:
        if name in existing:
            print("  · 已存在，跳过：%s" % name)
            continue
        ok = fl._ensure_field(at, tid, name, ftype)
        print(("  ✅ 已添加：%s" if ok else "  ❌ 失败：%s") % name)
        added += 1 if ok else 0
    print("  小结：新增 %d 列，现有共 %d 列" % (added, len(existing) + added))


def main():
    cfg = json.load(open(os.path.join(HERE, "config", "feishu.json"), encoding="utf-8"))
    fl = FeishuLoader(cfg["app_id"], cfg["app_secret"], cfg["tables"], cfg.get("base_url", ""))

    print("[导师表] 补激励 + 招募字段：")
    ensure_fields(fl, "mentor", MENTOR_ADD)

    print("\n[匹配结果表] 补各维度得分列：")
    ensure_fields(fl, "match", MATCH_ADD)

    print("\n[学生表] 检查核心字段：")
    t = fl.tables["student"]
    existing = set(fl._field_types(t["app_token"], t["table_id"]).keys())
    missing = [f for f in STUDENT_EXPECTED if f not in existing]
    if missing:
        print("  ⚠️ 缺失：", "、".join(missing))
    else:
        print("  ✅ 核心字段齐全（%d 列）" % len(existing))
    print("\n完成。导师表现可在飞书填写：累计服务时长 / 好评率 / 组织贡献分 / 资质类型 等激励与招募字段。")


if __name__ == "__main__":
    main()

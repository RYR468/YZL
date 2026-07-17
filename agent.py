"""益志领 · 学生↔导师匹配 MVP —— 端到端 CLI。

用法：
    python agent.py                       # 跑全部学生，每个返回 Top5
    python agent.py --student S001       # 只跑指定学生
    python agent.py --top 3 --out matches_output.json   # Top3 并把结果写入文件（仿 matches 表 schema）
    python agent.py --llm              # 用 LLM 生成匹配理由（需 OPENAI_API_KEY / OPENAI_MODEL 环境变量）
"""
from __future__ import annotations
import argparse
import json
import os
import sys

# 让中文输出在 Windows 控制台（默认 GBK）不报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from matching.config import load_config
from matching.loader import LocalLoader
from matching.dimensions import Dimensions
from matching.filters import HardFilter
from matching.scoring import Scorer
from matching.reason import template_reason, llm_reason


def run_match(student, mentors, dims, hardfilter, scorer, top_n, use_llm):
    """对单个学生：硬过滤 → 加权打分 → 取 Top-N → 生成理由。返回结果列表。"""
    candidates = [m for m in mentors if hardfilter.passes(m, student)]
    scored = [(m, scorer.score(m, student)) for m in candidates]
    scored.sort(key=lambda x: x[1]["total"], reverse=True)
    results = []
    for rank, (m, subs) in enumerate(scored[:top_n], 1):
        reason = llm_reason(m, student, subs) if use_llm else template_reason(m, student, subs)
        results.append({
            "rank": rank,
            "mentor_id": m.mentor_id,
            "scores": subs,
            "reason": reason,
        })
    return results


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="益志领 · 学生↔导师匹配 MVP")
    ap.add_argument("--student", help="指定学生ID（不指定则跑全部）")
    ap.add_argument("--top", type=int, default=5, help="每个学生返回的 Top-N 导师数（默认 5）")
    ap.add_argument("--data-dir", default=os.path.join(here, "data"))
    ap.add_argument("--config-dir", default=os.path.join(here, "config"))
    ap.add_argument("--out", help="把结果写入该 JSON 文件（仿 matches 表 schema）")
    ap.add_argument("--llm", action="store_true", help="用 LLM 生成匹配理由")
    args = ap.parse_args()

    weights = load_config("weights", args.config_dir)
    hard_cfg = load_config("hard_filters", args.config_dir)
    synonyms = load_config("synonyms", args.config_dir)

    loader = LocalLoader(args.data_dir)
    mentors = loader.load_mentors()
    students = loader.load_students()

    if args.student:
        students = [s for s in students if s.student_id == args.student]
        if not students:
            print("未找到学生 " + args.student)
            return

    dims = Dimensions(synonyms)
    hardfilter = HardFilter(hard_cfg, synonyms)
    scorer = Scorer(weights, dims)

    all_results = {}
    for s in students:
        matches = run_match(s, mentors, dims, hardfilter, scorer, args.top, args.llm)
        all_results[s.student_id] = {
            "student": {
                "grade": s.grade, "region": s.region, "gender": s.gender,
                "interested_fields": s.interested_fields, "needs": s.needs, "personality": s.personality,
            },
            "matches": matches,
        }

    # ---- 控制台输出 ----
    for sid, payload in all_results.items():
        info = payload["student"]
        fields = "、".join(info["interested_fields"]) if info["interested_fields"] else "不限"
        print("")
        print("=" * 100)
        print("学生 " + sid + " | " + info["grade"] + " | " + info["region"] + " | "
              + info["gender"] + " | 需求：" + "、".join(info["needs"]) + " | 意向：" + fields)
        print("-" * 100)
        if not payload["matches"]:
            print("  （无合格导师通过硬过滤）")
            continue
        for r in payload["matches"]:
            sc = r["scores"]
            line = "#{rank:<2} {mentor_id:<8} 总分 {total:<6.2f} | 行业 {industry:.2f} 需求 {need:.2f} 服务 {service:.2f} 地区 {region:.2f} 性格 {personality:.2f} 画像 {profile:.2f}".format(
                rank=r["rank"], mentor_id=r["mentor_id"], total=sc["total"],
                industry=sc["industry"], need=sc["need"], service=sc["service"],
                region=sc["region"], personality=sc["personality"], profile=sc["profile"])
            print(line)
            print("   → " + r["reason"])

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print("\n结果已写入 " + args.out)


if __name__ == "__main__":
    main()

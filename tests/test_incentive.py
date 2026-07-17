from __future__ import annotations
"""导师级别评定测试（L1/L2/L3）。直接运行：python tests/test_incentive.py"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # AI_CAMP 根
sys.path.insert(0, HERE)

from matching.config import load_config  # noqa: E402
from matching.models import Mentor  # noqa: E402
from matching.incentive import compute_level, compute_score  # noqa: E402

CFG = load_config("incentive", os.path.join(HERE, "config"))


def _m(**kw):
    base = dict(mentor_id="X")
    base.update(kw)
    return Mentor(**base)


def test_no_service_unrated():
    """无任何服务记录 → 未评定。"""
    level, name, _ = compute_level(_m(), CFG)
    assert level == "" and name == "未评定"


def test_L1_newcomer():
    """少量服务、无贡献、综合分低 → L1 新锐。"""
    m = _m(total_hours=20, total_students=2, rating=6)  # 综合约 28
    level, name, sc = compute_level(m, CFG)
    assert level == "L1" and name == "新锐导师", (level, sc)


def test_L2_senior_with_contribution():
    """综合分≥60 且有深度贡献 → L2 资深。"""
    m = _m(total_hours=120, total_students=10, rating=8, org_score=20)  # 综合约 64
    level, name, sc = compute_level(m, CFG)
    assert level == "L2" and name == "资深导师", (level, sc)


def test_L3_requires_excellent_contribution():
    """综合分够 L3 但深度贡献 < 30 → 不能 L3（降到 L2）。"""
    m = _m(total_hours=180, total_students=16, rating=9.5, org_score=15)  # 综合 80 但 org<30
    level, name, sc = compute_level(m, CFG)
    assert level != "L3", "贡献不够不应 L3，实际 %s（%s）" % (level, sc)


def test_L3_chief_full():
    """综合分高 + 卓越贡献 → L3 首席。"""
    m = _m(total_hours=200, total_students=16, rating=9.6, org_score=50)
    level, name, sc = compute_level(m, CFG)
    assert level == "L3" and name == "首席导师", (level, name, sc)


def test_score_weights():
    """综合分 = 时长40% + 质量40% + 贡献20%。"""
    m = _m(total_hours=200, rating=10, org_score=50)  # 三项全满分
    sc = compute_score(m, CFG)
    assert sc["hours"] == 100.0 and sc["quality"] == 100.0 and sc["contribution"] == 100.0
    assert abs(sc["total"] - 100.0) < 0.1


def test_fallback_to_used_hours():
    """total_hours 未登记回退 used_hours。"""
    m = _m(used_hours=100, total_hours=0, current_students=3, total_students=0)
    sc = compute_score(m, CFG)
    assert sc["hours"] == 50.0  # 100/200*100


# ---- 简易运行器 ----
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print("PASS", t.__name__)
        passed += 1
    print("\n%d/%d passed" % (passed, len(tests)))

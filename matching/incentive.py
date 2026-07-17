"""导师级别评定（L1/L2/L3，发展与赋能体系）。

综合评估分（0-100）= 服务时长 40% + 服务质量 40% + 深度贡献 20%。
级别：
  L3 首席：综合分 ≥ 80 且 深度贡献 ≥ 30（卓越贡献）
  L2 资深：综合分 ≥ 60 且 有深度贡献
  L1 新锐：其余有服务记录者
规则外置在 config/incentive.json，运营可调。

用法：
    from matching.config import load_config
    from matching.incentive import compute_level
    cfg = load_config("incentive", "config")
    level, level_name, score = compute_level(mentor, cfg)
"""
from __future__ import annotations
from typing import Dict, Tuple
from .models import Mentor


def _effective_hours(m: Mentor) -> int:
    """累计服务时长；未登记(total_hours=0)则回退到 used_hours。"""
    return m.total_hours or m.used_hours


def _effective_students(m: Mentor) -> int:
    """累计服务学生数；未登记则回退到 current_students。"""
    return m.total_students or m.current_students


def _dim_score(value: float, full: float) -> float:
    """单维度归一化到 0-100。"""
    if full <= 0:
        return 0.0
    return min(100.0, value / full * 100.0)


def compute_score(m: Mentor, cfg: dict) -> Dict[str, float]:
    """综合评估分 0-100 = 时长×40% + 质量×40% + 贡献×20%。返回各维度分 + 总分。"""
    cfg = cfg or {}
    w = cfg.get("weights", {"hours": 0.4, "quality": 0.4, "contribution": 0.2})
    full = cfg.get("full_scale", {"hours": 200, "rating": 10, "org": 50})
    hours = _dim_score(_effective_hours(m), full.get("hours", 200))
    quality = _dim_score(m.rating, full.get("rating", 10))      # rating 1-10 分
    contrib = _dim_score(m.org_score, full.get("org", 50))
    total = (hours * w.get("hours", 0.4)
             + quality * w.get("quality", 0.4)
             + contrib * w.get("contribution", 0.2))
    return {
        "hours": round(hours, 1),
        "quality": round(quality, 1),
        "contribution": round(contrib, 1),
        "total": round(total, 1),
    }


def compute_level(m: Mentor, cfg: dict) -> Tuple[str, str, float]:
    """返回 (level, level_name, 综合分)。
    L3 须综合≥80 且 org≥30；L2 须综合≥60 且 org>0；L1 为其余有服务者；无服务则未评定。"""
    cfg = cfg or {}
    sc = compute_score(m, cfg)
    total = sc["total"]
    th = cfg.get("level_thresholds", {"L3_score": 80, "L3_org": 30, "L2_score": 60})
    names = cfg.get("level_names", {"L1": "新锐导师", "L2": "资深导师", "L3": "首席导师"})
    has_service = _effective_hours(m) > 0 or _effective_students(m) > 0
    if not has_service:
        return "", "未评定", total
    if total >= th.get("L3_score", 80) and m.org_score >= th.get("L3_org", 30):
        return "L3", names.get("L3", "首席导师"), total
    if total >= th.get("L2_score", 60) and m.org_score > 0:
        return "L2", names.get("L2", "资深导师"), total
    return "L1", names.get("L1", "新锐导师"), total

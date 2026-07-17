from __future__ import annotations
from .models import Mentor, Student
from .dimensions import _contains_any


class HardFilter:
    """硬过滤：不达标的导师直接剔除，不进入打分。规则在 hard_filters.json 里可调。"""

    def __init__(self, config: dict, synonyms: dict):
        self.cfg = config or {}
        self.need_to_topics = (synonyms or {}).get("need_to_topics", {})

    def passes(self, m: Mentor, s: Student) -> bool:
        c = self.cfg

        # 1) 容量：剩余名额 > 0
        if c.get("capacity") and m.free_slots <= 0:
            return False

        # 2) 同性别偏好
        if c.get("same_gender") and s.prefer_same_gender and m.gender != s.gender:
            return False

        # 3) 同地区偏好
        if c.get("same_region") and s.prefer_same_region:
            regs = [r for r in ([m.city] + list(m.expected_regions)) if r]
            if not any(s.region in r or r in s.region for r in regs):
                return False

        # 4) 至少覆盖学生 N 个需求，避免完全无关
        min_cov = int(c.get("min_need_coverage", 0) or 0)
        if min_cov > 0:
            topics_text = " ".join(m.teach_topics)
            cov = sum(
                1 for need in s.needs
                if _contains_any(topics_text, self.need_to_topics.get(need, [need]))
            )
            if cov < min_cov:
                return False

        # 5) 招募资质：导师须满足招募条件之一（招募令第6条），默认关
        if c.get("require_qualification") and not m.qualification:
            return False

        return True

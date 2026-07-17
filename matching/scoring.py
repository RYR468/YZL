from __future__ import annotations
from typing import Dict
from .models import Mentor, Student
from .dimensions import Dimensions


class Scorer:
    """加权打分：score = Σ(权重 × 子匹配度)，按权重总和归一化。"""

    # 参与打分的维度顺序（决定输出列顺序）
    DIMS = ["industry", "need", "service", "region", "personality", "profile"]

    def __init__(self, weights: dict, dims: Dimensions):
        self.weights = weights or {}
        self.dims = dims

    def _sub_scores(self, m: Mentor, s: Student) -> Dict[str, float]:
        return {
            "industry": self.dims.industry(m, s),
            "need": self.dims.need(m, s),
            "service": self.dims.service(m, s),
            "region": self.dims.region(m, s),
            "personality": self.dims.personality(m, s),
            "profile": self.dims.profile(m, s),
        }

    def score(self, m: Mentor, s: Student) -> Dict[str, float]:
        raw = self._sub_scores(m, s)
        wsum = sum(self.weights.get(k, 0) for k in self.DIMS)
        total = sum(self.weights.get(k, 0) * v for k, v in raw.items())
        if wsum > 0:
            total = total / wsum
        out = {k: round(v, 3) for k, v in raw.items()}
        out["total"] = round(total, 4)
        return out

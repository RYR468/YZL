from __future__ import annotations
from typing import Iterable
from .models import Mentor, Student


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    """text 中是否出现任一关键词（子串匹配）。"""
    text = text or ""
    return any(k and k in text for k in keywords)


class Dimensions:
    """计算各维度的 0~1 子匹配度。权重在 Scorer 里配置。"""

    def __init__(self, synonyms: dict):
        self.syn = synonyms or {}
        # 行业反向索引：同义词 -> 规范组名（找不到的词以其自身为组名，兼顾字面匹配）
        self.industry_index: dict = {}
        for group, words in self.syn.get("industry_groups", {}).items():
            for w in words:
                self.industry_index[w] = group
        self.need_to_topics: dict = self.syn.get("need_to_topics", {})
        self.need_to_services: dict = self.syn.get("need_to_services", {})

    def _group(self, token: str) -> str:
        return self.industry_index.get(token, token)

    # ---- 各维度 ----

    def industry(self, m: Mentor, s: Student) -> float:
        """行业/专业方向契合：学生的感兴趣方向与导师行业/专精的组别重叠率。"""
        m_groups = {self._group(t) for t in [m.industry, *m.expertise] if t}
        s_groups = {self._group(f) for f in s.interested_fields if f}
        if not s_groups:
            return 0.0
        hit = len(m_groups & s_groups)
        return hit / len(s_groups)

    def need(self, m: Mentor, s: Student) -> float:
        """能力-需求契合：导师擅长主题能覆盖学生需求的比例。"""
        if not s.needs:
            return 0.0
        topics_text = " ".join(m.teach_topics)
        covered = sum(
            1 for need in s.needs
            if _contains_any(topics_text, self.need_to_topics.get(need, [need]))
        )
        return covered / len(s.needs)

    def service(self, m: Mentor, s: Student) -> float:
        """服务类型匹配：学生需求所隐含的服务，导师愿意提供的比例。"""
        if not s.needs:
            return 0.0
        needed = []
        for need in s.needs:
            for sv in self.need_to_services.get(need, []):
                if sv not in needed:
                    needed.append(sv)
        if not needed:
            return 0.0
        covered = sum(1 for sv in needed if sv in m.service_types)
        return covered / len(needed)

    def region(self, m: Mentor, s: Student) -> float:
        """地区/偏好：导师期望区域覆盖学生地区 → 1.0；填了但不覆盖 → 0.3；
        未填期望区域时用常住城市兜底（见 _region_fallback），避免该维度退化为常数。"""
        if m.expected_regions:
            for r in m.expected_regions:
                if s.region in r or r in s.region:
                    return 1.0
            return 0.3
        return self._region_fallback(m, s)

    def _region_fallback(self, m: Mentor, s: Student) -> float:
        """导师未填「期望辅导区域」时的城市兜底：同省/字面同域给 0.8，否则 0.5。
        用 synonyms.city_to_region 把导师城市归一到省，再与学生地区（如「四川县城」）
        做省名子串匹配。用于飞书导师表缺「期望辅导区域」列时恢复地区维度的区分度。"""
        city_map = self.syn.get("city_to_region", {})
        m_prov = city_map.get(m.city, "")
        s_region = s.region or ""
        s_prov = next((p for p in set(city_map.values()) if p and p in s_region), "")
        if m_prov and s_prov and m_prov == s_prov:
            return 0.8
        if m.city and (m.city in s_region or s_region in m.city):
            return 0.8
        return 0.5

    def personality(self, m: Mentor, s: Student) -> float:
        """性格（权重低）：老师认为性格不重要。"""
        if "外向" in m.tags and s.personality == "内向":
            return 0.8   # 外向导师带动内向学生
        if s.personality == "内向" and "内向" in m.tags:
            return 0.6   # 两个 I 人互相理解
        return 0.5

    def profile(self, m: Mentor, s: Student) -> float:
        """画像软契合：学生派生标签（意向+需求）与导师画像标签的重叠率。"""
        s_tags = set(s.interested_fields) | set(s.needs)
        if not s_tags:
            return 0.0
        hit = len(set(m.tags) & s_tags)
        return min(1.0, hit / len(s_tags))

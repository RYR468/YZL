"""导师自助招募 —— 规则初筛与入库辅助。

招募硬标准(《招募令》第6条):全球 Top100 院校毕业 或 世界500强中高层 或 优秀创业者。
本模块做规则初筛(快、可解释、零依赖);LLM 评语可选,由 app 层在配了 key 时叠加。
"""
from __future__ import annotations
from .loader import mentor_from_cn, _scalar
from .models import Mentor

# 必填字段(导师ID 允许空,自动生成)
REQUIRED = ["性别", "常住城市", "行业"]

# 资质命中关键词(写在「资质类型」或「毕业院校」里即视为符合硬标准)
QUAL_PASS_KEYS = ["500强", "前100", "top100", "百强", "创业", "高管", "中高层",
                  "资深", "总监", "经理", "首席", "合伙人", "总裁", "vice", "教授", "博士", "院士"]
TOP100_SCHOOLS = ["清华", "北京大学", "北大", "复旦", "上海交通", "交大", "浙江", "浙大",
                  "南京大学", "中科大", "中国科技", "哈工大", "西安交大", "武汉大学", "华科",
                  "牛津", "cambridge", "剑桥", "harvard", "哈佛", "mit", "麻省",
                  "stanford", "斯坦福", "yale", "耶鲁", "princeton", "普林斯顿"]


def screen(form: dict) -> dict:
    """规则初筛。返回 {result, reasons, missing, qualification_ok}。

    result:
      pass   —— 信息齐全且资质符合名校/500强/资深标准,自动入库
      review —— 信息不全,或资质需人工复核
      reject —— 无招募资质
    """
    missing = [k for k in REQUIRED if not str(_scalar(form.get(k))).strip()]
    qual = str(_scalar(form.get("资质类型"))).strip()
    school = str(_scalar(form.get("毕业院校"))).strip()
    text = (qual + " " + school).lower()

    qual_hit = any(k.lower() in text for k in QUAL_PASS_KEYS)
    school_hit = any(k.lower() in text for k in TOP100_SCHOOLS)
    has_qual = bool(qual) or bool(school)

    if missing:
        return {"result": "review", "missing": missing,
                "reasons": ["关键信息缺失：" + "、".join(missing) + ",请补充后重新提交。"],
                "qualification_ok": has_qual}
    reasons = []
    if school_hit:
        reasons.append("✓ 毕业院校符合全球知名院校标准。")
    if qual_hit:
        reasons.append("✓ 资质类型符合名校 / 500强 / 资深专家招募标准。")
    if qual_hit or school_hit:
        reasons.append("自动初筛通过,已入库并进入导师池。")
        return {"result": "pass", "missing": [], "reasons": reasons, "qualification_ok": True}
    if has_qual:
        return {"result": "review", "missing": [],
                "reasons": ["已提供资质信息,但未能自动判定是否符合名校 / 500强硬标准,转人工复核。"],
                "qualification_ok": False}
    return {"result": "reject", "missing": [],
            "reasons": ["未体现名校毕业或 500强 / 资深专家等招募资质,暂不符合入库硬标准。"],
            "qualification_ok": False}


def form_to_mentor(form: dict, seq: int) -> Mentor:
    """报名表单(中文 key)→ Mentor。导师ID 缺则自动生成 R###,默认可辅导人数 3。"""
    f = dict(form)
    if not str(_scalar(f.get("导师ID"))).strip():
        f["导师ID"] = "R%03d" % seq
    m = mentor_from_cn(f)
    if m.max_students <= 0:
        m.max_students = 3
    return m

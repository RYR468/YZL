from __future__ import annotations
"""匹配引擎单元测试。

本环境无法联网装 pytest，所以同时提供「直接 python 运行」的简易运行器：
    python tests/test_matching.py
装了 pytest 也可用：
    python -m pytest -q tests/
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../AI CAMP
sys.path.insert(0, HERE)

from matching.config import load_config
from matching.loader import LocalLoader
from matching.dimensions import Dimensions
from matching.filters import HardFilter
from matching.scoring import Scorer
from matching.reason import template_reason

CONFIG = os.path.join(HERE, "config")
DATA = os.path.join(HERE, "data")


def _setup():
    syn = load_config("synonyms", CONFIG)
    dims = Dimensions(syn)
    loader = LocalLoader(DATA)
    return (
        loader.load_mentors(),
        loader.load_students(),
        dims,
        HardFilter(load_config("hard_filters", CONFIG), syn),
        Scorer(load_config("weights", CONFIG), dims),
    )


def _find(items, key):
    for x in items:
        if getattr(x, "student_id", None) == key or getattr(x, "mentor_id", None) == key:
            return x
    raise KeyError(key)


def _rank_top(mentors, student, hardfilter, scorer):
    pairs = [(scorer.score(m, student)["total"], m.mentor_id)
             for m in mentors if hardfilter.passes(m, student)]
    pairs.sort(reverse=True)
    return pairs[0][1] if pairs else None


def test_capacity_filter():
    """容量已满的导师应被硬过滤剔除。"""
    mentors, students, dims, hardfilter, scorer = _setup()
    s = _find(students, "S003")
    m003 = _find(mentors, "M003")  # max=2, current=2 → 满
    assert m003.free_slots == 0
    assert hardfilter.passes(m003, s) is False


def test_same_gender_filter():
    """学生要求同性别时，异性导师被剔除。"""
    mentors, students, dims, hardfilter, scorer = _setup()
    s = _find(students, "S003")  # 女，prefer_same_gender=True
    assert hardfilter.passes(_find(mentors, "M001"), s) is False   # M001 男
    assert hardfilter.passes(_find(mentors, "M008"), s) is True    # M008 女


def test_s001_top_is_internet_mentor():
    """S001（互联网/科技）头部应为互联网类导师 M007 或 M001。"""
    mentors, students, dims, hardfilter, scorer = _setup()
    top = _rank_top(mentors, _find(students, "S001"), hardfilter, scorer)
    assert top in ("M001", "M007"), "S001 头部是 %s" % top


def test_reason_content():
    """模板理由应含导师ID 与行业关键词。"""
    mentors, students, dims, hardfilter, scorer = _setup()
    s = _find(students, "S002")  # 金融
    m = _find(mentors, "M002")
    subs = scorer.score(m, s)
    r = template_reason(m, s, subs)
    assert "M002" in r and "金融" in r


def test_weights_change_affects_ranking():
    """只看「行业」维度时，互联网类导师应居首。"""
    mentors, students, dims, hardfilter, scorer = _setup()
    s = _find(students, "S001")
    biased = Scorer(
        {"industry": 1.0, "need": 0, "service": 0, "region": 0, "personality": 0, "profile": 0},
        dims,
    )
    top = _rank_top(mentors, s, hardfilter, biased)
    assert top in ("M001", "M007", "M005"), top


# ---- 简易运行器（无 pytest 也能跑）----
if __name__ == "__main__":
    tests = [
        test_capacity_filter,
        test_same_gender_filter,
        test_s001_top_is_internet_mentor,
        test_reason_content,
        test_weights_change_affects_ranking,
    ]
    passed = 0
    for t in tests:
        t()
        print("PASS", t.__name__)
        passed += 1
    print("\n%d/%d passed" % (passed, len(tests)))

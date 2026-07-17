"""为指定导师生成「激励荣誉证书」HTML（浏览器打开，可打印 PDF）。
用法：python scripts/generate_certificate.py [导师ID，默认 M007]
输出：docs/certificates/certificate_{导师ID}.html
证书 HTML 由 matching/certificate.py 统一生成（与网页预览一致）。
"""
from __future__ import annotations
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # AI_CAMP 根
sys.path.insert(0, HERE)

from matching.config import load_config  # noqa: E402
from matching.loader import LocalLoader  # noqa: E402
from matching.incentive import compute_level  # noqa: E402
from matching.certificate import build_html  # noqa: E402


def main():
    mid = sys.argv[1] if len(sys.argv) > 1 else "M007"
    cfg = load_config("incentive", os.path.join(HERE, "config"))
    m = next((x for x in LocalLoader(os.path.join(HERE, "data")).load_mentors() if x.mentor_id == mid), None)
    if not m:
        print("找不到导师：%s" % mid)
        sys.exit(1)
    level, level_name, score = compute_level(m, cfg)
    html = build_html(m, level, level_name, score)
    out_dir = os.path.join(HERE, "docs", "certificates")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "certificate_%s.html" % mid)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成证书：%s" % os.path.relpath(path, HERE))
    print("  %s → %s %s（综合评估分 %s）" % (mid, level, level_name, score))
    print("  浏览器打开该 html 即可查看，Ctrl+P 可打印/存为 PDF。")


if __name__ == "__main__":
    main()

"""导师荣誉证书 HTML 生成（L1-L3 发展与赋能体系）。app 的 /certificate 与 scripts/generate_certificate.py 共用。"""
from __future__ import annotations
import datetime


def build_html(m, level, level_name, score) -> str:
    d = datetime.date.today()
    today = "%d 年 %d 月 %d 日" % (d.year, d.month, d.day)
    hours = m.total_hours or m.used_hours
    students = m.total_students or m.current_students
    rating_txt = ("%.1f" % m.rating) if m.rating else "—"
    # L3 首席触发「致信 CEO」表彰（发展与赋能体系）
    ceo_line = ("，并据此启动「致信所在机构 CEO」表彰机制，将您的公益贡献正式函告贵单位"
                if level == "L3" else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>荣誉证书 · {m.mentor_id}</title>
<style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
  .title,.name,.lv,.rank,.org,.item .num,.seal .inner{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC","STSong","SimSun",serif;}}
  .brandmark{{text-align:center;margin-bottom:4px;}}
  .brandmark svg{{width:34px;height:34px;stroke:#c9a227;stroke-width:1.5;fill:none;stroke-linecap:round;stroke-linejoin:round;}}
body {{ margin:0; padding:30px; background:#faf8f3; font-family:"Microsoft YaHei","PingFang SC",serif; display:flex; justify-content:center; }}
.certificate {{ width:210mm; min-height:297mm; background:#fffdf7; padding:16mm 18mm; position:relative;
  border:12px solid #c9a227; outline:2px solid #c9a227; outline-offset:6px; box-shadow:0 10px 40px rgba(0,0,0,.15); }}
.corner {{ position:absolute; width:54px; height:54px; border:3px solid #c9a227; }}
.tl {{ top:18px; left:18px; border-right:none; border-bottom:none; }}
.tr {{ top:18px; right:18px; border-left:none; border-bottom:none; }}
.bl {{ bottom:18px; left:18px; border-right:none; border-top:none; }}
.br {{ bottom:18px; right:18px; border-left:none; border-top:none; }}
.org {{ text-align:center; font-size:15px; color:#8a6d1f; letter-spacing:4px; margin-top:6px; }}
.title {{ text-align:center; font-size:40px; color:#1f2430; font-weight:700; margin:16px 0 2px; letter-spacing:10px; }}
.subtitle {{ text-align:center; font-size:12px; color:#b89b3e; letter-spacing:6px; }}
.line {{ width:100px; height:2px; background:#c9a227; margin:12px auto 22px; }}
.award {{ text-align:center; font-size:17px; color:#666; }}
.name {{ text-align:center; font-size:50px; color:#c9a227; font-weight:700; margin:8px 0; letter-spacing:4px; }}
.lv {{ text-align:center; font-size:30px; color:#c9a227; font-weight:700; letter-spacing:3px; margin:2px 0 4px; }}
.rank {{ text-align:center; font-size:24px; color:#1f2430; font-weight:700; margin-bottom:20px; letter-spacing:3px; }}
.body {{ font-size:15px; line-height:2; color:#333; margin:22px 56px; text-indent:2em; text-align:justify; }}
.detail {{ display:flex; justify-content:center; gap:30px; margin:22px 0; }}
.item {{ text-align:center; }}
.item .num {{ font-size:22px; color:#c9a227; font-weight:700; }}
.item .lbl {{ font-size:12px; color:#888; margin-top:2px; }}
.footer {{ position:absolute; bottom:22mm; left:0; right:0; display:flex; justify-content:space-between; align-items:center; padding:0 26mm; }}
.date {{ font-size:14px; color:#555; line-height:1.8; }}
.seal {{ width:116px; height:116px; border:4px solid #c0392b; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#c0392b; transform:rotate(-8deg); opacity:.92; }}
.seal .inner {{ width:92px; height:92px; border:2px solid #c0392b; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:16px; text-align:center; line-height:1.5; }}
@media print {{ body {{ background:#fff; padding:0; }} .certificate {{ box-shadow:none; }} }}
</style></head>
<body>
<div class="certificate">
  <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
  <div class="brandmark"><svg viewBox="0 0 24 24"><path d="M7 20h10"/><path d="M10 20c5.5-2.5.8-6.4 3-10"/><path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/><path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/></svg></div>
  <div class="org">上 海 益 志 领 公 益 基 金 会</div>
  <div class="title">导师荣誉证书</div>
  <div class="subtitle">CERTIFICATE OF EXCELLENCE</div>
  <div class="line"></div>
  <div class="award">兹评定以下导师为本年度</div>
  <div class="name">{m.mentor_id} 导师</div>
  <div class="lv">{level}</div>
  <div class="rank">{level_name}</div>
  <div class="body">感谢您在公益事业中展现的热忱与担当。您累计志愿服务 <b>{hours} 小时</b>，用心辅导 <b>{students} 位</b>困境学子{("，学生反馈平均分 <b>%.1f 分</b>" % m.rating) if m.rating else ""}{ceo_line}。您的付出是学员成长路上的光，也是基金会最珍视的力量。特评定为「<b>{level_name}</b>」，以彰荣功，以志感谢。</div>
  <div class="detail">
    <div class="item"><div class="num">{hours}h</div><div class="lbl">服务时长</div></div>
    <div class="item"><div class="num">{students}</div><div class="lbl">辅导学生</div></div>
    <div class="item"><div class="num">{rating_txt}</div><div class="lbl">反馈分(/10)</div></div>
    <div class="item"><div class="num">{m.org_score}</div><div class="lbl">深度贡献</div></div>
    <div class="item"><div class="num">{score}</div><div class="lbl">综合评估</div></div>
  </div>
  <div class="footer">
    <div class="date">评定日期<br><b>{today}</b><br>证书编号：YZL-{m.mentor_id}-{level or "L0"}</div>
    <div class="seal"><div class="inner">益志领<br>公益基金会</div></div>
  </div>
</div>
</body></html>"""

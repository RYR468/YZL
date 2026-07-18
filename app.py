"""益志领 · 导师匹配系统 —— Web 前端（Flask）。

启动：双击「启动.bat」或运行 python app.py，浏览器打开 http://127.0.0.1:5000

数据源（在网页「数据源」面板切换）：
  - 本地：读 data/*.json 的 mock 数据
  - 飞书：读飞书多维表格（凭证存 config/feishu.json），可一键写回匹配结果
  - 导入：在网页上传导师/学生 CSV（中文表头，与 data/*.csv 同格式）
"""
from __future__ import annotations
import csv
import datetime
import io
import json
import os
import sys
import threading
import urllib.request
import webbrowser

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import secrets
import time
from flask import Flask, request, jsonify, render_template, send_file, session, redirect

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _HAS_LIMITER = True
except ImportError:
    _HAS_LIMITER = False

from matching.config import load_config
from matching.loader import LocalLoader, FeishuLoader, mentor_from_cn, student_from_cn
from matching.dimensions import Dimensions
from matching.filters import HardFilter
from matching.scoring import Scorer
from matching.reason import template_reason
from matching.incentive import compute_level
from matching.certificate import build_html
from matching.recruit import screen as recruit_screen, form_to_mentor

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "config")
DATA_DIR = os.path.join(HERE, "data")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)  # 无 env 则每次启动随机(安全;重启 session 失效)

# 频率限制(防刷)。未装 flask-limiter 时降级为无限制,不阻断启动。
if _HAS_LIMITER:
    limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])

    def rate_limit(limit_str):
        return limiter.limit(limit_str)

    def _client_ip():
        return get_remote_address()
else:

    def rate_limit(limit_str):
        return (lambda f: f)

    def _client_ip():
        return request.remote_addr or "unknown"

# 登录失败锁定(内存,按 IP:连续 5 次错锁 15 分钟)
_LOGIN_FAILS = {}

def _check_login_lock(ip):
    rec = _LOGIN_FAILS.get(ip)
    if rec and rec[1] > time.time():
        return rec[1] - time.time()
    return 0

def _record_login_fail(ip):
    rec = _LOGIN_FAILS.get(ip, [0, 0])
    rec[0] += 1
    if rec[0] >= 5:
        rec[1] = time.time() + 900
        rec[0] = 0
    _LOGIN_FAILS[ip] = rec

def _clear_login_fails(ip):
    _LOGIN_FAILS.pop(ip, None)

# ---- 管理端登录密码 / 二级密码 ----  优先环境变量(部署),其次 config/admin.json(本地开发);两者都没有则拒绝启动
_admin_cfg = load_config("admin", CONFIG_DIR) or {}
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or _admin_cfg.get("password")
AUDIT_PASSWORD = os.getenv("AUDIT_PASSWORD") or _admin_cfg.get("audit_password") or ADMIN_PASSWORD
if not ADMIN_PASSWORD:
    print("❌ 未配置 ADMIN_PASSWORD(设环境变量或 config/admin.json),拒绝启动。", file=sys.stderr)
    sys.exit(1)
PUBLIC_PATHS = {"/login", "/logout", "/recruit", "/api/recruit"}


@app.before_request
def _gate():
    """公开路由放行;其余需登录,API 未登录回 401,页面跳 /login。"""
    if request.path in PUBLIC_PATHS or request.path.startswith("/static"):
        return
    if not session.get("admin"):
        if request.path.startswith("/api/") or request.path.startswith("/certificate"):
            return jsonify({"error": "未登录", "login": True}), 401
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
@rate_limit("5/minute")
def login():
    if request.method == "POST":
        ip = _client_ip()
        remain = _check_login_lock(ip)
        if remain > 0:
            return jsonify({"ok": False, "message": "尝试过多已锁定,请 %d 分钟后再试" % int(remain / 60 + 1)}), 429
        pwd = ((request.get_json(silent=True) or {}).get("password")
               or request.form.get("password", ""))
        if pwd == ADMIN_PASSWORD:
            _clear_login_fails(ip)
            session["admin"] = True
            return jsonify({"ok": True})
        _record_login_fail(ip)
        return jsonify({"ok": False, "message": "密码错误"}), 401
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/admin/password", methods=["POST"])
def admin_password():
    """修改登录密码 / 二级密码(需登录 + 校验当前密码)。写回 config/admin.json 并即时更新内存。"""
    global ADMIN_PASSWORD, AUDIT_PASSWORD
    body = request.get_json(silent=True) or {}
    if (body.get("current") or "") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "message": "当前密码错误"}), 403
    new_pw = (body.get("password") or "").strip()
    new_audit = (body.get("audit_password") or "").strip()
    if not new_pw and not new_audit:
        return jsonify({"ok": False, "message": "请填写新登录密码或新二级密码(至少一项)"}), 400
    path = os.path.join(CONFIG_DIR, "admin.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    changed = []
    if new_pw:
        data["password"] = new_pw
        changed.append("登录密码")
    if new_audit:
        data["audit_password"] = new_audit
        changed.append("二级密码")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if new_pw:
        ADMIN_PASSWORD = new_pw
    if new_audit:
        AUDIT_PASSWORD = new_audit
    return jsonify({"ok": True, "message": "已更新:" + "、".join(changed) + "。立即生效,下次登录/审核请用新密码。"})


SYNONYMS = load_config("synonyms", CONFIG_DIR)
DIMS = Dimensions(SYNONYMS)
DEFAULT_WEIGHTS = load_config("weights", CONFIG_DIR)
HARD_CFG = load_config("hard_filters", CONFIG_DIR)
INCENTIVE_CFG = load_config("incentive", CONFIG_DIR)

DIM_LABELS = {"industry": "行业/方向", "need": "能力-需求", "service": "服务类型",
              "region": "地区/偏好", "personality": "性格", "profile": "画像"}
DIM_ORDER = ["industry", "need", "service", "region", "personality", "profile"]

# 三种数据源的缓存
CACHE = {
    "source": "local",
    "local": {"mentors": LocalLoader(DATA_DIR).load_mentors(), "students": LocalLoader(DATA_DIR).load_students()},
    "feishu": {"mentors": [], "students": []},
    "imported": {"mentors": [], "students": []},
    "feishu_loader": None,
}


def _can_import(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _feishu_cfg():
    # 优先环境变量(部署到云平台用),其次 config/feishu.json(本地开发用)
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if app_id and app_secret:
        try:
            tables = json.loads(os.getenv("FEISHU_TABLES_JSON") or "{}")
        except Exception:
            tables = {}
        return {
            "app_id": app_id, "app_secret": app_secret,
            "base_url": os.getenv("FEISHU_BASE_URL", ""),
            "group_webhook": os.getenv("FEISHU_GROUP_WEBHOOK", ""),
            "group_chat_id": os.getenv("FEISHU_GROUP_CHAT_ID", ""),
            "tables": tables,
        }
    path = os.path.join(CONFIG_DIR, "feishu.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("app_id") and cfg.get("app_secret") and cfg.get("tables"):
            return cfg
    except Exception:
        pass
    return None


def _feishu_loader():
    cfg = _feishu_cfg()
    if not cfg:
        return None
    try:
        if CACHE["feishu_loader"] is None:
            CACHE["feishu_loader"] = FeishuLoader(cfg["app_id"], cfg["app_secret"], cfg["tables"], cfg.get("base_url", ""))
        return CACHE["feishu_loader"]
    except Exception:
        return None


def feishu_status():
    installed = _can_import("lark_oapi")
    configured = bool(_feishu_cfg())
    if not installed:
        msg = "未安装飞书 SDK（lark-oapi）。"
    elif not configured:
        msg = "未配置飞书凭证。"
    else:
        msg = "凭证已保存，可切换到飞书数据源。"
    return {"installed": installed, "configured": configured, "message": msg}


# ---- 飞书消息通知 ----
NOTIFY_RECRUIT_RECEIVED = "【益志领】感谢您报名益志领导师!我们已收到您的申请,审核结果将通过飞书通知您。"
NOTIFY_RECRUIT_SCREEN_PASS = "【益志领】恭喜!您的报名已通过系统初筛(名校/500强资质核验),我们将尽快人工审核,结果会再次飞书通知您。"
NOTIFY_RECRUIT_APPROVED = "【益志领】恭喜您通过益志领导师审核,正式加入导师库!感谢您愿意成为困境学子的志愿导师,后续请留意匹配与课程通知。"
NOTIFY_RECRUIT_REJECTED = "【益志领】感谢您对益志领的关注。本次申请暂未通过,如有疑问欢迎联系我们。"
NOTIFY_MATCH_MENTOR = "【益志领】系统为您匹配了一位新学生:{student}。请尽快与学生联系开启辅导。"
NOTIFY_MATCH_STUDENT = "【益志领】已为您匹配志愿导师:{mentor},期待你们的交流!"
NOTIFY_SCHEDULE = "【益志领】课程提醒:{time} {topic}({mode}),导师{mentor} ↔ 学生{student},请按时参加。"
NOTIFY_ACTIVITY = "【益志领·活动通知】{title}\n时间:{time}\n地点:{location}\n{content}"


def _notify_mobile(mobile, text):
    """给手机号发飞书消息;返回 (ok, msg)。飞书未配置/失败不抛异常。"""
    if not mobile:
        return False, "未填手机号,跳过通知"
    fl = _feishu_loader()
    if not fl:
        return False, "飞书未配置,未通知"
    try:
        fl.send_to_mobile(mobile, text)
        return True, "已飞书通知"
    except Exception as e:
        return False, "通知未发送:%s" % e


def _notify_chat(text):
    cfg = _feishu_cfg() or {}
    webhook = cfg.get("group_webhook")
    if webhook:
        try:
            data = json.dumps({"msg_type": "text", "content": {"text": text}},
                              ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code", 0) != 0:
                return False, "发群失败:%s" % (result.get("msg") or str(result))
            return True, "已发大群(webhook)"
        except Exception as e:
            return False, "发群失败:%s" % e
    chat_id = cfg.get("group_chat_id")
    if chat_id:
        fl = _feishu_loader()
        if fl:
            try:
                fl.send_to_chat(chat_id, text)
                return True, "已发大群"
            except Exception as e:
                return False, "发群失败:%s" % e
    return False, "未配置大群 webhook/chat_id"


def current():
    return CACHE[CACHE["source"]]


def _counts(source=None):
    d = CACHE[source or CACHE["source"]]
    return {"mentors": len(d["mentors"]), "students": len(d["students"])}


def load_source(source):
    """切换/刷新数据源。返回 (ok, message)。"""
    if source == "feishu":
        fl = _feishu_loader()
        if not fl:
            return False, "飞书未配置或 SDK 未安装"
        try:
            CACHE["feishu"]["mentors"] = fl.load_mentors()
            CACHE["feishu"]["students"] = fl.load_students()
            CACHE["source"] = "feishu"
            msg = "已从飞书加载 %d 位导师、%d 位学生" % (len(CACHE["feishu"]["mentors"]), len(CACHE["feishu"]["students"]))
            if getattr(fl, "mentor_missing_columns", None):
                msg += "；⚠️导师表缺 %s 列，地区维度已用城市兜底，建议补列" % "、".join(fl.mentor_missing_columns)
            return True, msg
        except Exception as e:
            return False, "读取飞书失败：%s" % e
    if source == "imported":
        if not CACHE["imported"]["mentors"] and not CACHE["imported"]["students"]:
            return False, "还没导入任何数据，请先在「导入数据」上传 CSV"
        CACHE["source"] = "imported"
        return True, "已切换到导入数据：%d 导师 / %d 学生" % (len(CACHE["imported"]["mentors"]), len(CACHE["imported"]["students"]))
    # local
    CACHE["source"] = "local"
    return True, "已切换到本地 mock 数据：%d 导师 / %d 学生" % (len(CACHE["local"]["mentors"]), len(CACHE["local"]["students"]))


def _brief(s):
    return {"student_id": s.student_id, "grade": s.grade, "region": s.region, "gender": s.gender,
            "interested_fields": s.interested_fields, "needs": s.needs, "personality": s.personality}


def _compute(student, weights, top_n):
    mentors = current()["mentors"]
    hf = HardFilter(HARD_CFG, SYNONYMS)
    scorer = Scorer(weights, DIMS)
    cands = [m for m in mentors if hf.passes(m, student)]
    scored = sorted(((scorer.score(m, student), m) for m in cands),
                    key=lambda x: x[0]["total"], reverse=True)[:top_n]
    matches = []
    for rank, (subs, m) in enumerate(scored, 1):
        level, level_name, _lv = compute_level(m, INCENTIVE_CFG)
        matches.append({"rank": rank, "mentor_id": m.mentor_id, "industry": m.industry,
                        "city": m.city, "free_slots": m.free_slots,
                        "scores": subs, "reason": template_reason(m, student, subs),
                        "level": level, "level_name": level_name})
    return matches, len(mentors) - len(cands)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    d = current()
    return jsonify({"source": CACHE["source"], "counts": _counts(),
                    "students": [_brief(s) for s in d["students"]]})


@app.route("/api/config")
def api_config():
    return jsonify({"weights": DEFAULT_WEIGHTS, "dim_labels": DIM_LABELS, "dim_order": DIM_ORDER,
                    "top_n": 5, "feishu": feishu_status(), "source": CACHE["source"],
                    "imported_counts": _counts("imported")})


@app.route("/api/source", methods=["POST"])
def api_source():
    body = request.get_json(silent=True) or {}
    ok, msg = load_source(body.get("source", "local"))
    out = {"ok": ok, "message": msg, "source": CACHE["source"], "counts": _counts()}
    if ok:
        out["students"] = [_brief(s) for s in current()["students"]]
    return jsonify(out)


@app.route("/api/import", methods=["POST"])
def api_import():
    kind = request.form.get("type")  # mentor / student
    f = request.files.get("file")
    if kind not in ("mentor", "student") or not f:
        return jsonify({"ok": False, "message": "请选择类型（导师/学生）并上传 CSV 文件。"})
    text = f.read().decode("utf-8-sig", errors="ignore")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return jsonify({"ok": False, "message": "CSV 里没读到数据，请检查表头是否为中文（导师ID/学生ID…）。"})
    if kind == "mentor":
        CACHE["imported"]["mentors"] = [mentor_from_cn(r) for r in rows]
    else:
        CACHE["imported"]["students"] = [student_from_cn(r) for r in rows]
    CACHE["source"] = "imported"
    name = "导师" if kind == "mentor" else "学生"
    return jsonify({"ok": True, "message": "已导入 %d 条%s，已切换到「导入」数据源。" % (len(rows), name),
                    "source": "imported", "counts": _counts("imported"),
                    "students": [_brief(s) for s in CACHE["imported"]["students"]]})


@app.route("/api/template/<kind>")
def api_template(kind):
    """下载导师/学生的 CSV 表头模板（即 data/mentors.csv、students.csv）。"""
    name = {"mentor": "mentors.csv", "student": "students.csv"}.get(kind)
    if not name:
        return "not found", 404
    return send_file(os.path.join(DATA_DIR, name), as_attachment=True)


@app.route("/api/match", methods=["POST"])
def api_match():
    body = request.get_json(silent=True) or {}
    sid = body.get("student_id")
    weights = body.get("weights") or DEFAULT_WEIGHTS
    top_n = int(body.get("top_n", 5))
    students = current()["students"]
    student = next((s for s in students if s.student_id == sid), None)
    if not student:
        return jsonify({"error": "学生不存在: %s" % sid}), 404
    matches, filtered_out = _compute(student, weights, top_n)
    return jsonify({"student": _brief(student), "matches": matches, "filtered_out": filtered_out})


@app.route("/api/mentors")
def api_mentors():
    """导师管理视图：列出当前数据源所有导师 + 上课时长 + 星级等。"""
    out = []
    for m in current()["mentors"]:
        level, level_name, score = compute_level(m, INCENTIVE_CFG)
        out.append({"mentor_id": m.mentor_id, "gender": m.gender, "city": m.city,
                    "industry": m.industry, "used_hours": m.used_hours,
                    "total_hours": m.total_hours or m.used_hours,
                    "current_students": m.current_students, "max_students": m.max_students,
                    "total_students": m.total_students or m.current_students,
                    "free_slots": m.free_slots, "level": level, "level_name": level_name, "score": score,
                    "tags": m.tags, "qualification": m.qualification, "school": m.school,
                    "work_years": m.work_years, "company": m.company, "status": m.status,
                    "annual_hour_cap": m.annual_hour_cap, "cert_state": _cert_state(m, level)})
    return jsonify({"source": CACHE["source"], "count": len(out), "mentors": out})


@app.route("/api/mentor/<mid>", methods=["POST"])
def mentor_update(mid):
    """管理员编辑导师字段(余量/年度上限/状态)→ 写飞书导师表 + 更新本地缓存。"""
    body = request.get_json(silent=True) or {}
    m = next((x for x in current()["mentors"] if x.mentor_id == mid), None)
    if not m:
        return jsonify({"ok": False, "message": "导师不存在"}), 404
    fields_cn = {}
    if "max_students" in body:
        m.max_students = max(0, int(body.get("max_students") or 0))
        fields_cn["可同时辅导人数"] = m.max_students
    if "current_students" in body:
        m.current_students = max(0, int(body.get("current_students") or 0))
        fields_cn["已配学生数"] = m.current_students
    if "annual_hour_cap" in body:
        m.annual_hour_cap = max(0, int(body.get("annual_hour_cap") or 0))
        fields_cn["年度时长上限"] = m.annual_hour_cap
    if "status" in body:
        m.status = body.get("status") or m.status
        fields_cn["服务状态"] = m.status
    msg_extra = ""
    fl = _feishu_loader()
    if fl and fields_cn:
        try:
            fl.update_mentor_fields(mid, fields_cn)
            msg_extra = ",已写飞书导师表"
        except Exception as e:
            msg_extra = "(飞书更新失败:%s;已本地更新)" % e
    elif fields_cn:
        msg_extra = "(飞书未配置,已本地更新)"
    return jsonify({"ok": True, "message": "已更新" + msg_extra,
                    "free_slots": m.free_slots, "annual_hour_cap": m.annual_hour_cap})


def _cert_state(m, level):
    """证书状态:L1 自动可生成;L2/L3 需管理员审核(m.cert_status=approved 后可生成)。"""
    if m.cert_status == "approved":
        return "approved"
    if not level:
        return "none"
    return "auto" if level == "L1" else "pending"


def _cert_pending_html(m, level, level_name, title, tip):
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{title} · {m.mentor_id}</title>
<style>body{{margin:0;font-family:"Microsoft YaHei",sans-serif;background:#faf8f3;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:20px;}}
.box{{background:#fff;border:1px solid #e7dfcf;border-radius:16px;padding:40px 36px;text-align:center;max-width:420px;box-shadow:0 10px 30px rgba(0,0,0,.06);}}
.ic{{font-size:44px;}} h1{{color:#214f60;font-family:"Noto Serif SC",serif;font-size:20px;margin:14px 0 8px;}} p{{color:#5e6b6a;font-size:14px;line-height:1.7;margin:6px 0;}}
.lv{{font-size:13px;color:#aab;}}
</style></head><body><div class="box"><div class="ic">📜</div><h1>{title}</h1><p>{tip}</p>
<p class="lv">{m.mentor_id} · {level or "未评定"} {level_name or ""}</p></div></body></html>"""


@app.route("/certificate/<mid>")
def certificate(mid):
    """导师激励证书:L1 系统自动可生成;L2/L3 需管理员审核通过后生成。"""
    m = next((x for x in current()["mentors"] if x.mentor_id == mid), None)
    if not m:
        return "导师不存在: %s" % mid, 404
    level, level_name, score = compute_level(m, INCENTIVE_CFG)
    st = _cert_state(m, level)
    if st in ("auto", "approved"):
        return build_html(m, level, level_name, score)
    if st == "none":
        return _cert_pending_html(m, level, level_name, "尚未达到发证条件", "该导师暂无级别评定,无法生成荣誉证书。")
    return _cert_pending_html(m, level, level_name, "证书待管理员审核",
                              "%s 级别的荣誉证书需经管理员审核通过后方可生成。" % (level or ""))


@app.route("/api/mentor/<mid>/cert/approve", methods=["POST"])
def mentor_cert_approve(mid):
    """管理员审核通过 L2/L3 证书(通过后 /certificate 即可生成)。需二级密码。"""
    body = request.get_json(silent=True) or {}
    if body.get("audit_pw") != AUDIT_PASSWORD:
        return jsonify({"ok": False, "message": "二级密码错误,操作已拦截"}), 403
    m = next((x for x in current()["mentors"] if x.mentor_id == mid), None)
    if not m:
        return jsonify({"ok": False, "message": "导师不存在"}), 404
    level = compute_level(m, INCENTIVE_CFG)[0]
    if level not in ("L2", "L3"):
        return jsonify({"ok": False, "message": "仅 L2/L3 需审核;当前 %s" % (level or "未评定")})
    m.cert_status = "approved"
    return jsonify({"ok": True, "message": "已通过 %s 证书审核,现在可生成。" % level, "cert_status": "approved"})


APPLICANTS_FILE = os.path.join(DATA_DIR, "applicants.json")


def _load_applicants():
    if os.path.exists(APPLICANTS_FILE):
        try:
            with open(APPLICANTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_applicants(rows):
    with open(APPLICANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


PAIRS_FILE = os.path.join(DATA_DIR, "pairs.json")


def _load_pairs():
    if os.path.exists(PAIRS_FILE):
        try:
            with open(PAIRS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_pairs(rows):
    with open(PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")


def _load_schedules():
    if os.path.exists(SCHEDULES_FILE):
        try:
            with open(SCHEDULES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_schedules(rows):
    with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


ACTIVITIES_FILE = os.path.join(DATA_DIR, "activities.json")


def _load_activities():
    if os.path.exists(ACTIVITIES_FILE):
        try:
            with open(ACTIVITIES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_activities(rows):
    with open(ACTIVITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


@app.route("/recruit")
def recruit_page():
    """导师自助报名(对外公开页,无需登录)。"""
    return render_template("recruit.html")


@app.route("/api/recruit", methods=["POST"])
@rate_limit("3/minute")
def api_recruit():
    """导师报名 → 规则初筛 → 进待审核池(不自动入名单;管理员审核通过才写飞书导师表)。"""
    form = request.get_json(silent=True) or {}
    # 蜜罐:隐藏字段 website 真人不会填,机器人会填 → 静默丢弃(返回 ok 但不入库,不暴露已识别)
    if form.get("website"):
        return jsonify({"ok": True, "result": "review", "reasons": [], "missing": [],
                        "mentor_id": "R0000", "status": "pending",
                        "note": "报名已提交,等待管理员复核。", "notify": ""})
    rows = _load_applicants()
    seq = len(rows) + 1
    scr = recruit_screen(form)
    m = form_to_mentor(form, seq)
    rows.append({"id": "A%04d" % seq, "mentor_id": m.mentor_id, "status": "pending",
                 "result": scr["result"], "reasons": scr["reasons"], "missing": scr["missing"],
                 "form": form, "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    _save_applicants(rows)
    note = ("初筛通过,等待管理员审核后正式入库。" if scr["result"] == "pass"
            else "报名已提交,等待管理员复核。" if scr["result"] == "review"
            else "感谢关注;管理员仍可人工复核。")
    nok, nmsg = _notify_mobile(form.get("飞书手机号") or m.feishu_mobile,
                               NOTIFY_RECRUIT_SCREEN_PASS if scr["result"] == "pass" else NOTIFY_RECRUIT_RECEIVED)
    return jsonify({"ok": True, "result": scr["result"], "reasons": scr["reasons"],
                    "missing": scr["missing"], "mentor_id": m.mentor_id,
                    "status": "pending", "note": note, "notify": nmsg})


@app.route("/api/applicants")
def api_applicants():
    """待审核招募列表(管理端)。"""
    return jsonify({"applicants": _load_applicants()})


@app.route("/api/applicant/<aid>/approve", methods=["POST"])
def applicant_approve(aid):
    """通过招募申请 → 写飞书导师表(权威)+ 即时入本地导师池。飞书失败则降级本地。需二级密码。"""
    body = request.get_json(silent=True) or {}
    if body.get("audit_pw") != AUDIT_PASSWORD:
        return jsonify({"ok": False, "message": "二级密码错误,操作已拦截"}), 403
    rows = _load_applicants()
    rec = next((r for r in rows if r.get("id") == aid), None)
    if not rec:
        return jsonify({"ok": False, "message": "找不到该申请"}), 404
    if rec.get("status") in ("approved", "approved-local"):
        return jsonify({"ok": True, "message": "该申请已通过", "status": rec["status"]})
    form = dict(rec.get("form", {}))
    form["导师ID"] = rec.get("mentor_id") or form.get("导师ID") or ("R%03d" % len(rows))
    msg_extra = ""
    fl = _feishu_loader()
    if fl:
        try:
            fl.add_mentor(form)
            rec["status"] = "approved"
            msg_extra = "，已写入飞书导师表"
        except Exception as e:
            rec["status"] = "approved-local"
            msg_extra = "（飞书写入失败：%s；已本地入库，请到飞书授予应用「可编辑」权限或手动录入）" % e
    else:
        rec["status"] = "approved-local"
        msg_extra = "（飞书未配置，已本地入库）"
    # 即时进入本地导师池，管理台当场可见可匹配
    if not any(m.mentor_id == form["导师ID"] for m in CACHE["local"]["mentors"]):
        CACHE["local"]["mentors"].append(mentor_from_cn(form))
    _save_applicants(rows)
    nok, nmsg = _notify_mobile(form.get("飞书手机号") or "", NOTIFY_RECRUIT_APPROVED)
    return jsonify({"ok": True, "message": "已通过" + msg_extra + ";通知:" + nmsg, "status": rec["status"]})


@app.route("/api/applicant/<aid>/reject", methods=["POST"])
def applicant_reject(aid):
    body = request.get_json(silent=True) or {}
    if body.get("audit_pw") != AUDIT_PASSWORD:
        return jsonify({"ok": False, "message": "二级密码错误,操作已拦截"}), 403
    rows = _load_applicants()
    rec = next((r for r in rows if r.get("id") == aid), None)
    if not rec:
        return jsonify({"ok": False, "message": "找不到该申请"}), 404
    rec["status"] = "rejected"
    _save_applicants(rows)
    nok, nmsg = _notify_mobile((rec.get("form") or {}).get("飞书手机号") or "", NOTIFY_RECRUIT_REJECTED)
    return jsonify({"ok": True, "message": "已拒绝;通知:" + nmsg})


@app.route("/api/applicants/batch", methods=["POST"])
def applicants_batch():
    """批量通过/拒绝招募申请。需二级密码。"""
    body = request.get_json(silent=True) or {}
    if body.get("audit_pw") != AUDIT_PASSWORD:
        return jsonify({"ok": False, "message": "二级密码错误,操作已拦截"}), 403
    ids = body.get("ids") or []
    action = body.get("action")
    if action not in ("approve", "reject") or not ids:
        return jsonify({"ok": False, "message": "参数无效"}), 400
    rows = _load_applicants()
    idset = set(ids)
    done = 0
    fail = 0
    for r in rows:
        if r.get("id") in idset and r.get("status") == "pending":
            if action == "approve":
                form = dict(r.get("form", {}))
                form["导师ID"] = r.get("mentor_id") or form.get("导师ID") or ("R%03d" % len(rows))
                fl = _feishu_loader()
                if fl:
                    try:
                        fl.add_mentor(form)
                        r["status"] = "approved"
                    except Exception:
                        r["status"] = "approved-local"
                        fail += 1
                else:
                    r["status"] = "approved-local"
                if not any(mm.mentor_id == form["导师ID"] for mm in CACHE["local"]["mentors"]):
                    CACHE["local"]["mentors"].append(mentor_from_cn(form))
            else:
                r["status"] = "rejected"
            done += 1
    _save_applicants(rows)
    verb = "通过" if action == "approve" else "拒绝"
    msg = "已批量%s %d 条申请" % (verb, done)
    if fail:
        msg += "(其中 %d 条飞书写入失败,已本地入库)" % fail
    return jsonify({"ok": True, "message": msg, "done": done})


@app.route("/api/applicant/<aid>/delete", methods=["POST"])
def applicant_delete(aid):
    """删除一条招募申请记录。"""
    rows = _load_applicants()
    new = [r for r in rows if r.get("id") != aid]
    if len(new) == len(rows):
        return jsonify({"ok": False, "message": "找不到该申请"}), 404
    _save_applicants(new)
    return jsonify({"ok": True, "message": "已删除该申请记录"})


@app.route("/api/pair", methods=["POST"])
def api_pair():
    """正式确认配对:去重 + 导师容量+1 + 飞书通知师生。"""
    body = request.get_json(silent=True) or {}
    mid = body.get("mentor_id")
    sid = body.get("student_id")
    if not mid or not sid:
        return jsonify({"ok": False, "message": "缺少 mentor_id / student_id"}), 400
    rows = _load_pairs()
    if any(p["mentor_id"] == mid and p["student_id"] == sid for p in rows):
        return jsonify({"ok": False, "message": "该导师-学生已配对"}), 400
    m = next((x for x in current()["mentors"] if x.mentor_id == mid), None)
    s = next((x for x in current()["students"] if x.student_id == sid), None)
    if not m or not s:
        return jsonify({"ok": False, "message": "导师或学生不存在"}), 404
    if m.free_slots <= 0:
        return jsonify({"ok": False, "message": "导师已无余量,无法配对"}), 400
    m.current_students += 1
    pid = "P%04d" % (len(rows) + 1)
    rows.append({"pair_id": pid, "mentor_id": mid, "student_id": sid,
                 "status": "配对中", "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    _save_pairs(rows)
    nm = _notify_mobile(m.feishu_mobile, NOTIFY_MATCH_MENTOR.replace("{student}", sid))[1]
    ns = _notify_mobile(s.feishu_mobile, NOTIFY_MATCH_STUDENT.replace("{mentor}", mid))[1]
    return jsonify({"ok": True, "message": "已配对 %s ↔ %s;导师通知:%s;学生通知:%s" % (mid, sid, nm, ns),
                    "pair_id": pid})


@app.route("/api/pairs")
def api_pairs():
    return jsonify({"pairs": _load_pairs()})


@app.route("/api/pair/<pid>/cancel", methods=["POST"])
def pair_cancel(pid):
    """取消配对:删除该配对 + 导师容量 -1(释放名额,可重新配对)。"""
    rows = _load_pairs()
    p = next((x for x in rows if x.get("pair_id") == pid), None)
    if not p:
        return jsonify({"ok": False, "message": "配对不存在"}), 404
    rows = [x for x in rows if x.get("pair_id") != pid]
    _save_pairs(rows)
    m = next((x for x in current()["mentors"] if x.mentor_id == p["mentor_id"]), None)
    if m and m.current_students > 0:
        m.current_students -= 1
    return jsonify({"ok": True, "message": "已取消配对 %s ↔ %s,导师名额已释放" % (p["mentor_id"], p["student_id"])})


@app.route("/api/pair/<pid>/complete", methods=["POST"])
def pair_complete(pid):
    """标记配对已完成(保留记录)。"""
    rows = _load_pairs()
    p = next((x for x in rows if x.get("pair_id") == pid), None)
    if not p:
        return jsonify({"ok": False, "message": "配对不存在"}), 404
    p["status"] = "已完成"
    _save_pairs(rows)
    return jsonify({"ok": True, "message": "已标记 %s ↔ %s 完成" % (p["mentor_id"], p["student_id"])})


@app.route("/api/schedules")
def api_schedules():
    return jsonify({"schedules": _load_schedules()})


@app.route("/api/schedule", methods=["POST"])
def api_schedule():
    """新增课程安排:存 + 飞书通知师生。"""
    body = request.get_json(silent=True) or {}
    mid = body.get("mentor_id")
    sid = body.get("student_id")
    if not mid or not sid or not body.get("time") or not body.get("topic"):
        return jsonify({"ok": False, "message": "缺少导师/学生/时间/主题"}), 400
    rows = _load_schedules()
    cid = "C%04d" % (len(rows) + 1)
    rows.append({"sched_id": cid, "pair_id": body.get("pair_id") or "",
                 "mentor_id": mid, "student_id": sid,
                 "time": body.get("time"), "topic": body.get("topic"),
                 "mode": body.get("mode") or "线上", "status": "待进行",
                 "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    _save_schedules(rows)
    text = (NOTIFY_SCHEDULE.replace("{time}", body.get("time")).replace("{topic}", body.get("topic"))
            .replace("{mode}", body.get("mode") or "线上").replace("{mentor}", mid).replace("{student}", sid))
    m = next((x for x in current()["mentors"] if x.mentor_id == mid), None)
    s = next((x for x in current()["students"] if x.student_id == sid), None)
    nm = _notify_mobile(m.feishu_mobile if m else "", text)[1]
    ns = _notify_mobile(s.feishu_mobile if s else "", text)[1]
    nc = _notify_chat("【课程安排】" + text)[1]
    return jsonify({"ok": True, "message": "已安排课程 %s;导师:%s;学生:%s;大群:%s" % (cid, nm, ns, nc), "sched_id": cid})


@app.route("/api/activities")
def api_activities():
    return jsonify({"activities": _load_activities()})


@app.route("/api/activity", methods=["POST"])
def api_activity():
    """发布活动到大群:存 + 飞书发群。"""
    body = request.get_json(silent=True) or {}
    title = body.get("title")
    tm = body.get("time")
    if not title or not tm:
        return jsonify({"ok": False, "message": "缺少活动标题/时间"}), 400
    loc = body.get("location") or "—"
    content = body.get("content") or ""
    rows = _load_activities()
    aid = "ACT%04d" % (len(rows) + 1)
    rows.append({"activity_id": aid, "title": title, "time": tm, "location": loc, "content": content,
                 "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    _save_activities(rows)
    text = (NOTIFY_ACTIVITY.replace("{title}", title).replace("{time}", tm)
            .replace("{location}", loc).replace("{content}", content))
    nok, nmsg = _notify_chat(text)
    return jsonify({"ok": True, "message": "活动已发布;" + nmsg, "activity_id": aid})


@app.route("/api/activity/<aid>/delete", methods=["POST"])
def activity_delete(aid):
    """删除一条活动记录。"""
    rows = _load_activities()
    new = [r for r in rows if r.get("activity_id") != aid]
    if len(new) == len(rows):
        return jsonify({"ok": False, "message": "找不到该活动"}), 404
    _save_activities(new)
    return jsonify({"ok": True, "message": "已删除该活动记录"})


@app.route("/api/feishu/write", methods=["POST"])
def api_feishu_write():
    fl = _feishu_loader()
    if not fl:
        return jsonify({"ok": False, "message": "飞书未配置，无法写回。"})
    body = request.get_json(silent=True) or {}
    sid = body.get("student_id")
    weights = body.get("weights") or DEFAULT_WEIGHTS
    top_n = int(body.get("top_n", 5))
    student = next((s for s in current()["students"] if s.student_id == sid), None)
    if not student:
        return jsonify({"ok": False, "message": "学生不存在"})
    matches, _ = _compute(student, weights, top_n)
    if not matches:
        return jsonify({"ok": False, "message": "没有匹配结果可写回。"})
    rows = [{"student_id": sid, "mentor_id": m["mentor_id"], "total": m["scores"]["total"],
             "sub_scores": {k: m["scores"][k] for k in DIM_ORDER}, "rank": m["rank"],
             "reason": m["reason"]} for m in matches]
    try:
        _tid, url = fl.write_matches_new_table(sid, rows)
        return jsonify({"ok": True,
                        "message": "已在飞书新建匹配表并写入 %d 条结果，点链接打开查看。" % len(rows),
                        "url": url})
    except Exception as e:
        return jsonify({"ok": False, "message": "写回失败：%s" % e})


@app.route("/api/feishu/test", methods=["POST"])
def api_feishu_test():
    fl = _feishu_loader()
    if not fl:
        return jsonify({"ok": False, "message": "飞书未配置或 SDK 未安装。"})
    try:
        n = len(fl.load_mentors())
        return jsonify({"ok": True, "message": "连接成功，读取到 %d 位导师。" % n})
    except Exception as e:
        return jsonify({"ok": False, "message": "连接失败：%s" % e})


@app.route("/api/feishu/links")
def feishu_links():
    """飞书三张多维表格的快捷打开链接(供管理端入口)。"""
    cfg = _feishu_cfg()
    if not cfg:
        return jsonify({"ok": False, "links": {}})
    base = (cfg.get("base_url") or "").rstrip("/")
    tables = cfg.get("tables", {})
    def url(key):
        t = tables.get(key) or {}
        return ("%s/base/%s?table=%s" % (base, t.get("app_token", ""), t.get("table_id", ""))) if t.get("app_token") else ""
    return jsonify({"ok": True, "links": {"mentor": url("mentor"), "student": url("student"), "match": url("match")}})


def _open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    _c = _counts()
    print("=" * 56)
    print("  益志领 · 导师匹配系统已启动")
    print("  数据源：%s（导师 %d / 学生 %d）" % (CACHE["source"], _c["mentors"], _c["students"]))
    print("  浏览器打开：http://127.0.0.1:5000")
    print("  关闭本窗口或按 Ctrl+C 停止")
    print("=" * 56)
    threading.Timer(1.5, _open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)

from __future__ import annotations
import datetime
import json
import os
from typing import List, Tuple
from .models import Mentor, Student


class LocalLoader:
    """从本地 JSON 文件加载导师/学生数据（脱敏/mock）。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def load_mentors(self) -> List[Mentor]:
        path = os.path.join(self.data_dir, "mentors.json")
        with open(path, encoding="utf-8") as f:
            return [Mentor(**d) for d in json.load(f)]

    def load_students(self) -> List[Student]:
        path = os.path.join(self.data_dir, "students.json")
        with open(path, encoding="utf-8") as f:
            return [Student(**d) for d in json.load(f)]


# ---- 值规范化 ----
def _scalar(v):
    if v is None:
        return ""
    if isinstance(v, dict):
        return v.get("text") or v.get("name") or ""
    if isinstance(v, list):
        return _scalar(v[0]) if v else ""
    return v


def _as_list(v):
    if v is None:
        raw = []
    elif isinstance(v, str):
        raw = [v]
    elif isinstance(v, list):
        raw = [_scalar(x) for x in v]
    else:
        raw = [str(v)]
    out = []
    for it in raw:
        for part in str(it).split("、"):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _num(v) -> int:
    try:
        return int(float(_scalar(v)))
    except (ValueError, TypeError):
        return 0


def _bool(v) -> bool:
    return str(_scalar(v)).strip() in ("是", "True", "true", "1", "✓")


def _to_rating(v) -> float:
    """学生反馈平均分 1~10。"""
    try:
        return float(_scalar(v))
    except (ValueError, TypeError):
        return 0.0


MENTOR_CN = {
    "导师ID": "mentor_id", "性别": "gender", "常住城市": "city", "行业": "industry",
    "专精领域": "expertise", "期望辅导区域": "expected_regions", "期望学员性别": "expected_gender",
    "每月可用时长": "monthly_hours", "可同时辅导人数": "max_students", "擅长授课主题": "teach_topics",
    "可提供服务": "service_types", "画像标签": "tags", "已配学生数": "current_students", "已用时长": "used_hours",
    "累计服务时长": "total_hours", "累计服务学生数": "total_students",
    "好评率": "rating", "组织贡献分": "org_score", "当前星级": "star",
    "资质类型": "qualification", "毕业院校": "school", "工作年限": "work_years",
    "年度时长上限": "annual_hour_cap", "服务状态": "status", "飞书手机号": "feishu_mobile",
}
STUDENT_CN = {
    "学生ID": "student_id", "年级": "grade", "地区": "region", "性别": "gender",
    "感兴趣方向": "interested_fields", "需求类型": "needs", "性格": "personality",
    "要求同性别": "prefer_same_gender", "要求同地区": "prefer_same_region", "紧迫度": "urgency",
    "飞书手机号": "feishu_mobile",
}

# 写回时各维度独立列的中文短名（顺序即展示顺序）
DIM_SHORT = {"industry": "行业", "need": "需求", "service": "服务",
             "region": "地区", "personality": "性格", "profile": "画像"}


def mentor_from_cn(f: dict) -> Mentor:
    g = lambda cn: f.get(cn)
    return Mentor(
        mentor_id=_scalar(g("导师ID")), gender=_scalar(g("性别")),
        city=_scalar(g("常住城市")), industry=_scalar(g("行业")),
        expertise=_as_list(g("专精领域")), expected_regions=_as_list(g("期望辅导区域")),
        expected_gender=_scalar(g("期望学员性别")),
        monthly_hours=_num(g("每月可用时长")), max_students=_num(g("可同时辅导人数")),
        teach_topics=_as_list(g("擅长授课主题")), service_types=_as_list(g("可提供服务")),
        tags=_as_list(g("画像标签")), current_students=_num(g("已配学生数")),
        used_hours=_num(g("已用时长")),
        total_hours=_num(g("累计服务时长")), total_students=_num(g("累计服务学生数")),
        rating=_to_rating(g("好评率")), org_score=_num(g("组织贡献分")),
        star=_num(g("当前星级")),
        qualification=_scalar(g("资质类型")), school=_scalar(g("毕业院校")),
        work_years=_num(g("工作年限")),
        annual_hour_cap=_num(g("年度时长上限")),
        feishu_mobile=_scalar(g("飞书手机号")),
    )


def student_from_cn(f: dict) -> Student:
    g = lambda cn: f.get(cn)
    return Student(
        student_id=_scalar(g("学生ID")), grade=_scalar(g("年级")),
        region=_scalar(g("地区")), gender=_scalar(g("性别")),
        interested_fields=_as_list(g("感兴趣方向")), needs=_as_list(g("需求类型")),
        personality=_scalar(g("性格")),
        prefer_same_gender=_bool(g("要求同性别")),
        prefer_same_region=_bool(g("要求同地区")),
        urgency=_num(g("紧迫度")),
        feishu_mobile=_scalar(g("飞书手机号")),
    )


class FeishuLoader:
    """飞书多维表格数据源：读导师/学生表，写匹配结果（每次新建一个数据表）。"""

    def __init__(self, app_id: str, app_secret: str, tables: dict, base_url: str = ""):
        import lark_oapi as lark
        from lark_oapi.api.bitable import v1 as b
        self.b = b
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        self.tables = tables
        self.base_url = (base_url or "https://feishu.cn").rstrip("/")
        self.mentor_missing_columns = []  # load_mentors 后填充，供前端提示补数据

    def _check(self, resp, action):
        if not resp.success():
            raise RuntimeError("【%s】失败 code=%s msg=%s log_id=%s"
                               % (action, resp.code, resp.msg, getattr(resp, "log_id", "")))
        return resp

    def _list_with_ids(self, app_token, table_id):
        out, page_token = [], None
        while True:
            rb = (self.b.ListAppTableRecordRequest.builder()
                  .app_token(app_token).table_id(table_id).page_size(500))
            if page_token:
                rb = rb.page_token(page_token)
            resp = self._check(self.client.bitable.v1.app_table_record.list(rb.build()), "读取记录")
            for item in (resp.data.items or []):
                out.append((item.record_id, item.fields or {}))
            if not resp.data.has_more:
                break
            page_token = resp.data.page_token
        return out

    def _list_records(self, app_token, table_id):
        return [f for _id, f in self._list_with_ids(app_token, table_id)]

    def _field_types(self, app_token, table_id):
        req = (self.b.ListAppTableFieldRequest.builder()
               .app_token(app_token).table_id(table_id).page_size(100).build())
        resp = self._check(self.client.bitable.v1.app_table_field.list(req), "读取字段类型")
        return {f.field_name: f.type for f in (resp.data.items or [])}

    def _ensure_field(self, app_token, table_id, name, ftype):
        try:
            req = (self.b.CreateAppTableFieldRequest.builder()
                   .app_token(app_token).table_id(table_id)
                   .request_body(self.b.AppTableField.builder().field_name(name).type(ftype).build())
                   .build())
            resp = self.client.bitable.v1.app_table_field.create(req)
            return resp.success()
        except Exception:
            return False

    # ---- 读：导师 / 学生 ----
    def load_mentors(self) -> List[Mentor]:
        t = self.tables["mentor"]
        at, tid = t["app_token"], t["table_id"]
        types = self._field_types(at, tid)
        # 检测影响匹配的缺失列：缺「期望辅导区域」会让地区维度走城市兜底，提示案主补列
        self.mentor_missing_columns = [c for c in ("期望辅导区域",) if c not in types]
        return [mentor_from_cn(row) for row in self._list_records(at, tid)]

    def load_students(self) -> List[Student]:
        t = self.tables["student"]
        return [student_from_cn(row) for row in self._list_records(t["app_token"], t["table_id"])]

    # ---- 写：匹配结果 ----
    def _build_records(self, rows, dim_labels, types):
        records = []
        for i, r in enumerate(rows, 1):
            sub = r.get("sub_scores", {})
            dim_text = "  ".join("%s %.2f" % (dim_labels[k], sub.get(k, 0)) for k in dim_labels)
            fields = {
                "匹配ID": "M%s" % r.get("rank", i),
                "学生ID": r["student_id"],
                "导师ID": r["mentor_id"],
                "综合得分": r["total"],
                "各维度得分": dim_text,
                "排名": r.get("rank", i),
                "匹配理由": r.get("reason", ""),
                "状态": "待确认",
            }
            for key, label in dim_labels.items():
                col = label + "得分"
                if col in types:
                    fields[col] = sub.get(key, 0)
            records.append(self.b.AppTableRecord.builder()
                           .fields({k: self._fmt(v, types.get(k, 1)) for k, v in fields.items()})
                           .build())
        return records

    def _batch_create(self, app_token, table_id, records, action):
        req = (self.b.BatchCreateAppTableRecordRequest.builder()
               .app_token(app_token).table_id(table_id)
               .request_body(self.b.BatchCreateAppTableRecordRequestBody.builder()
                             .records(records).build()).build())
        self._check(self.client.bitable.v1.app_table_record.batch_create(req), action)

    def write_matches(self, rows, dim_labels=None):
        """写入【现有的】匹配结果表（各维度独立列，不存在自动建）。"""
        dim_labels = dim_labels or DIM_SHORT
        t = self.tables["match"]
        at, tid = t["app_token"], t["table_id"]
        types = self._field_types(at, tid)
        for key, label in dim_labels.items():
            col = label + "得分"
            if col not in types and self._ensure_field(at, tid, col, 2):
                types[col] = 2
        records = self._build_records(rows, dim_labels, types)
        self._batch_create(at, tid, records, "写回匹配结果")
        return len(records)

    def _match_table_fields(self, dim_labels):
        b = self.b
        def fld(name, t):
            return b.AppTableField.builder().field_name(name).type(t).build()
        fields = [fld("匹配ID", 1), fld("学生ID", 1), fld("导师ID", 1),
                  fld("综合得分", 2), fld("各维度得分", 1)]
        for label in dim_labels.values():
            fields.append(fld(label + "得分", 2))
        fields += [fld("排名", 2), fld("匹配理由", 1), fld("状态", 1)]
        return fields

    def create_match_table(self, name, dim_labels=None) -> str:
        """在匹配结果文档里新建一个数据表（含完整字段），返回 table_id。"""
        dim_labels = dim_labels or DIM_SHORT
        t = self.tables["match"]
        req = (self.b.CreateAppTableRequest.builder().app_token(t["app_token"])
               .request_body(self.b.CreateAppTableRequestBody.builder()
                 .table(self.b.ReqTable.builder().name(name)
                        .fields(self._match_table_fields(dim_labels)).build())
                 .build()).build())
        resp = self._check(self.client.bitable.v1.app_table.create(req), "新建匹配表「%s」" % name)
        return resp.data.table_id

    def write_matches_new_table(self, student_label, rows, dim_labels=None) -> Tuple[str, str]:
        """每次写回新建一个数据表，命名「{学生} {日期 时分秒} 匹配表」。
        带时分秒保证同一天多次写回同一学生不会因表名重复（飞书 1254013）失败。
        返回 (table_id, 打开链接)。"""
        dim_labels = dim_labels or DIM_SHORT
        t = self.tables["match"]
        name = "%s %s 匹配表" % (student_label, datetime.datetime.now().strftime("%Y-%m-%d %H%M%S"))
        tid = self.create_match_table(name, dim_labels)
        types = self._field_types(t["app_token"], tid)
        records = self._build_records(rows, dim_labels, types)
        self._batch_create(t["app_token"], tid, records, "写入新匹配表")
        url = "%s/base/%s?table=%s" % (self.base_url, t["app_token"], tid)
        return tid, url

    def add_mentor(self, form: dict):
        """把一条报名(中文 key dict)写入飞书导师表。用于招募审核通过入库。缺列自动补建,避免 1254045。"""
        t = self.tables["mentor"]
        at, tid = t["app_token"], t["table_id"]
        types = self._field_types(at, tid)
        multi = ("专精领域", "期望辅导区域", "擅长授课主题", "可提供服务", "画像标签")
        num_cols = ("可同时辅导人数", "工作年限", "每月可用时长", "已用时长",
                    "累计服务时长", "累计服务学生数")
        # 报名表里出现、但导师表不存在的列 → 自动补建(数字 2 / 多选 11 / 文本 1)
        for cn in form:
            if cn in types or not form.get(cn):
                continue
            ftype = 2 if cn in num_cols else (11 if cn in multi else 1)
            if self._ensure_field(at, tid, cn, ftype):
                types[cn] = ftype
        fields = {}
        for cn, v in form.items():
            if v is None or v == "":
                continue
            if cn in multi and isinstance(v, str):
                v = [s.strip() for s in v.split("、") if s.strip()]
            fields[cn] = v
        rec = (self.b.AppTableRecord.builder()
               .fields({k: self._fmt(v, types.get(k, 1)) for k, v in fields.items()}).build())
        self._batch_create(at, tid, [rec], "招募审核通过-新增导师")
        return True

    def update_mentor_fields(self, mentor_id, fields_cn):
        """更新飞书导师表里某导师(按 导师ID 匹配)的字段。fields_cn: 中文 key dict。缺列自动补建。"""
        t = self.tables["mentor"]
        at, tid = t["app_token"], t["table_id"]
        types = self._field_types(at, tid)
        num_cols = ("可同时辅导人数", "已配学生数", "年度时长上限", "工作年限",
                    "累计服务时长", "累计服务学生数", "已用时长", "每月可用时长")
        for k in fields_cn:
            if k not in types:
                ftype = 2 if k in num_cols else 1
                if self._ensure_field(at, tid, k, ftype):
                    types[k] = ftype
        rid = None
        for _rid, f in self._list_with_ids(at, tid):
            if _scalar(f.get("导师ID")) == mentor_id:
                rid = _rid
                break
        if not rid:
            raise RuntimeError("飞书导师表未找到导师 %s" % mentor_id)
        rec = (self.b.AppTableRecord.builder().record_id(rid)
               .fields({k: self._fmt(v, types.get(k, 1)) for k, v in fields_cn.items()}).build())
        req = (self.b.BatchUpdateAppTableRecordRequest.builder()
               .app_token(at).table_id(tid)
               .request_body(self.b.BatchUpdateAppTableRecordRequestBody.builder()
                             .records([rec]).build()).build())
        self._check(self.client.bitable.v1.app_table_record.batch_update(req), "更新导师字段")
        return True

    def send_text(self, receive_id_type, receive_id, text):
        """发飞书文本消息。receive_id_type 是 query 参数(mobile/chat_id/open_id),body 含 receive_id/msg_type/content。"""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        body = (CreateMessageRequestBody.builder()
                .receive_id(receive_id).msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False, separators=(",", ":"))).build())
        req = (CreateMessageRequest.builder()
               .receive_id_type(receive_id_type).request_body(body).build())
        resp = self.client.im.v1.message.create(req)
        if not resp.success():
            raise RuntimeError("飞书消息发送失败 code=%s msg=%s" % (resp.code, resp.msg))
        return True

    def mobile_to_open_id(self, mobile):
        """通过手机号查飞书 open_id(需应用有通讯录 mobile 查询权限 + 号码在可见范围)。失败抛具体原因。"""
        from lark_oapi.api.contact.v3 import BatchGetIdUserRequest, BatchGetIdUserRequestBody
        body = BatchGetIdUserRequestBody.builder().mobiles([mobile]).build()
        req = BatchGetIdUserRequest.builder().user_id_type("open_id").request_body(body).build()
        resp = self.client.contact.v3.user.batch_get_id(req)
        if not resp.success():
            raise RuntimeError("手机号查 open_id 失败 code=%s msg=%s(检查 contact:user.id 权限)" % (resp.code, resp.msg))
        users = getattr(resp.data, "user_list", None) or []
        if not users or not users[0].user_id:
            raise RuntimeError("手机号 %s 未查到飞书用户(未绑飞书或不在应用通讯录可见范围)" % mobile)
        return users[0].user_id

    def send_to_mobile(self, mobile, text):
        oid = self.mobile_to_open_id(mobile)
        if not oid:
            raise RuntimeError("无法通过手机号 %s 查到飞书用户(需通讯录权限或该号未绑飞书)" % mobile)
        return self.send_text("open_id", oid, text)

    def send_to_chat(self, chat_id, text):
        return self.send_text("chat_id", chat_id, text)

    def delete_empty_rows(self) -> int:
        t = self.tables["match"]
        at, tid = t["app_token"], t["table_id"]
        ids = [rid for rid, f in self._list_with_ids(at, tid) if not _scalar(f.get("学生ID"))]
        if not ids:
            return 0
        req = (self.b.BatchDeleteAppTableRecordRequest.builder()
               .app_token(at).table_id(tid)
               .request_body(self.b.BatchDeleteAppTableRecordRequestBody.builder()
                             .records(ids).build())
               .build())
        self._check(self.client.bitable.v1.app_table_record.batch_delete(req), "删除空行")
        return len(ids)

    @staticmethod
    def _fmt(value, type_code):
        if type_code == 2:
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0
        if type_code in (4, 11):   # 4=复选, 11=多选
            return _as_list(value)
        if type_code == 7:
            return _bool(value)
        return str(_scalar(value))

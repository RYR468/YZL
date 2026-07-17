"""一键在飞书创建多维表格（导师表 / 学生表 / 匹配结果表）+ 导入 mock 数据。

前置：
  1) pip install lark-oapi
  2) 在 https://open.feishu.cn 建好"自建应用"，开通权限：
       多维表格：bitable:app （查看、评论、编辑和管理云空间中所有多维表格）
  3) 拿到 App ID（cli_xxx）和 App Secret。

运行（任选一种方式提供凭证）：
  方式A 环境变量：
      set FEISHU_APP_ID=cli_xxx
      set FEISHU_APP_SECRET=你的secret
      python feishu_setup.py
  方式B 用网页「飞书连接」里已保存的凭证（config/feishu.json）：
      python feishu_setup.py

结束后会打印 app_token 和三张表的 table_id——把它们填到网页「飞书连接」里即可对接。

注意：飞书 SDK 各版本 API 细节偶有差异，若运行报错，把完整报错贴给我，我来改。
"""
from __future__ import annotations
import csv
import json
import os
import sys

try:
    import lark_oapi as lark
    from lark_oapi.api.bitable import v1 as b
except ImportError:
    print("请先安装飞书 SDK： pip install lark-oapi")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# lark 多维表格字段类型代码
TEXT, NUMBER, SINGLE, MULTI, CHECK, DATE = 1, 2, 3, 4, 7, 5

# 表结构定义：(列名, 类型, [可选]单/多选的预设选项)
MENTOR_SPEC = [
    ("导师ID", TEXT), ("性别", SINGLE, ["男", "女"]), ("常住城市", TEXT), ("行业", TEXT),
    ("专精领域", MULTI), ("期望辅导区域", MULTI), ("期望学员性别", SINGLE, ["不限", "男", "女"]),
    ("每月可用时长", NUMBER), ("可同时辅导人数", NUMBER), ("擅长授课主题", MULTI),
    ("可提供服务", MULTI), ("画像标签", MULTI), ("已配学生数", NUMBER), ("已用时长", NUMBER),
]
STUDENT_SPEC = [
    ("学生ID", TEXT), ("年级", TEXT), ("地区", TEXT), ("性别", SINGLE, ["男", "女"]),
    ("感兴趣方向", MULTI), ("需求类型", MULTI), ("性格", SINGLE, ["内向", "外向", "未知"]),
    ("要求同性别", CHECK), ("要求同地区", CHECK), ("紧迫度", NUMBER),
    ("状态", SINGLE, ["待匹配", "已匹配"]),
]
MATCH_SPEC = [
    ("匹配ID", TEXT), ("学生ID", TEXT), ("导师ID", TEXT), ("综合得分", NUMBER),
    ("各维度得分", TEXT), ("排名", NUMBER), ("匹配理由", TEXT),
    ("状态", SINGLE, ["待确认", "已确认", "已调整"]), ("时间", DATE),
]


def get_creds():
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        path = os.path.join(HERE, "config", "feishu.json")
        if os.path.exists(path):
            cfg = json.load(open(path, encoding="utf-8"))
            app_id, app_secret = cfg.get("app_id"), cfg.get("app_secret")
    if not app_id or not app_secret:
        print("缺少飞书凭证。请设置 FEISHU_APP_ID / FEISHU_APP_SECRET，或在网页保存凭证。")
        sys.exit(1)
    return app_id, app_secret


def check(resp, action):
    """统一处理 lark 响应：失败则打印并退出。"""
    if not resp.success():
        print("【%s】失败" % action)
        print("  code:", resp.code, " msg:", resp.msg)
        if resp.log_id:
            print("  log_id:", resp.log_id)
        sys.exit(1)
    return resp


def field_builder(name, ftype, options=None):
    fb = b.AppTableField.builder().field_name(name).type(ftype)
    if options is not None:  # 单选/多选的选项
        opts = [b.AppTableSelectOption.builder().name(o).build() for o in options]
        fb = fb.property(b.AppTableFieldProperty.builder().options(opts).build())
    return fb.build()


def create_table(client, app_token, table_name, spec):
    """建一张表（含字段），返回 table_id。"""
    fields = []
    for item in spec:
        name, ftype = item[0], item[1]
        options = item[2] if len(item) > 2 else None
        fields.append(field_builder(name, ftype, options))
    req = (b.CreateAppTableRequest.builder()
           .app_token(app_token)
           .request_body(b.CreateAppTableRequestBody.builder()
                         .table(b.ReqTable.builder().name(table_name).fields(fields).build())
                         .build())
           .build())
    resp = check(client.bitable.v1.app_table.create(req), "建表 %s" % table_name)
    return resp.data.table_id


def csv_rows(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_value(raw, ftype):
    if raw is None:
        return None
    if ftype == NUMBER:
        try:
            return float(raw)
        except ValueError:
            return None
    if ftype == MULTI:
        return [x for x in (raw or "").split("、") if x]
    if ftype == CHECK:
        return str(raw).strip() in ("是", "True", "true", "1")
    if ftype == SINGLE:
        return raw or ""
    return raw  # text


def insert_records(client, app_token, table_id, spec, csv_name):
    rows = csv_rows(csv_name)
    if not rows:
        print("  （%s 无数据，跳过导入）" % csv_name)
        return
    type_by_name = {n: t for n, t, *_ in spec}
    records = []
    for row in rows:
        fields = {name: to_value(row.get(name, ""), type_by_name[name]) for name in type_by_name}
        records.append(b.AppTableRecord.builder().fields(fields).build())
    req = (b.BatchCreateAppTableRecordRequest.builder()
           .app_token(app_token).table_id(table_id)
           .request_body(b.BatchCreateAppTableRecordRequestBody.builder().records(records).build())
           .build())
    check(client.bitable.v1.app_table_record.batch_create(req), "导入 %s" % csv_name)
    print("  已导入 %d 条 → %s" % (len(records), csv_name))


def main():
    app_id, app_secret = get_creds()
    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    # 1) 创建一个多维表格
    req = (b.CreateAppRequest.builder()
           .request_body(b.CreateAppRequestBody.builder().name("益志领导师匹配").build())
           .build())
    resp = check(client.bitable.v1.app.create(req), "创建多维表格")
    app_token = resp.data.app.app_token
    print("✅ 多维表格已创建，app_token =", app_token)

    # 2) 建三张表
    print("正在建表…")
    tables = {
        "导师表": (create_table(client, app_token, "导师表", MENTOR_SPEC), MENTOR_SPEC, "mentors.csv"),
        "学生表": (create_table(client, app_token, "学生表", STUDENT_SPEC), STUDENT_SPEC, "students.csv"),
        "匹配结果表": (create_table(client, app_token, "匹配结果表", MATCH_SPEC), MATCH_SPEC, "matches_template.csv"),
    }

    # 3) 导入 mock 数据
    print("正在导入数据…")
    for tname, (table_id, spec, csv_name) in tables.items():
        print("[%s] table_id = %s" % (tname, table_id))
        insert_records(client, app_token, table_id, spec, csv_name)

    print("\n🎉 全部完成！把下面这些填到网页「飞书连接」里：")
    print("  app_token =", app_token)
    for tname, (table_id, _, _) in tables.items():
        print("  %s table_id = %s" % (tname, table_id))


if __name__ == "__main__":
    main()

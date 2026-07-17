from __future__ import annotations
import os
from typing import Dict
from .models import Mentor, Student


def template_reason(m: Mentor, s: Student, subs: Dict[str, float]) -> str:
    """模板化匹配理由（无需任何外部依赖，v1/v1.5 都可用）。"""
    points = []
    if subs.get("industry", 0) >= 0.5:
        points.append(f"行业方向契合（{m.industry}）")
    if subs.get("need", 0) >= 0.5:
        topics = "、".join(m.teach_topics[:2]) if m.teach_topics else "—"
        points.append(f"擅长主题可覆盖需求（{topics}）")
    if subs.get("service", 0) >= 0.5:
        points.append(f"可提供服务：{'、'.join(m.service_types) or '—'}")
    if subs.get("region", 0) >= 0.7:
        points.append(f"地区匹配（{m.city}）")
    body = "；".join(points) if points else "基础匹配"
    if m.free_slots <= 1:
        body += f"；⚠️剩余容量仅 {m.free_slots}，建议尽早对接"
    return f"推荐 {m.mentor_id}：{body}。综合得分 {subs['total']:.2f}"


def llm_reason(m: Mentor, s: Student, subs: Dict[str, float]) -> str:
    """LLM 生成有温度的匹配理由。需同时设置环境变量 OPENAI_API_KEY 与 OPENAI_MODEL；
    缺失则回退到 template_reason。可选 OPENAI_BASE_URL 指向兼容接口。"""
    key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not key or not model:
        return template_reason(m, s, subs)
    try:
        import openai
        client = openai.OpenAI(
            api_key=key,
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
        info = (
            f"学生：{s.grade}，{s.region}，{s.gender}，"
            f"意向「{'、'.join(s.interested_fields) or '不限'}」，"
            f"需求「{'、'.join(s.needs) or '无'}」，性格{s.personality or '未知'}；"
            f"导师：行业{m.industry}，擅长「{'、'.join(m.teach_topics)}」，"
            f"可提供服务「{'、'.join(m.service_types)}」，城市{m.city}；"
            f"各维度得分：{subs}。"
        )
        prompt = (
            "你是公益基金会的导师匹配助手。请用一段有温度、具体的中文（不超过80字）"
            "向运营解释：为什么推荐这位导师给这个学生。只说优点和注意事项，不要套话。\n"
            + info
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # 任何异常都安全回退，保证流程不中断
        return template_reason(m, s, subs) + f"（LLM 不可用，已用模板：{type(e).__name__}）"

# 益志领 · 学生↔导师匹配 MVP

为上海益志领公益基金会开发的 **AI Agent 驱动志愿者导师全流程管理体系** 中的 **匹配核心**。
给定一个待匹配学生 → 系统输出 **Top-N 导师候选 + 各维度得分 + 匹配理由**，供运营一键确认。

> 案主需求与整体方案见计划文件。本仓库先落地 **v1.5 匹配引擎**（可独立运行、不依赖外部凭证），
> v1（飞书原生多维表格）在飞书界面搭建，飞书 API 读写待凭证就绪后接入（见下文「接入飞书」）。

---

## 快速开始

```bash
cd "d:\py\AI CAMP"

# 跑全部 mock 学生，每个返回 Top5
python agent.py

# 只跑某个学生
python agent.py --student S001

# Top3，并把结果写入 JSON（仿飞书 matches 表 schema）
python agent.py --top 3 --out matches_output.json

# 用 LLM 生成有温度的匹配理由（需先设环境变量）
set OPENAI_API_KEY=sk-xxx
set OPENAI_MODEL=gpt-4o-mini        # 或豆包/DeepSeek/智谱等兼容模型
set OPENAI_BASE_URL=https://...     # 可选，非 OpenAI 官方时设置
python agent.py --llm
```

> 核心引擎只用 Python 标准库 + JSON 配置，**无需 pip install 即可运行**。
> LLM / 飞书 / YAML 是可选增强（见 `requirements.txt`）。

---

## 匹配逻辑

**Step 1 硬过滤（剔除不达标）**：容量不足 / 不满足同性别·同地区偏好 / 完全不覆盖学生需求 → 剔除。规则在 `config/hard_filters.json`。

**Step 2 加权打分**：`总分 = Σ(权重 × 子匹配度)`，按权重总和归一化。6 个维度（权重在 `config/weights.json` 可调）：

| 维度 | 默认权重 | 含义 |
|---|---|---|
| industry | 0.35 | 行业/专业方向契合（核心） |
| need | 0.25 | 导师擅长主题 vs 学生需求（核心） |
| service | 0.15 | 导师愿提供的服务类型 vs 学生需要 |
| region | 0.15 | 地区/区域契合 |
| personality | 0.05 | 性格（老师明确权重应低） |
| profile | 0.05 | 画像标签软契合 |

**Step 3 取 Top-N** 按总分排序。

**Step 4 生成理由**：默认模板拼接命中点；`--llm` 时调用 LLM 生成有温度的自然语言理由。

---

## 目录结构

```
AI CAMP/
  agent.py                 # 端到端 CLI（读数据→过滤→打分→理由→输出）
  config/
    weights.json           # 各维度权重（运营/老师可调）
    hard_filters.json      # 硬过滤开关
    synonyms.json          # 行业同义词、需求→主题/服务 映射
  data/
    mentors.json           # mock 脱敏导师（字段对齐《导师报名表》）
    students.json          # mock 学生（数值 mock）
  matching/
    models.py              # Mentor / Student 数据类
    config.py              # 配置加载（yaml 优先，回退 json）
    loader.py              # LocalLoader（本地JSON）/ FeishuLoader（v1.5 待实现）
    dimensions.py          # 各维度 0~1 子匹配度
    filters.py             # 硬过滤
    scoring.py             # 加权打分
    reason.py              # 模板理由 + LLM 理由（双模式）
  tests/
    test_matching.py       # 单元测试（python tests/test_matching.py 即可跑）
```

---

## 调权重看效果（呼应老师「权重要活」）

改 `config/weights.json` 的数字，重跑 `python agent.py`，观察排名变化。
例如把 `industry` 调高、`personality` 调低，行业契合的导师会上升。无需改代码。

---

## 接入飞书（v1.5，待凭证）

数据源当前是本地 JSON。接入飞书多维表格时，只需实现 `matching/loader.py` 里的 `FeishuLoader`，
替换 `agent.py` 中的 `LocalLoader`，**匹配逻辑无需改动**：

1. 在飞书开放平台创建自建应用，拿到 `app_id` / `app_secret`。
2. 给应用开通多维表格读写权限，并授权目标多维表格（导师表 / 学生表 / 匹配结果表，字段名对齐 `models.py`）。
3. `pip install lark-oapi`，在 `FeishuLoader` 里用 SDK 读取导师/学生记录、回写匹配结果。
4. （可选）匹配确认后，用飞书消息 API 自动通知师生。

三张表结构（飞书多维表格）：
- **导师表 mentors**：报名表字段 + 画像标签 + 容量状态（`剩余容量 = 可同时辅导人数 - 已配学生数`）
- **学生表 students**：学生字段 + `状态`（待匹配/已匹配）
- **匹配结果表 matches**：`match_id / student_id / mentor_id / 总分 / 各维度子分 / 匹配理由 / 状态(待确认/已确认/已调整) / 时间`

---

## 数据脱敏（老师硬要求）

- 导师真实姓名 → `mentor_id`（M001…），不存真实姓名/手机/邮箱到仓库。
- 学生全部 mock（S001…），不含任何真实个人信息。
- 真实数据由基金会提供脱敏版本，置于 `data/`，**勿提交未脱敏数据到 GitHub**。

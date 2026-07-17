from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class Mentor:
    """导师（字段来自《人生职业导师报名表》，姓名等已脱敏）。"""

    mentor_id: str = ""
    gender: str = ""                 # 性别
    city: str = ""                 # 常住城市
    industry: str = ""               # 行业
    expertise: List[str] = field(default_factory=list)        # 专精行业与擅长领域
    expected_regions: List[str] = field(default_factory=list)  # 期望辅导学员的区域
    expected_gender: str = ""            # 期望学员性别（""=不限）
    monthly_hours: int = 0             # 每月可用辅导时长
    max_students: int = 0             # 可同时辅导学员人数
    teach_topics: List[str] = field(default_factory=list)   # 擅长授课主题
    service_types: List[str] = field(default_factory=list)  # 愿与提供：线上沟通/线下活动/公益营授课/电话回访
    tags: List[str] = field(default_factory=list)     # 导师画像标签（AI 生成）
    current_students: int = 0           # 已配学生数
    used_hours: int = 0               # 已用时长
    # ---- 激励体系字段（见 docs/incentive_design.md，默认 0，数据补齐后启用）----
    total_hours: int = 0              # 累计服务时长（激励用；缺省回退 used_hours）
    total_students: int = 0           # 累计服务学生数（激励用；缺省回退 current_students）
    rating: float = 0.0               # 学生反馈平均分 1~10（来自反馈模块）
    org_score: int = 0                # 深度贡献分（拉新导师/赞助/课程开发/治理建议，运营登记）
    star: int = 0                     # （旧 5 星字段，保留兼容，不再使用）
    # ---- 发展与赋能体系 L1-L3 ----
    level: str = ""                   # 导师级别 L1/L2/L3（系统算出）
    level_name: str = ""              # 级别名 新锐/资深/首席
    company: str = ""                 # 所在机构（致信 CEO 机制所需）
    status: str = "活跃"              # 服务状态 活跃/停牌/移除
    # ---- 招募资质（招募令第6条：名校/500强/创业者，入库门槛）----
    qualification: str = ""           # 资质类型：世界500强中高层/全球前100强毕业/优秀创业者
    school: str = ""                  # 毕业院校
    work_years: int = 0               # 工作年限
    annual_hour_cap: int = 0          # 个人年度服务时长上限（0=不限），超额预警
    cert_status: str = ""             # 证书审核状态:""(派生) / auto / approved / pending
    feishu_mobile: str = ""           # 飞书绑定手机号(用于发消息通知)

    @property
    def free_slots(self) -> int:
        """剩余可辅导名额（用于容量硬过滤）。"""
        return max(0, self.max_students - self.current_students)


@dataclass
class Student:
    """学生（数据仅给字段，数值 mock：学生001…）。"""

    student_id: str = ""
    grade: str = ""                    # 年级，如高一
    region: str = ""                  # 地区/生源
    gender: str = ""                    # 性别
    interested_fields: List[str] = field(default_factory=list)  # 感兴趣专业/职业方向
    needs: List[str] = field(default_factory=list)        # 需求类型：职业启蒙/价值观/心理/学业
    personality: str = ""               # 内向/外向
    prefer_same_gender: bool = False       # 是否要求同性别导师
    prefer_same_region: bool = False      # 是否要求同地区导师
    urgency: int = 0                  # 紧迫度
    feishu_mobile: str = ""           # 飞书绑定手机号(用于发消息通知)

"""全局领域常量。

集中定义环节、评分维度、状态枚举，避免各处硬编码字符串不一致。
后端与前端展示文案共用同一套 key。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------- 面试环节
INTRO = "intro"
RESUME_DEEP_DIVE = "resume_deep_dive"
HARD_SKILL = "hard_skill"
BEHAVIORAL = "behavioral"
PRESSURE = "pressure"
CANDIDATE_ASK = "candidate_ask"

STAGES: list[str] = [
    INTRO,
    RESUME_DEEP_DIVE,
    HARD_SKILL,
    BEHAVIORAL,
    PRESSURE,
    CANDIDATE_ASK,
]

STAGE_META: dict[str, dict] = {
    INTRO: {"label": "开场与自我介绍", "weight": 0.08, "goal": "破冰并验证自我介绍与岗位匹配度"},
    RESUME_DEEP_DIVE: {
        "label": "简历深挖",
        "weight": 0.27,
        "goal": "深挖简历中 2 段最相关的项目经历",
    },
    HARD_SKILL: {"label": "专业技能", "weight": 0.30, "goal": "按 JD 硬技能权重考察专业深度"},
    BEHAVIORAL: {"label": "行为面试", "weight": 0.15, "goal": "用 STAR 考察协作、抗压、主动性"},
    PRESSURE: {"label": "压力追问", "weight": 0.12, "goal": "质疑数据合理性、追问边界条件"},
    CANDIDATE_ASK: {"label": "候选人反问", "weight": 0.08, "goal": "候选人反问，评估求职动机"},
}

# ---------------------------------------------------------------- 会话状态
STATUS_CREATED = "created"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_FINISHED = "finished"
STATUS_ABORTED = "aborted"

SESSION_STATUSES = [
    STATUS_CREATED,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_FINISHED,
    STATUS_ABORTED,
]

# 这些状态下可以继续答题
ACTIVE_STATUSES = (STATUS_CREATED, STATUS_RUNNING, STATUS_PAUSED)

# ---------------------------------------------------------------- 评分维度
DIMENSIONS: list[str] = ["relevance", "structure", "depth", "delivery", "fit"]

DIMENSION_WEIGHTS: dict[str, float] = {
    "relevance": 0.20,
    "structure": 0.20,
    "depth": 0.25,
    "delivery": 0.15,
    "fit": 0.20,
}

DIMENSION_LABELS: dict[str, str] = {
    "relevance": "内容相关性",
    "structure": "结构逻辑",
    "depth": "专业深度",
    "delivery": "表达流畅",
    "fit": "岗位匹配",
}

# ---------------------------------------------------------------- 面试配置
INTERVIEW_TYPES: dict[str, str] = {
    "technical": "技术面",
    "behavioral": "行为面",
    "comprehensive": "综合终面",
    "hr": "HR 面",
}

DIFFICULTIES: dict[str, str] = {
    "intern": "实习",
    "campus": "校招",
    "bigtech": "大厂",
}

DURATIONS: list[int] = [15, 30, 45]

LANGUAGES: dict[str, str] = {"zh": "中文", "en": "英文"}

# 多轮模式下每个环节换一位面试官（更接近真实校招流程）
INTERVIEWER_MODES: dict[str, str] = {
    "panel": "多轮换人（推荐）",
    "single": "单人整场",
}

# ---------------------------------------------------------------- 面试模式
# text：纯文字打字；video：摄像头 + 麦克风，真实视频面试
INTERVIEW_MODES: dict[str, str] = {
    "text": "文字面试",
    "video": "视频面试",
}

# ---------------------------------------------------------------- 表达指标
# 用于把「语速 / 口头禅 / 停顿」变成可评分的数字，而不是让模型凭感觉说"表达流畅"
FILLER_WORDS: list[str] = [
    "然后", "就是", "那个", "这个", "其实", "反正", "怎么说呢",
    "呃", "嗯", "啊", "吧", "嘛", "的话", "对吧", "你知道",
]

# 理想语速区间（字/分钟）。低于下限像背稿或没想清楚，高于上限像赶时间。
SPEECH_RATE_MIN = 180
SPEECH_RATE_MAX = 320

# 单次停顿时长阈值（毫秒）：超过视为"卡壳"
LONG_PAUSE_MS = 2500


# ---------------------------------------------------------------- 追问规则
MAX_FOLLOWUP_DEPTH = 2  # 同一考察点最多追问层数
FOLLOWUP_TIME_GUARD = 0.20  # 剩余时间低于此比例时停止追问
WRAPUP_TIME_GUARD = 0.05  # 剩余时间低于此比例时直接进入反问环节

# ---------------------------------------------------------------- 面试官意图
# 架构决策：**决策与措辞分离**。
# 服务端用确定性规则决定「这一轮该干什么」（可单测），
# LLM 只负责把这件事说得像个真人面试官（流式、纯文本）。
INTENT_OPENING = "opening"
INTENT_NEW_COMPETENCY = "new_competency"
INTENT_FOLLOWUP_DETAIL = "followup_detail"  # 追问数字 / 技术细节的来源
INTENT_FOLLOWUP_CONCRETE = "followup_concrete"  # 回答太空泛，要具体案例
INTENT_FOLLOWUP_CHALLENGE = "followup_challenge"  # 质疑不自洽 / 追问边界条件
INTENT_STAGE_TRANSITION = "stage_transition"
INTENT_WRAPUP = "wrapup"

INTENT_LABELS: dict[str, str] = {
    INTENT_OPENING: "开场并请候选人自我介绍",
    INTENT_NEW_COMPETENCY: "切换到新的考察点，提出该考察点的主问题",
    INTENT_FOLLOWUP_DETAIL: "追问上一轮回答中具体数字或技术细节的来源与做法",
    INTENT_FOLLOWUP_CONCRETE: "上一轮回答过于空泛，要求给出具体案例或数据",
    INTENT_FOLLOWUP_CHALLENGE: "对候选人数据或结论的自洽性提出温和质疑，追问边界条件",
    INTENT_STAGE_TRANSITION: "结束当前环节并自然过渡到下一环节",
    INTENT_WRAPUP: "收尾，请候选人提问",
}

# 判定回答「空泛」的信号词（无数字、无技术名词时命中即视为空泛）
VAGUE_MARKERS: list[str] = [
    "参与了",
    "负责了",
    "协助",
    "提升了性能",
    "优化了",
    "做了",
    "搞了",
    "一些",
    "等等",
    "差不多",
    "挺好的",
]

# 技术名词信号（命中即认为回答包含可追问的细节）
TECH_TOKEN_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+#._-]{1,}|"
    r"[\u4e00-\u9fa5]{2,8}(?:索引|缓存|队列|事务|锁|分片|集群|框架|算法|模型|接口|服务|中间件|数据库))"
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|ms|毫秒|秒|s|万|亿|倍|QPS|qps|TPS|次|人|天|G|M|K)?")

# 上下文压缩
RECENT_TURNS_FULL = 4  # 最近 N 轮保留全文，更早轮次压缩为摘要

DEFAULT_CONFIG: dict = {
    "interview_type": "comprehensive",
    "duration_min": 30,
    "difficulty": "campus",
    "language": "zh",
    "pressure_mode": True,
    # 反馈模式：
    #   practice   练习模式 —— 每答完一题立刻在对话内显示评分卡（学得快）
    #   simulation 模拟模式 —— 全程隐藏分数，结束统一看报告（像真实面试）
    # realtime_feedback 由 feedback_mode 派生，保留是为了不破坏既有 SSE 逻辑
    "feedback_mode": "simulation",
    "realtime_feedback": False,
    "voice_enabled": False,
    # text 纯文字 / video 摄像头 + 麦克风
    "mode": "text",
    # panel = 每个环节换一位面试官；single = 整场同一位
    "interviewer_mode": "panel",
    "interviewer_type": "technical",
    # 允许考生点「提示」，但会被记录（诚实机制）
    "allow_hint": True,
    # 允许跳过实在答不出的问题，记为 0 分但不中断面试
    "allow_skip": True,
    # 是否要求开启摄像头（关闭后只录音，适合没有摄像头或不想露脸的场景）
    "require_camera": True,
    # 内部记账：暂停累计秒数（不计入面试时长）
    "_paused_seconds": 0,
}

FEEDBACK_MODES: dict[str, str] = {
    "simulation": "模拟模式（全程不看分数）",
    "practice": "练习模式（每题即时评分）",
}

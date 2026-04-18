# -*- coding: utf-8 -*-
"""
多维表格配置常量
与文档《ZSXQ精选内容拉取工具·完整说明文档》保持同步
文档: https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh
"""

# ============================================================
# 多维表格信息（AI破局俱乐部·精选内容库）
# ============================================================
BITABLE_APP_TOKEN = "XpGMbvYwsaNvZMsBzZ3cN1DRnOc"
BITABLE_TABLE_ID = "tblt1Lm7ipCFuyXi"

# ============================================================
# 字段名常量（9字段结构）
# ============================================================
FIELD_FEISHU_LINK = "飞书链接"
FIELD_TOPIC_ID = "话题ID"
FIELD_TITLE = "标题"
FIELD_AUTHOR = "作者"
FIELD_PUBLISH_TIME = "发布时间"
FIELD_TAGS = "标签"
FIELD_TAG_DESC = "标签说明"
FIELD_TAG_FREQ = "标签频次"
FIELD_LINK = "链接"

# ============================================================
# MultiSelect 字段选项（抽象标签 + 具体功能标签）
# ============================================================
# 抽象标签（描述内容类别）
ABSTRACT_TAGS = {
    "写作": "AI辅助写作、文案创作",
    "提示词": "Prompt Engineering",
    "智能体": "Agent/智能体应用",
    "获客": "变现、商业化、赚钱",
    "自媒体": "内容创业、个人IP",
}

# 具体功能标签（描述具体应用场景，随内容新增）
SPECIFIC_TAGS = {
    "口语陪练": "AI英语口语练习",
    "AI伙伴": "Coze Agent World / AI Companion",
}

# ============================================================
# 标签提取关键词映射
# ============================================================
TAG_KEYWORD_MAP = {
    "写作": ["写作", "文案", "内容创作", "写文章", "claude code", "cursor"],
    "提示词": ["提示词", "prompt", "prompting", "prompt engineering"],
    "智能体": ["智能体", "agent", "智能代理", "agent world", "ai伙伴"],
    "获客": ["获客", "变现", "商业化", "赚钱", "收入", "创业"],
    "自媒体": ["自媒体", "内容创业", "个人ip", "ip打造"],
}

# ============================================================
# 时间戳计算
# ============================================================
from datetime import datetime, timezone, timedelta


def cst_now():
    """当前 CST 时间"""
    return datetime.now(timezone(timedelta(hours=8)))


def datetime_to_ms(dt: datetime) -> int:
    """
    将 datetime 转换为毫秒级 Unix 时间戳
    用于写入 Feishu Bitable DateTime 字段

    示例:
        dt = datetime(2026, 4, 9, 14, 38, 0, tzinfo=timezone(timedelta(hours=8)))
        ms = datetime_to_ms(dt)  # 1775716680000
    """
    return int(dt.timestamp() * 1000)


def str_to_ms(date_str: str) -> int:
    """
    将 'YYYY-MM-DD HH:mm' 格式字符串转换为毫秒级时间戳

    示例:
        ms = str_to_ms("2026-04-09 14:38")  # 1775716680000
    """
    cst = timezone(timedelta(hours=8))
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    dt = dt.replace(tzinfo=cst)
    return datetime_to_ms(dt)

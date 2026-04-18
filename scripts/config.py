# -*- coding: utf-8 -*-
"""
多维表格配置常量 + 抽象标签持久化

与文档《ZSXQ精选内容拉取工具·完整说明文档》保持同步
文档: https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh

抽象标签采用 JSON 文件持久化，支持动态追加
"""

import json
import os

# ============================================================
# 文件路径
# ============================================================
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_TAGS_DIR = os.path.join(os.path.dirname(_SKILL_DIR), "data")
ABSTRACT_TAGS_FILE = os.path.join(_TAGS_DIR, "abstract_tags.json")

# 确保 data 目录存在
os.makedirs(_TAGS_DIR, exist_ok=True)

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
# 抽象标签（内容类别）
# 初始值，最终以 JSON 文件为准
# ============================================================
_INITIAL_ABSTRACT_TAGS = {
    "写作": "AI辅助写作、文案创作",
    "提示词": "Prompt Engineering",
    "智能体": "Agent/智能体应用",
    "获客": "变现、商业化、赚钱",
    "自媒体": "内容创业、个人IP",
}

# ============================================================
# 具体功能标签（描述具体应用场景，随内容新增）
# ============================================================
SPECIFIC_TAGS = {
    "口语陪练": "AI英语口语练习",
    "AI伙伴": "Coze Agent World / AI Companion",
}

# ============================================================
# 抽象标签关键词映射
# ============================================================
TAG_KEYWORD_MAP = {
    "写作": ["写作", "文案", "内容创作", "写文章", "claude code", "cursor"],
    "提示词": ["提示词", "prompt", "prompting", "prompt engineering"],
    "智能体": ["智能体", "agent", "智能代理", "agent world", "ai伙伴"],
    "获客": ["获客", "变现", "商业化", "赚钱", "收入", "创业"],
    "自媒体": ["自媒体", "内容创业", "个人ip", "ip打造"],
}

# ============================================================
# 抽象标签持久化（JSON 文件）
# ============================================================

def load_abstract_tags() -> dict:
    """
    从 JSON 文件加载抽象标签

    文件不存在时返回初始值，并写入文件
    """
    if os.path.exists(ABSTRACT_TAGS_FILE):
        try:
            with open(ABSTRACT_TAGS_FILE, "r", encoding="utf-8") as f:
                tags = json.load(f)
            return dict(tags)
        except (json.JSONDecodeError, IOError):
            pass

    # 文件不存在或读取失败，写入初始值
    save_abstract_tags(_INITIAL_ABSTRACT_TAGS)
    return dict(_INITIAL_ABSTRACT_TAGS)


def save_abstract_tags(tags: dict) -> None:
    """
    将抽象标签写入 JSON 文件
    """
    with open(ABSTRACT_TAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)


def add_abstract_tag(name: str, desc: str = "") -> None:
    """
    动态追加新的抽象标签

    参数:
        name: 标签名
        desc: 标签描述（自动从关键词推断）
    """
    tags = load_abstract_tags()
    if name not in tags:
        tags[name] = desc or "内容主题标签"
        save_abstract_tags(tags)
        print(f"✅ 新增抽象标签: {name} → {tags[name]}")


def list_abstract_tags() -> list:
    """列出所有抽象标签"""
    tags = load_abstract_tags()
    return sorted(tags.keys())


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

# -*- coding: utf-8 -*-
"""
配置常量
"""

from datetime import datetime, timezone, timedelta


# ============================================================
# 多维表格（AI破局俱乐部·精选内容库）
# ============================================================
BITABLE_APP_TOKEN = "XpGMbvYwsaNvZMsBzZ3cN1DRnOc"
BITABLE_TABLE_ID = "tblt1Lm7ipCFuyXi"

# ============================================================
# 字段名常量（与多维表格列名一致）
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
# 时间戳计算
# ============================================================

def str_to_ms(date_str: str) -> int:
    """
    将 'YYYY-MM-DD HH:mm' 转换为毫秒级时间戳（北京时间）
    """
    cst = timezone(timedelta(hours=8))
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    dt = dt.replace(tzinfo=cst)
    return int(dt.timestamp() * 1000)

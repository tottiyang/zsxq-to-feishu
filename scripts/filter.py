"""
filter.py — 话题过滤器

功能：
1. extract_feishu_links()  — 从 talk.text HTML 中提取飞书链接
2. parse_time_ms()         — ISO时间字符串 → 毫秒时间戳
3. extract_topic_data()   — 从单条 topic 提取入库字段

入库条件（二选一）：
- 有飞书链接（<e type="web" href="feishu.cn...">）→ 入库
- 有 talk.article.article_url                               → 入库
- 两者都没有                                               → 跳过（不入库）

分享链接获取方式：
- 由 zsxq_api.fetch_share_urls_for_topics() 批量获取
- 返回结构：{topic_id: share_url}
- engine.py 中先拉 topics，再批量获取分享链接，再传给本模块
"""

import re, html, urllib.parse
from typing import Optional
from datetime import datetime

WEB_TAG_RE = re.compile(r'<e\s+type="web"\s+href="([^"]+)"', re.IGNORECASE)


def extract_feishu_links(text: str) -> list[str]:
    """从 talk.text HTML 中提取飞书链接（已解码）"""
    if not text:
        return []
    decoded = []
    for h in WEB_TAG_RE.findall(text):
        try:
            d = html.unescape(h)
            d = urllib.parse.unquote(d)
            decoded.append(d)
        except Exception:
            decoded.append(h)
    return [u for u in decoded if 'feishu.cn' in u or 'larksuite' in u]


def parse_time_str(iso_time: str) -> str:
    """ISO 时间字符串 → 'YYYY-MM-DD HH:MM' 格式"""
    if not iso_time:
        return ""
    dt = datetime.fromisoformat(iso_time.replace('+0800', '+08:00'))
    return dt.strftime("%Y-%m-%d %H:%M")


def extract_topic_data(topic: dict, share_map: dict = None) -> Optional[dict]:
    """
    从单条 topic 提取入库数据

    Args:
        topic: ZSXQ Topics API 返回的单条记录
        share_map: {topic_id: share_url}，由 zsxq_api.fetch_share_urls_for_topics() 生成

    Returns:
        dict: 入库字段 | None: 无外链，跳过

    标题逻辑（needs_title_from_feishu 标记）:
        有飞书链接 → title=zsxq原始标题（待 engine.py 调用飞书API后替换）
        无飞书链接 → title=zsxq原始标题（直接入库）
    """
    topic_type = topic.get("type", "talk")

    if topic_type == "talk":
        talk = topic.get("talk") or {}
        text = talk.get("text", "") or ""
        article = talk.get("article")
        author = (talk.get("owner") or {}).get("name", "") or ""
    elif topic_type == "question":
        question = topic.get("question") or {}
        text = question.get("text", "") or ""
        article = None
        author = (question.get("owner") or {}).get("name", "") or ""
    else:
        return None

    # 提取飞书链接
    feishu_url = ""
    web_links = extract_feishu_links(text)
    if web_links:
        feishu_url = web_links[0]

    # 提取付费文章链接
    article_url = ""
    if article and isinstance(article, dict):
        article_url = article.get("article_url", "") or ""

    # 入库条件判断
    if not feishu_url and not article_url:
        return None

    # 净化标题
    clean_title = re.sub(r'<[^>]+>', '', topic.get("title") or "").strip()[:200]

    # 获取分享链接
    tid = str(topic["topic_id"])
    share_url = ""
    if share_map:
        share_url = share_map.get(tid, "")

    return {
        "feishu_url": feishu_url,
        "article_url": article_url,
        "topic_id": tid,
        "title": clean_title,
        "author": author,
        "create_time": topic.get("create_time", "") or "",
        "create_time_str": parse_time_str(topic.get("create_time", "")),
        "share_url": share_url,
        "is_digest": "是" if topic.get("digested") else "否",
        "needs_title_from_feishu": bool(feishu_url),   # 有飞书链接 → 标题取自文档
        "needs_tags": bool(feishu_url),
    }

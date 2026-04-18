# -*- coding: utf-8 -*-
"""
标签提取器

说明：Agent 本身就是 LLM，标签提取在对话中直接完成，
此脚本只返回 LLM 提示词和格式化结果。
"""

import json
import textwrap


# ============================================================
# LLM 提取提示词
# ============================================================

LLM_TAG_PROMPT_TEMPLATE = textwrap.dedent("""\
    从以下文档内容中提取 2-4 个最合适的标签。

    ## 文档标题
    {title}

    ## 文档正文（摘要，已截取前4000字）
    {content}

    ## 参考标签（可直接使用，优先选这些）
    写作、提示词、智能体、获客、自媒体、AI研究、编程开发、效率工具、学习教育

    ## 要求
    - 每个标签 2-5 个汉字
    - 标签要概括内容的本质主题，选最具代表性的，不要堆砌
    - 参考标签没有的可以自拟

    ## 输出格式（只需 JSON）
    {{"tags": ["标签1", "标签2", ...], "reason": "简短说明"}}
""")


# ============================================================
# 构建 LLM 提示词
# ============================================================

def build_llm_prompt(content: str, title: str = "") -> str:
    """
    构建标签提取的 LLM 提示词

    参数:
        content: 飞书文档正文（截取前4000字）
        title: 文档标题

    返回:
        LLM 提示词字符串
    """
    snippet = content[:4000]
    return LLM_TAG_PROMPT_TEMPLATE.format(title=title or "(无标题)", content=snippet)


# ============================================================
# 解析 LLM 输出
# ============================================================

def parse_llm_response(raw: str, content: str = "") -> dict:
    """
    解析 LLM 返回的标签 JSON，并统计标签词在正文中的出现频次

    参数:
        raw: LLM 原始输出
        content: 文档正文（用于频次统计）

    返回:
        {"tags": [...], "tag_desc": "...", "tag_freq": "..."}
    """
    raw = raw.strip()

    # 解析 JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError:
                data = {"tags": [], "reason": "解析失败"}
        else:
            data = {"tags": [], "reason": "无JSON"}

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [t for t in tags if isinstance(t, str) and 2 <= len(t) <= 8][:4]

    reason = data.get("reason", "")
    tag_desc = (reason + " | " + " / ".join(tags)).strip("| ").strip()
    if not tag_desc:
        tag_desc = " / ".join(tags)

    # 统计标签词在正文中的出现频次
    tag_freq = _build_tag_freq(tags, content)

    return {
        "tags": tags,
        "tag_desc": tag_desc,
        "tag_freq": tag_freq,
    }


def _build_tag_freq(tags: list, content: str) -> str:
    """
    简单关键词频次统计

    对每个标签，统计其在正文中出现的次数（不区分大小写，整词匹配）
    返回格式：标签1:3次、标签2:1次
    """
    if not tags or not content:
        return ""

    # 扩展关键词（同义词/子词，增加匹配覆盖面）
    KEYWORD_EXPANSION = {
        "写作": ["写作", "文章", "文案", "创作", "写文章", "写作指南"],
        "智能体": ["智能体", "agent", "agentic", "agent world", "ai伙伴"],
        "效率工具": ["效率", "提效", "工具", "工作流", "自动化", "workflow"],
        "编程开发": ["编程", "代码", "python", "cursor", "claude code", "github", "api"],
        "AI研究": ["ai", "大模型", "模型", "llm", "deepseek", "论文", "benchmark", "训练", "gpt", "chatgpt", "gemini", "claude"],
        "学习教育": ["学习", "教程", "课程", "入门", "指南", "教学", "教育", "练习"],
        "获客": ["变现", "赚钱", "创业", "商业", "收入", "获客", "变现"],
        "自媒体": ["自媒体", "ip", "个人ip", "内容创业", "公众号", "视频号", "小红书"],
        "提示词": ["提示词", "prompt", "prompting", "prompt engineering"],
    }

    freq_map = {}
    text_lower = content.lower()

    for tag in tags:
        keywords = KEYWORD_EXPANSION.get(tag, [tag])
        total = 0
        for kw in keywords:
            total += text_lower.count(kw.lower())
        if total > 0:
            freq_map[tag] = total

    if not freq_map:
        return ""

    sorted_freq = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)[:5]
    return "、".join([f"{t}{c}次" for t, c in sorted_freq])


# ============================================================
# 格式化（供 engine.py 调用）
# ============================================================

def extract_tags(content: str, title: str = "") -> dict:
    """
    返回 LLM 提示词（标签提取由 Agent 直接完成）

    返回:
        {
            "llm_prompt": "...",   # LLM 提示词，供 Agent 使用
            "tags": [],            # 占位（Agent 填入）
            "tag_desc": "",        # 占位
            "tag_freq": "",
            "llm_needed": True,    # 标记需要 Agent 填充
        }
    """
    return {
        "llm_prompt": build_llm_prompt(content, title),
        "tags": [],
        "tag_desc": "",
        "tag_freq": "",
        "llm_needed": True,
    }


def format_record_tags(tags: list, tag_desc: str, tag_freq: str) -> dict:
    """格式化为多维表格字段"""
    return {
        "标签": tags,
        "标签说明": tag_desc,
        "标签频次": tag_freq,
    }

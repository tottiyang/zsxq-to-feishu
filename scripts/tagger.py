# -*- coding: utf-8 -*-
"""
智能标签提取器（混合方案 v2）
从飞书文档正文中智能分析内容标签

算法：
1. 全文词频统计（jieba 分词）
2. 先用已知抽象标签规则匹配（从 JSON 文件加载）
3. 匹配不上 → 标记需要 LLM，由 Agent 调用大模型生成新标签 → 固化到 JSON
4. 具体功能标签始终由规则动态生成
5. 生成标签说明和频次文本

与文档《ZSXQ精选内容拉取工具·完整说明文档》保持同步
文档: https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh
"""

import json
import os
import re
from collections import Counter

import jieba

from config import (
    ABSTRACT_TAGS_FILE,
    load_abstract_tags,
    save_abstract_tags,
    TAG_KEYWORD_MAP,
    SPECIFIC_TAGS,
    FIELD_TAGS,
    FIELD_TAG_DESC,
    FIELD_TAG_FREQ,
)

# ============================================================
# 快速判断规则（不依赖 LLM，作为 fallback）
# 当规则匹配不上抽象标签时使用
# ============================================================
QUICK_TAG_RULES = [
    {
        "tag": "编程开发",
        "keywords": ["代码", "编程", "python", "cursor", "claude code", "函数",
                     "接口", "api", "github", "调试", "算法", "开发", "coding"],
    },
    {
        "tag": "效率工具",
        "keywords": ["notion", "obsidian", "笔记", "工作流", "自动化",
                     "效率", "模板", "流程", "airtable", "工具"],
    },
    {
        "tag": "AI研究",
        "keywords": ["论文", "模型", "研究", "benchmark", "训练",
                     "deepseek", "llm", "开源模型", "学术"],
    },
    {
        "tag": "学习教育",
        "keywords": ["教程", "学习", "课程", "入门", "指南", "教学", "练习", "课堂"],
    },
    {
        "tag": "生活应用",
        "keywords": ["美食", "健身", "旅行", "家居", "日常", "生活"],
    },
]


# ============================================================
# 核心提取函数
# ============================================================

def extract_tags(content: str, title: str = "") -> dict:
    """
    从文档内容中智能提取标签（混合方案 v2）

    参数:
        content: 飞书文档正文（纯文本）
        title: 文档标题

    返回:
        {
            "tags": [...],              # 完整标签列表
            "abstract_tags": [...],       # 抽象标签
            "specific_tags": [...],       # 具体功能标签
            "tag_desc": "...",
            "tag_freq": "...",
            "top_words": [...],          # 高频词
            "llm_needed": False,         # 是否需要 LLM 生成新抽象标签
            "llm_context": {...},         # LLM 调用所需上下文（供 Agent 使用）
        }
    """
    # ── 1. 全文分词 + 词频统计 ───────────────────────
    words = [
        w for w in jieba.cut(content)
        if len(w) >= 2 and not w.isdigit() and not re.match(r'^[\W_]+$', w)
    ]
    word_freq = Counter(words)
    top_words = word_freq.most_common(20)
    top_words_dict = dict(top_words)

    # ── 2. 加载最新抽象标签（从 JSON 文件）─────────────
    abstract_tags_map = load_abstract_tags()
    keyword_map = dict(TAG_KEYWORD_MAP)

    # 动态更新关键词映射（包含之前固化的新标签）
    for tag_name in abstract_tags_map:
        if tag_name not in keyword_map:
            keyword_map[tag_name] = [tag_name]

    # ── 3. 规则匹配抽象标签 ───────────────────────────
    matched_abstract = []
    for tag_name, keywords in keyword_map.items():
        if any(kw.lower() in content.lower() for kw in keywords):
            matched_abstract.append(tag_name)
    matched_abstract = list(dict.fromkeys(matched_abstract))  # 去重保序

    # ── 4. 规则匹配不上 → 快速判断（fallback1） → LLM（fallback2） ──
    llm_needed = False
    llm_context = None

    if not matched_abstract:
        # 尝试快速判断（基于规则，不依赖 LLM）
        quick_tags = _quick_match(title, content, top_words_dict)
        if quick_tags:
            matched_abstract = quick_tags
        else:
            # 需要 LLM，生成调用上下文
            llm_needed = True
            known_tags = list(abstract_tags_map.keys())
            llm_context = {
                "title": title,
                "content_snippet": content[:2000],
                "top_words": [(w, c) for w, c in top_words[:15]],
                "known_tags": known_tags,
                "known_keywords": keyword_map,
                "instruction": _build_llm_instruction(title, top_words[:15], known_tags),
            }

    # ── 5. 判断具体功能标签（始终由规则动态生成）──────
    specific_tags = _detect_specific_tags(title, content, word_freq)

    # ── 6. 构建最终标签列表 ──────────────────────────
    all_tags = matched_abstract + specific_tags

    # ── 7. 生成标签说明和频次 ────────────────────────
    tag_desc = _build_tag_desc(matched_abstract, specific_tags, top_words_dict, keyword_map)
    tag_freq = _build_tag_freq(matched_abstract, specific_tags, content, keyword_map)

    return {
        "tags": all_tags,
        "abstract_tags": matched_abstract,
        "specific_tags": specific_tags,
        "tag_desc": tag_desc,
        "tag_freq": tag_freq,
        "top_words": top_words,
        "llm_needed": llm_needed,
        "llm_context": llm_context,
    }


def _quick_match(title: str, content: str, top_words_dict: dict) -> list:
    """
    快速判断抽象标签（规则匹配，不依赖 LLM）
    """
    text = (title + " " + content).lower()
    matched = []

    for rule in QUICK_TAG_RULES:
        if any(kw.lower() in text for kw in rule["keywords"]):
            matched.append(rule["tag"])

    return list(dict.fromkeys(matched))  # 去重保序


def _build_llm_instruction(title: str, top_words: list, known_tags: list) -> str:
    """
    生成 LLM 调用指令（供 Agent 使用）
    """
    top_words_str = ", ".join([f"{w}({c}次)" for w, c in top_words])
    known_str = ", ".join(known_tags) if known_tags else "无"

    return f"""请为以下内容生成 1-2 个最合适的抽象标签。

## 文档标题
{title}

## 高频词
{top_words_str}

## 已有抽象标签（不要重复）
{known_str}

## 要求
- 2-4 个汉字，简洁有力
- 能概括内容的本质主题
- 参考已有标签风格

## 输出格式
只输出标签名，逗号分隔，不要解释。
例如：编程开发, 效率工具"""


# ============================================================
# 具体功能标签识别（动态规则）
# ============================================================

def _detect_specific_tags(title: str, content: str, word_freq: Counter) -> list:
    """
    从内容中识别具体功能标签（具体应用场景）
    随内容动态新增，不穷举所有标签
    """
    text = (title + " " + content).lower()
    specific = []

    # 口语陪练
    if "口语" in text and ("陪练" in text or "英语" in text):
        specific.append("口语陪练")

    # AI伙伴 / Agent World
    if any(kw in text for kw in ["ai伙伴", "agent world", "ai companion"]):
        specific.append("AI伙伴")

    # PPT / 演示文稿
    if any(kw in text for kw in ["ppt", "演示", "幻灯片", "slides", "slide"]):
        specific.append("PPT制作")

    # Claude Code
    if "claude code" in text or "claude-code" in text:
        specific.append("Claude Code")

    # Cursor 编程
    if "cursor" in text:
        specific.append("Cursor编程")

    # Coze / 扣子
    if any(kw in text for kw in ["coze", "扣子"]):
        if "agent world" in text or "ai伙伴" in text:
            specific.append("AI伙伴")
        if "智能体" not in text and "agent" not in text:
            specific.append("Coze智能体")

    # DeepSeek
    if "deepseek" in text:
        specific.append("DeepSeek")

    # 小红书
    if "小红书" in text:
        specific.append("小红书运营")

    # 视频创作
    if any(kw in text for kw in ["视频", "剪辑", "youtube", "b站", "bilibili"]):
        specific.append("视频创作")

    # 千人大会
    if "千人大会" in text:
        specific.append("千人大会")

    # 去重保序
    return list(dict.fromkeys(specific))


# ============================================================
# 标签说明和频次生成
# ============================================================

def _build_tag_desc(abstract_tags: list, specific_tags: list,
                    top_words_dict: dict, keyword_map: dict) -> str:
    """生成标签说明文本"""
    parts = []
    abstract_map = load_abstract_tags()

    for tag in abstract_tags:
        desc = abstract_map.get(tag, "")
        # 找相关高频词
        related_kws = keyword_map.get(tag, [])
        related = [(w, c) for w, c in top_words_dict.items() if w in related_kws]
        if related:
            w, c = related[0]
            parts.append(f"{tag}：{desc}，{w}出现{c}次")
        else:
            parts.append(f"{tag}：{desc}")

    for tag in specific_tags:
        desc = SPECIFIC_TAGS.get(tag, "具体应用场景")
        parts.append(f"{tag}：{desc}")

    return " | ".join(parts) if parts else ""


def _build_tag_freq(abstract_tags: list, specific_tags: list,
                    content: str, keyword_map: dict) -> str:
    """生成标签频次文本"""
    freq_map = {}

    for tag in abstract_tags:
        for kw in keyword_map.get(tag, [tag]):
            count = content.lower().count(kw.lower())
            if count > 0:
                freq_map[kw] = count

    for tag in specific_tags:
        for w in SPECIFIC_TAGS.get(tag, ""):
            count = content.count(w)
            if count > 0:
                freq_map[w] = count

    sorted_freq = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)[:5]
    return "、".join([f"{w}{c}次" for w, c in sorted_freq]) if sorted_freq else ""


# ============================================================
# Agent 调用接口（固化新标签）
# ============================================================

def persist_new_abstract_tags(new_tags: list, descriptions: dict = None) -> dict:
    """
    将 LLM 生成的新抽象标签固化到 JSON 文件

    参数:
        new_tags: 新标签名列表，如 ["编程开发", "AI研究"]
        descriptions: 标签描述字典，如 {"编程开发": "Python/编程技能", "AI研究": "大模型研究"}

    返回:
        {"saved": ["编程开发", "AI研究"], "all_tags": [...]}
    """
    if not new_tags:
        return {"saved": [], "all_tags": list_abstract_tags()}

    tags = load_abstract_tags()
    descriptions = descriptions or {}
    saved = []

    for tag in new_tags:
        tag = tag.strip()
        if not tag or tag in tags:
            continue
        # 标签名本身作为关键词
        tags[tag] = descriptions.get(tag, f"内容主题标签")
        saved.append(tag)

    if saved:
        save_abstract_tags(tags)
        print(f"✅ 已固化新抽象标签: {saved}")

    return {"saved": saved, "all_tags": sorted(tags.keys())}


def list_abstract_tags() -> list:
    """列出所有抽象标签"""
    return sorted(load_abstract_tags().keys())


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python3 tagger.py <正文内容> [标题]")
        sys.exit(1)

    content = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""

    result = extract_tags(content, title)

    print("=" * 40)
    print(f"✅ 抽象标签: {result['abstract_tags']}")
    print(f"✅ 具体功能标签: {result['specific_tags']}")
    print(f"✅ 完整标签: {result['tags']}")
    print(f"✅ 标签说明: {result['tag_desc']}")
    print(f"✅ 标签频次: {result['tag_freq']}")
    print(f"✅ 高频词 Top10: {[(w, c) for w, c in result['top_words'][:10]]}")
    print(f"✅ 需要LLM: {result['llm_needed']}")

    if result['llm_needed']:
        print()
        print("⚠️  抽象标签未能匹配，需要 LLM 生成")
        ctx = result['llm_context']
        print(f"   标题: {ctx['title']}")
        print(f"   高频词: {ctx['top_words']}")
        print(f"   已有标签: {ctx['known_tags']}")
        print()
        print("   请 Agent 调用 LLM（参考 instruction）生成新标签后，")
        print("   调用 persist_new_abstract_tags([新标签]) 固化到 JSON")
        print()
        print("   完整 LLM 指令:")
        print("   " + ctx['instruction'])

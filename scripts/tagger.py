# -*- coding: utf-8 -*-
"""
智能标签提取器
从飞书文档正文中智能分析内容标签

算法：
1. 全文词频统计（中文分词 jieba）
2. 标题关键词优先判断
3. 抽象标签（内容类别）+ 具体功能标签（具体应用场景）
4. 生成标签说明和频次文本

与文档《ZSXQ精选内容拉取工具·完整说明文档》保持同步
文档: https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh
"""

import jieba
from collections import Counter
from config import TAG_KEYWORD_MAP, ABSTRACT_TAGS, SPECIFIC_TAGS, FIELD_TAG_DESC, FIELD_TAG_FREQ


def extract_tags(content: str, title: str = "") -> dict:
    """
    从文档内容中智能提取标签

    参数:
        content: 飞书文档正文（纯文本）
        title: 文档标题（用于关键词优先匹配）

    返回:
        {
            "tags": ["智能体", "AI伙伴"],           # 标签列表
            "abstract_tags": ["智能体"],             # 抽象标签
            "specific_tags": ["AI伙伴"],            # 具体功能标签
            "tag_desc": "智能体：... | AI伙伴：...",  # 标签说明
            "tag_freq": "伙伴37次、Agent15次...",    # 标签频次
            "top_words": [("写作", 37), ...]         # Top20 高频词
        }
    """
    # ── 1. 全文分词 + 词频统计 ──────────────────────────
    # jieba 精确模式，只保留 >= 2 个字符的词
    words = [w for w in jieba.cut(content) if len(w) >= 2 and not w.isdigit()]
    word_freq = Counter(words)
    top_words = word_freq.most_common(20)

    # ── 2. 判断抽象标签（内容类别）─────────────────────
    abstract_tags = []
    for tag_name, keywords in TAG_KEYWORD_MAP.items():
        if any(kw.lower() in content.lower() for kw in keywords):
            abstract_tags.append(tag_name)

    # 去重，保持顺序
    abstract_tags = list(dict.fromkeys(abstract_tags))

    # ── 3. 判断具体功能标签（具体应用场景）──────────────
    specific_tags = _detect_specific_tags(content, title, word_freq)

    # ── 4. 构建最终标签列表 ───────────────────────────
    # 顺序：抽象标签 → 具体功能标签
    all_tags = abstract_tags + specific_tags

    # ── 5. 生成标签说明 ───────────────────────────────
    tag_desc = _build_tag_desc(abstract_tags, specific_tags, top_words)

    # ── 6. 生成标签频次文本 ───────────────────────────
    tag_freq = _build_tag_freq(abstract_tags, specific_tags, content)

    return {
        "tags": all_tags,
        "abstract_tags": abstract_tags,
        "specific_tags": specific_tags,
        "tag_desc": tag_desc,
        "tag_freq": tag_freq,
        "top_words": top_words,
    }


def _detect_specific_tags(content: str, title: str, word_freq: Counter) -> list:
    """
    从内容中识别具体功能标签（具体应用场景）
    随内容类型新增，不预先定义所有标签
    """
    specific = []
    text = title + content

    # ── 口语陪练 ───────────────────────────────────
    if "口语" in text and (
        "陪练" in text or "英语" in text or "口语练习" in text
    ):
        specific.append("口语陪练")

    # ── AI伙伴 / Agent World ─────────────────────────
    if any(kw in text for kw in ["AI伙伴", "Agent World", "AI Companion"]):
        specific.append("AI伙伴")

    # ── PPT / 演示文稿 ──────────────────────────────
    if "PPT" in text or "演示" in text or "幻灯片" in text:
        specific.append("PPT制作")

    # ── Claude Code 写作 ─────────────────────────────
    if "claude code" in text.lower() or "claude-code" in text.lower():
        specific.append("Claude Code")

    # ── Cursor 编程 ────────────────────────────────
    if "cursor" in text.lower():
        specific.append("Cursor编程")

    # ── 千人大会 ──────────────────────────────────
    if "千人大会" in text:
        specific.append("千人大会")

    # ── Coze / 扣子 ────────────────────────────────
    if any(kw in text for kw in ["扣子", "coze", "Coze"]):
        if "Agent World" in text:
            specific.append("AI伙伴")  # 确保添加
        if "智能体" not in text:
            specific.append("Coze智能体")

    # ── 去重 ──────────────────────────────────────
    return list(dict.fromkeys(specific))


def _build_tag_desc(abstract_tags: list, specific_tags: list, top_words: list) -> str:
    """
    生成标签说明文本

    格式: "{标签1}：{一句话说明}，{频次最高} | {标签2}：..."
    """
    parts = []

    # 抽象标签说明
    for tag in abstract_tags:
        desc = ABSTRACT_TAGS.get(tag, "")
        # 从高频词中找该标签相关的词
        related = [(w, c) for w, c in top_words if w in str(TAG_KEYWORD_MAP.get(tag, []))]
        if related:
            top_word, top_count = related[0]
            parts.append(f"{tag}：{desc}，频次{top_count}次")
        else:
            parts.append(f"{tag}：{desc}")

    # 具体功能标签说明
    for tag in specific_tags:
        desc = SPECIFIC_TAGS.get(tag, "具体应用场景")
        related = [(w, c) for w, c in top_words if w in desc]
        if related:
            top_word, top_count = related[0]
            parts.append(f"{tag}：{desc}，频次{top_count}次")
        else:
            parts.append(f"{tag}：{desc}")

    return " | ".join(parts)


def _build_tag_freq(abstract_tags: list, specific_tags: list, content: str) -> str:
    """
    生成标签频次文本（关键词在正文的实际出现次数）

    格式: "{词1}{count1}次、{词2}{count2}次、{词3}{count3}次"
    """
    freq_map = {}

    # 抽象标签相关关键词
    for tag in abstract_tags:
        keywords = TAG_KEYWORD_MAP.get(tag, [])
        for kw in keywords:
            count = content.lower().count(kw.lower())
            if count > 0:
                freq_map[kw] = count

    # 具体功能标签相关关键词
    for tag in specific_tags:
        desc = SPECIFIC_TAGS.get(tag, "")
        for w in desc:
            count = content.count(w)
            if count > 0:
                freq_map[w] = count

    # 取 Top 3
    sorted_freq = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)[:5]
    return "、".join([f"{w}{c}次" for w, c in sorted_freq])


def format_record_tags(tags: list, tag_desc: str, tag_freq: str) -> dict:
    """
    将标签信息格式化为多维表格字段格式

    返回:
        {
            FIELD_TAGS: ["智能体", "AI伙伴"],
            FIELD_TAG_DESC: "...",
            FIELD_TAG_FREQ: "..."
        }
    """
    from config import FIELD_TAGS, FIELD_TAG_DESC, FIELD_TAG_FREQ

    return {
        FIELD_TAGS: tags,
        FIELD_TAG_DESC: tag_desc,
        FIELD_TAG_FREQ: tag_freq,
    }


if __name__ == "__main__":
    # 测试
    test_content = """
    扣子 2.5 实测：从对话框到 AI 伙伴，Agent World 来了

    今天来聊聊 Coze 平台的最新更新——扣子 2.5 版本，
    最大的亮点是引入了 Agent World 功能，让 AI 从单纯的对话工具，
    进化为真正的 AI 伙伴。

    在 Agent World 中，用户可以创建自己的 AI 伙伴，
    这些伙伴具有记忆能力，可以记住用户的偏好和习惯。

    经过测试，AI伙伴的反应速度非常快，伙伴 37 次提到，
    Agent 相关功能出现了 15 次，扣子平台本身出现了 12 次。
    """

    result = extract_tags(test_content, "扣子 2.5 实测：从对话框到 AI 伙伴，Agent World 来了")
    print("提取结果:")
    print(f"  标签: {result['tags']}")
    print(f"  抽象标签: {result['abstract_tags']}")
    print(f"  具体功能标签: {result['specific_tags']}")
    print(f"  标签说明: {result['tag_desc']}")
    print(f"  标签频次: {result['tag_freq']}")
    print(f"  Top10词频: {result['top_words'][:10]}")

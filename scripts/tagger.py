"""
tagger.py — 标签提取 + 标题生成
执行方式：由 Agent 自身大模型（非外部API）分析内容生成标签/标题
固化提示词：见下方 SYSTEM_PROMPT
"""
import json, re

# ─────────── 标签提取 ───────────

SYSTEM_PROMPT_TAGS = """你是一个内容分类专家。根据给定的飞书文档内容，提取标签。

【输出格式】
严格按以下JSON格式输出，不要输出任何其他文字：
{
  "abstract_tags": ["抽象标签1"],
  "functional_tags": ["功能标签1", "功能标签2"],
  "tag_explanations": {"标签名": "为什么打这个标签（5~20字）"}
}

【标签生成规则】
1. abstract_tags：基于内容宏观主题生成1~2个合适的标签，不限于任何候选池
2. functional_tags：基于具体提到的工具/平台/方法生成2~4个合适的标签，不限于任何候选池
3. tag_explanations：所有标签都必须有解释
4. 内容无关或质量低时：{"abstract_tags": [], "functional_tags": [], "tag_explanations": {}}
5. 只根据正文内容判断，不要凭空想象
6. 解释要具体指出文档中提到的内容
"""

USER_PROMPT_TAGS_TEMPLATE = """【文档信息】
标题：{title}

正文内容：
{content}

请直接输出JSON，不要其他文字。"""

# ─────────── 标题生成 ───────────

SYSTEM_PROMPT_TITLE = """你是一个内容策划专家。根据给定的正文内容，生成一个简洁有力的标题。

【输出格式】
严格按以下JSON格式输出，不要输出任何其他文字：
{"title": "标题文字"}

【标题生成规则】
1. 标题长度：8~30个字符
2. 标题要反映正文核心主题或亮点，吸引读者点击
3. 不要照搬原文，要提炼精华，可以包含数字、方法论、个人故事亮点
4. 不要加书名号《》、双引号等装饰符号
5. 内容无关或质量极低时：{"title": ""}
"""

USER_PROMPT_TITLE_TEMPLATE = """【正文内容】
{content}

请直接输出JSON，不要其他文字。"""

# ─────────── 通用工具函数 ───────────

def _clean_doc_content(raw: str, max_len: int = 3000) -> str:
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

# ─────────── 标签提取 API ───────────

def build_tag_prompt(title: str, content: str) -> tuple[str, str]:
    clean = _clean_doc_content(content)
    user_prompt = USER_PROMPT_TAGS_TEMPLATE.format(title=title, content=clean)
    return SYSTEM_PROMPT_TAGS, user_prompt

def tags_to_row(tags_result: dict) -> tuple[str, str]:
    abstract = tags_result.get("abstract_tags", [])
    functional = tags_result.get("functional_tags", [])
    explanations = tags_result.get("tag_explanations", {})
    all_tags = abstract + functional
    tags_str = ",".join(all_tags) if all_tags else ""
    notes_str = json.dumps(explanations, ensure_ascii=False)
    return tags_str, notes_str

# ─────────── 标题生成 API ───────────

def build_title_prompt(clean_text: str) -> tuple[str, str]:
    """为正文内容构建标题生成提示词"""
    user_prompt = USER_PROMPT_TITLE_TEMPLATE.format(content=clean_text)
    return SYSTEM_PROMPT_TITLE, user_prompt

def parse_title_result(raw) -> str:
    """从 Agent 返回中解析标题（支持 str 或 dict）"""
    try:
        if isinstance(raw, dict):
            result = raw
        else:
            result = json.loads(raw)
        title = result.get("title", "").strip()
        return title[:50] if title else ""
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ""

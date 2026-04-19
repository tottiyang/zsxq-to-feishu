"""
tagger.py — 标签提取
执行方式：由 Agent 自身大模型（非外部API）分析飞书文档内容生成标签
固化提示词：见下方 SYSTEM_PROMPT
"""
import json, re

SYSTEM_PROMPT = """你是一个内容分类专家。根据给定的飞书文档内容，提取标签。

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

USER_PROMPT_TEMPLATE = """【文档信息】
标题：{title}

正文内容：
{content}

请直接输出JSON，不要其他文字。"""

def _clean_doc_content(raw: str, max_len: int = 3000) -> str:
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]

def build_tag_prompt(title: str, content: str) -> tuple[str, str]:
    clean = _clean_doc_content(content)
    user_prompt = USER_PROMPT_TEMPLATE.format(title=title, content=clean)
    return SYSTEM_PROMPT, user_prompt

def tags_to_row(tags_result: dict) -> tuple[str, str]:
    abstract = tags_result.get("abstract_tags", [])
    functional = tags_result.get("functional_tags", [])
    explanations = tags_result.get("tag_explanations", {})
    all_tags = abstract + functional
    tags_str = ",".join(all_tags) if all_tags else ""
    notes_str = json.dumps(explanations, ensure_ascii=False)
    return tags_str, notes_str

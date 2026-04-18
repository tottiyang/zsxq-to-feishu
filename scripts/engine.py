# -*- coding: utf-8 -*-
"""
ZSXQ 精选内容拉取引擎
ZSXQ 分享链接 → 结构化数据 → 写入飞书多维表格

完整流程:
  ① extract_zsxq_share() 提取 ZSXQ 元数据（飞书链接 + topic_id + 作者 + 时间）
  ② Agent 调用 feishu_doc 读取飞书文档正文
  ③ Agent 用 tagger.build_llm_prompt() 生成标签提取提示词，调用 LLM 提取标签
  ④ Agent 将标签填入 record_fields，调用 feishu_bitable_create_record 写入

使用方式:
  python3 engine.py "https://t.zsxq.com/6L4Ry"
"""

import sys
import json
import textwrap

from config import (
    BITABLE_APP_TOKEN,
    BITABLE_TABLE_ID,
    FIELD_FEISHU_LINK,
    FIELD_TOPIC_ID,
    FIELD_TITLE,
    FIELD_AUTHOR,
    FIELD_PUBLISH_TIME,
    FIELD_TAGS,
    FIELD_TAG_DESC,
    FIELD_TAG_FREQ,
    FIELD_LINK,
    str_to_ms,
)
from extractor import extract_zsxq_share, extract_feishu_token
from tagger import build_llm_prompt, parse_llm_response, format_record_tags


# ============================================================
# 阶段一：提取元数据
# ============================================================

def run(share_url: str) -> dict:
    """
    提取 ZSXQ 分享链接的元数据

    返回:
        success=True 时返回:
        {
          "success": True,
          "step": "meta_extracted",
          "feishu_token": "...",
          "feishu_link": "...",
          "title": "...",
          "author": "...",
          "date_str": "...",
          "zsxq_url": "...",
          "zsxq_topic_id": "...",
          "next_step": "read_feishu_doc",
          "instruction": "请调用 feishu_doc...",
        }
    """
    print(f"[步骤1] 提取 ZSXQ 元数据: {share_url}")
    meta = extract_zsxq_share(share_url)
    if not meta.get("success"):
        return {"success": False, "error": f"[步骤1失败] {meta.get('error')}"}

    feishu_link = meta.get("feishu_link", "")
    title = meta.get("title") or meta.get("zsxq_url", "未知标题")
    author = meta.get("author") or "未知作者"
    date_str = meta.get("date_str")
    zsxq_url = meta.get("zsxq_url") or share_url
    feishu_token = extract_feishu_token(feishu_link)
    zsxq_topic_id = meta.get("zsxq_topic_id") or feishu_token

    print(f"  ✅ 标题: {title}")
    print(f"  ✅ 作者: {author}")
    print(f"  ✅ 时间: {date_str}")
    print(f"  ✅ 飞书链接: {feishu_link}")

    return {
        "success": True,
        "step": "meta_extracted",
        "feishu_link": feishu_link,
        "feishu_token": feishu_token,
        "title": title,
        "author": author,
        "date_str": date_str,
        "zsxq_url": zsxq_url,
        "zsxq_topic_id": zsxq_topic_id,
        "next_step": "read_feishu_doc",
        "instruction": (
            f"请调用 feishu_doc(action='read', doc_token='{feishu_token}') "
            "获取文档正文。"
        ),
    }


# ============================================================
# 阶段二：提取标签（Agent 调用 LLM）
# ============================================================

def process_content(
    feishu_token: str,
    feishu_link: str,
    title: str,
    author: str,
    date_str: str,
    zsxq_url: str,
    zsxq_topic_id: str,
    feishu_content: str,
) -> dict:
    """
    构建多维表格记录字段

    流程：
    1. Agent 调用 feishu_doc 读取正文
    2. Agent 用下方 instruction 调用 LLM 提取标签
    3. Agent 填入 tags 后，调用 feishu_bitable_create_record 写入

    参数:
        feishu_content: feishu_doc 读取的文档正文（纯文本）

    返回:
        llm_needed=True 时返回 LLM 提示词，等 Agent 填入标签后完成
    """
    print(f"\n[步骤2] 构建 LLM 标签提取提示词")
    llm_prompt = build_llm_prompt(feishu_content, title)
    print(f"  ✅ 提示词已生成（内容前100字）：")
    print(f"     {feishu_content[:100].replace(chr(10), ' ')}...")

    # 时间戳
    publish_ms = str_to_ms(date_str) if date_str else None

    # 构建不含标签的字段（供 Agent 填入标签后使用）
    base_fields = {
        FIELD_FEISHU_LINK: {"link": feishu_link, "text": title},
        FIELD_TOPIC_ID: zsxq_topic_id,
        FIELD_TITLE: title,
        FIELD_AUTHOR: author,
        FIELD_LINK: zsxq_url,
    }
    if publish_ms:
        base_fields[FIELD_PUBLISH_TIME] = publish_ms

    return {
        "success": True,
        "step": "llm_tag_needed",
        "llm_prompt": llm_prompt,
        "base_fields": base_fields,
        "title": title,
        "feishu_link": feishu_link,
        "next_step": "call_llm_and_write",
        "instruction": textwrap.dedent(f"""\
            请用以下提示词调用 LLM 提取标签，然后写入多维表格。

            ## LLM 提示词
            {llm_prompt}

            ## 操作步骤
            1. 将提示词发给 LLM（当前 Agent 本身就是 LLM，直接用自己回答）
            2. 从 LLM 回复中解析出 tags 列表（JSON 格式）
            3. 用 `parse_llm_response(LLM回复, feishu_content)` 解析标签并自动计算频次
            4. 用下方 fields 创建多维表格记录：
               app_token={BITABLE_APP_TOKEN}
               table_id={BITABLE_TABLE_ID}
               fields={{
                 *base_fields（已填好）*,
                 "标签": <tags列表>,
                 "标签说明": <tag_desc>,
                 "标签频次": <tag_freq>   ← parse_llm_response 已自动计算
               }}
            5. 调用 feishu_bitable_create_record 完成写入
        """),
    }


# ============================================================
# 主入口
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python3 engine.py <ZSXQ分享链接>")
        sys.exit(1)
    result = run(sys.argv[1])
    print(f"\n结果: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()

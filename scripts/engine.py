# -*- coding: utf-8 -*-
"""
ZSXQ 精选内容拉取引擎
将 ZSXQ 分享链接 → 结构化数据 → 写入飞书多维表格

完整流程:
  ① Playwright 提取 ZSXQ 分享链接数据（飞书链接 + 元数据）
  ② feishu_doc 读取飞书文档正文
  ③ tagger 智能分析内容标签
  ④ feishu_bitable 创建/更新多维表格记录

与文档《ZSXQ精选内容拉取工具·完整说明文档》保持同步
文档: https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh

使用方式:
  python3 engine.py "https://t.zsxq.com/6L4Ry"
"""

import sys
import json

# 导入本地模块
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
from tagger import extract_tags, format_record_tags


def run(share_url: str) -> dict:
    """
    主流程：处理单个 ZSXQ 分享链接

    参数:
        share_url: ZSXQ 分享链接，如 https://t.zsxq.com/6L4Ry

    返回:
        {"success": True, "record_id": "...", "title": "...", "tags": [...]}
        或 {"success": False, "error": "..."}
    """
    # ── 步骤1：提取 ZSXQ 元数据 ────────────────────────
    print(f"[步骤1] 提取 ZSXQ 元数据: {share_url}")
    meta = extract_zsxq_share(share_url)
    if not meta.get("success"):
        return {"success": False, "error": f"[步骤1失败] {meta.get('error')}"}

    feishu_link = meta.get("feishu_link")
    title = meta.get("title") or meta.get("zsxq_url", "未知标题")
    author = meta.get("author") or "未知作者"
    date_str = meta.get("date_str")
    zsxq_url = meta.get("zsxq_url") or share_url

    if not feishu_link:
        return {"success": False, "error": "[步骤1失败] 未找到飞书文档链接"}

    feishu_token = extract_feishu_token(feishu_link)
    zsxq_topic_id = meta.get("zsxq_topic_id") or feishu_token

    print(f"  ✅ 标题: {title}")
    print(f"  ✅ 作者: {author}")
    print(f"  ✅ 时间: {date_str}")
    print(f"  ✅ 飞书链接: {feishu_link}")

    # ── 步骤2：读取飞书文档正文（需要 Agent 调用 feishu_doc）─────
    # 注意：这里只返回元数据，实际读取由 Agent 调用 feishu_doc 完成
    # Agent 需要先读取文档，再调用本引擎的 process_content 方法

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
            "获取文档正文，然后调用 process_content() 处理内容并写入多维表格"
        ),
    }


def process_content(
    feishu_token: str,
    feishu_link: str,
    title: str,
    author: str,
    date_str: str,
    zsxq_url: str,
    topic_id: str,
    feishu_content: str,
) -> dict:
    """
    步骤2-4：处理飞书文档内容，提取标签，写入多维表格

    参数:
        feishu_token: 飞书文档 token
        feishu_link: 飞书文档链接
        title: 话题标题
        author: 作者
        date_str: 发布时间 "YYYY-MM-DD HH:mm"
        zsxq_url: ZSXQ 分享链接
        topic_id: ZSXQ topic_id，约17位数字，如 45544844845444248
        feishu_content: 飞书文档正文（纯文本）

    返回:
        {"success": True, "record_id": "...", "title": "...", "tags": [...]}
    """
    # ── 步骤2：提取标签 ──────────────────────────────
    print(f"\n[步骤2] 提取内容标签")
    tag_result = extract_tags(feishu_content, title)
    print(f"  ✅ 标签: {tag_result['tags']}")
    print(f"  ✅ 标签说明: {tag_result['tag_desc']}")
    print(f"  ✅ 标签频次: {tag_result['tag_freq']}")

    # ── 步骤3：计算时间戳 ────────────────────────────
    print(f"\n[步骤3] 计算时间戳")
    if date_str:
        publish_ms = str_to_ms(date_str)
    else:
        publish_ms = None
    print(f"  ✅ 时间戳: {publish_ms}")

    # ── 步骤4：写入多维表格（Agent 调用 OpenClaw 工具）───────────
    # 这里只返回要写入的字段数据
    # 实际写入由 Agent 调用 feishu_bitable_create_record 完成

    record_fields = {
        FIELD_FEISHU_LINK: {
            "link": feishu_link,
            "text": title,
        },
        FIELD_TOPIC_ID: zsxq_topic_id,
        FIELD_TITLE: title,
        FIELD_AUTHOR: author,
        FIELD_LINK: zsxq_url,
    }

    if publish_ms:
        record_fields[FIELD_PUBLISH_TIME] = publish_ms

    tag_fields = format_record_tags(
        tag_result["tags"],
        tag_result["tag_desc"],
        tag_result["tag_freq"],
    )
    record_fields.update(tag_fields)

    return {
        "success": True,
        "step": "ready_to_write",
        "record_fields": record_fields,
        "tags": tag_result["tags"],
        "title": title,
        "feishu_link": feishu_link,
        "instruction": (
            "请调用 feishu_bitable_create_record 创建记录：\n"
            f"  app_token={BITABLE_APP_TOKEN}\n"
            f"  table_id={BITABLE_TABLE_ID}\n"
            f"  fields={json.dumps(record_fields, ensure_ascii=False, indent=2)}"
        ),
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python3 engine.py <ZSXQ分享链接>")
        print("示例: python3 engine.py https://t.zsxq.com/6L4Ry")
        sys.exit(1)

    share_url = sys.argv[1]
    result = run(share_url)
    print(f"\n结果: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()

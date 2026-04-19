"""feishu_doc_reader.py — 飞书文档内容获取"""
import json, re, urllib.request, os
from typing import Optional

FEISHU_USER_TOKEN_PATH = "~/.qclaw/skills-config/feishu/tokens/user_token.json"


def get_user_token() -> str:
    with open(os.path.expanduser(FEISHU_USER_TOKEN_PATH)) as f:
        d = json.load(f)
    return d.get("access_token", "")


def extract_doc_token(feishu_url: str) -> str:
    """从飞书文档URL提取doc_token"""
    patterns = [
        r'/docx/([a-zA-Z0-9]+)',
        r'/doc/([a-zA-Z0-9]+)',
        r'/wiki/([a-zA-Z0-9]+)',
    ]
    for p in patterns:
        m = re.search(p, feishu_url)
        if m:
            return m.group(1)
    return ""


def extract_doc_title(feishu_url: str) -> str:
    """获取飞书文档标题（纯API，无SDK）"""
    doc_token = extract_doc_token(feishu_url)
    if not doc_token:
        return ""
    try:
        token = get_user_token()
        req = urllib.request.Request(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("data", {}).get("title", "")
    except Exception as e:
        print(f"    [feishu] 文档标题获取失败: {e}")
        return ""


def fetch_doc_content(feishu_url: str) -> str:
    """
    获取飞书文档 raw_content（Markdown，截取前5000字）
    """
    doc_token = extract_doc_token(feishu_url)
    if not doc_token:
        return ""
    try:
        token = get_user_token()
        req = urllib.request.Request(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            content = data.get("data", {}).get("content", "")
            return content[:5000]
    except Exception as e:
        print(f"    [feishu] 文档内容获取失败: {e}")
        return ""

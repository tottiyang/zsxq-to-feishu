"""
feishu_doc_reader.py — 飞书文档内容获取

支持 /docx/ 链接（直接 API）和 /wiki/ 链接（需要解析为 docx token 再调 API）。
"""

import json, re, urllib.request, os

FEISHU_USER_TOKEN_PATH = "~/.qclaw/skills-config/feishu/tokens/user_token.json"


def get_user_token() -> str:
    with open(os.path.expanduser(FEISHU_USER_TOKEN_PATH)) as f:
        d = json.load(f)
    return d.get("access_token", "")


def _extract_docx_token(feishu_url: str) -> str:
    """从 URL 提取 docx token（/docx/TOKEN 或 /doc/TOKEN）"""
    for p in [r'/docx/([a-zA-Z0-9]+)', r'/doc/([a-zA-Z0-9]+)']:
        m = re.search(p, feishu_url)
        if m:
            return m.group(1)
    return ""


def _extract_wiki_node_token(feishu_url: str) -> str:
    """从 URL 提取 wiki node token（/wiki/TOKEN）"""
    m = re.search(r'/wiki/([a-zA-Z0-9]+)', feishu_url)
    return m.group(1) if m else ""


def _resolve_wiki_to_docx(wiki_node_token: str, space_id: str) -> str:
    """
    通过飞书 Wiki API 将 wiki node token 解析为 docx token。
    成功返回 docx token，失败返回空字符串。
    """
    try:
        token = get_user_token()
        url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes/{wiki_node_token}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())
            if d.get("code") == 0:
                node = d.get("data", {}).get("node", {})
                return node.get("obj_token", "") or ""
            return ""
    except Exception:
        return ""


def extract_doc_title(feishu_url: str) -> str:
    """
    获取飞书文档标题。

    对于 /wiki/ 链接，通过 wiki API 解析为 docx token 后再查标题。
    """
    docx_token = _extract_docx_token(feishu_url)
    wiki_node = _extract_wiki_node_token(feishu_url)

    if not docx_token and wiki_node:
        # 尝试 wiki API 解析
        docx_token = _resolve_wiki_to_docx(wiki_node, "7620079371449125819")

    if not docx_token:
        return ""

    try:
        token = get_user_token()
        req = urllib.request.Request(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{docx_token}",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("code") == 0:
                return data.get("data", {}).get("title", "") or \
                       data.get("data", {}).get("document", {}).get("title", "")
    except Exception as e:
        print(f"    [feishu] 文档标题获取失败: {e}")

    return ""


def fetch_doc_content(feishu_url: str) -> str:
    """
    获取飞书文档 raw_content（Markdown，截取前5000字）。
    支持 /docx/ 和 /wiki/ 两种链接格式。
    """
    docx_token = _extract_docx_token(feishu_url)
    wiki_node = _extract_wiki_node_token(feishu_url)

    if not docx_token and wiki_node:
        docx_token = _resolve_wiki_to_docx(wiki_node, "7620079371449125819")

    if not docx_token:
        return ""

    try:
        token = get_user_token()
        req = urllib.request.Request(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{docx_token}/raw_content",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            if data.get("code") == 0:
                content = data.get("data", {}).get("content", "")
                return content[:5000]
    except Exception as e:
        print(f"    [feishu] 文档内容获取失败: {e}")

    return ""

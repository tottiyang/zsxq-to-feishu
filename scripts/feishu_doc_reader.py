"""feishu_doc_reader.py — 飞书文档内容获取"""
import json, re, urllib.request
FEISHU_USER_TOKEN_PATH = "~/.qclaw/skills-config/feishu/tokens/user_token.json"

def get_user_token() -> str:
    with open(FEISHU_USER_TOKEN_PATH.expanduser()) as f:
        d = json.load(f)
    return d.get("access_token", "")

def extract_doc_token(feishu_url: str) -> str | None:
    m = re.search(r'(?:wiki|docx)/([a-zA-Z0-9]+)', feishu_url)
    return m.group(1) if m else None

def fetch_doc_content(feishu_url: str) -> str:
    doc_token = extract_doc_token(feishu_url)
    if not doc_token:
        return ""
    token = get_user_token()
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("data", {}).get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            return content[:5000]
    except Exception as e:
        print(f"飞书文档读取失败 {feishu_url}: {e}")
        return ""

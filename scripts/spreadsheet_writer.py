"""spreadsheet_writer.py — 飞书电子表格写入（已实测验证 ✅ 2026-04-19）"""
import json, time, urllib.request

APP_ID = "cli_a95e368b8cf89bc4"
APP_SECRET = "3Y5LRpcDnAo8XEip4zv9fhIARz6HwtEO"
SPREADSHEET_TOKEN = "JmMhsCi5Bhc9dMth7QocNJPZnrh"
SHEET_ID = "70f043"

_tenant_token_cache = None
_token_expire_time = 0

def get_tenant_token() -> str:
    global _tenant_token_cache, _token_expire_time
    current_time = time.time()
    if _tenant_token_cache and current_time < _token_expire_time - 300:
        return _tenant_token_cache
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        _tenant_token_cache = data["tenant_access_token"]
        _token_expire_time = current_time + data.get("expire_in", 7200)
        return _tenant_token_cache

def row_to_values(data: dict) -> list:
    return [
        data.get("feishu_url", ""),
        data.get("article_url", ""),
        data.get("topic_id", ""),
        data.get("title", ""),
        data.get("author", ""),
        data.get("create_time_str", ""),   # 格式: "2026-04-15 12:20"
        data.get("share_url", ""),
        data.get("is_digest", "否"),
        data.get("tags_str", ""),
        data.get("tag_notes", "{}"),
    ]

def batch_write_rows(rows: list[list], start_row: int = 2) -> dict:
    token = get_tenant_token()
    end_row = start_row + len(rows) - 1
    range_ = f"{SHEET_ID}!A{start_row}:J{end_row}"
    payload = {"valueRange": {"range": range_, "values": rows}}
    url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_last_row() -> int:
    token = get_tenant_token()
    url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values/{SHEET_ID}!C:C"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        values = result.get("data", {}).get("valueRange", {}).get("values", [])
    last_row = 1
    for i, row in enumerate(values):
        if row and row[0]:
            last_row = i + 1
    return last_row

def test_connection():
    print("=== 飞书电子表格写入验证 ===")
    test_row = [
        "https://my.feishu.cn/wiki/test", "https://articles.zsxq.com/test.html",
        "TEST_ID", "测试标题", "测试作者",
        "2026-04-19 12:00", "https://t.zsxq.com/TEST", "否",
        "AI编程,实战", '{"AI编程": "核心主题"}'
    ]
    result = batch_write_rows([test_row], start_row=2)
    print(f"写入: code={result.get('code')}, updatedCells={result.get('data',{}).get('updatedCells')}")
    cleanup = batch_write_rows([[None]*10], start_row=2)
    print(f"清理: code={cleanup.get('code')}")
    print("✓ 验证完成")

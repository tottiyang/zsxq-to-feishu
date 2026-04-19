"""
config.py — ZSXQ话题拉取系统常量配置
"""

GROUP_ID = "15552545485212"
ZSXQ_URL = "https://wx.zsxq.com/group/15552545485212"
CHROME_DEBUG_PORT = 28800
PLAYWRIGHT_MODULE = "/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright"

FEISHU_APP_ID = "cli_a95e368b8cf89bc4"
FEISHU_APP_SECRET = "3Y5LRpcDnAo8XEip4zv9fhIARz6HwtEO"
SPREADSHEET_TOKEN = "JmMhsCi5Bhc9dMth7QocNJPZnrh"
SHEET_ID = "70f043"

COLUMNS = [
    "飞书链接", "文章地址", "话题ID", "标题",
    "作者", "发布时间", "链接", "是否精华", "标签", "标签说明"
]

STOP_TIME_PHASE1 = "2024-01-01T00:00:00+0800"
BEGIN_TIME_PHASE2 = "2025-01-01T00:00:00+0800"

"""
config.py — ZSXQ话题拉取系统常量配置
"""

GROUP_ID = "15552545485212"
ZSXQ_URL = "https://wx.zsxq.com/group/15552545485212"

# Chrome Remote Debugging 端口（以实际运行端口为准，2026-04-19 确认：9333）
CHROME_DEBUG_PORT = 9333

# Playwright Node.js 模块路径（npx 缓存）
PLAYWRIGHT_MODULE = "/Users/totti/.npm/_npx/705bc6b22212b352/node_modules"

# ZSXQ API Token（Cookie 中的 zsxq_access_token）
ZSXQ_TOKEN = "A45B66F3-9226-4FE0-94DF-1AE8248512B9_F908FDC766129DED"

FEISHU_APP_ID = "cli_a95e368b8cf89bc4"
FEISHU_APP_SECRET = "3Y5LRpcDnAo8XEip4zv9fhIARz6HwtEO"
SPREADSHEET_TOKEN = "JmMhsCi5Bhc9dMth7QocNJPZnrh"
SHEET_ID = "70f043"

# 10列表头（A~J）
COLUMNS = [
    "飞书链接",    # A
    "文章地址",    # B
    "话题ID",     # C
    "标题",       # D
    "作者",       # E
    "发布时间",    # F
    "分享链接",    # G
    "是否精华",   # H
    "标签",       # I  ← 由大模型根据飞书文档内容生成（仅飞书链接话题）
    "标签说明",   # J  ← 每个标签的生成原因
]

# Phase1: 24年及之前精华
STOP_TIME_PHASE1 = "2024-01-01T00:00:00+0800"
# Phase2: 25年至今全量
BEGIN_TIME_PHASE2 = "2025-01-01T00:00:00+0800"

# API 限速配置（秒，浮动范围避免触发限流）
TOPICS_FETCH_INTERVAL = (3, 6)   # iter_topics 翻页间隔
SHARE_URL_INTERVAL    = (1, 2)   # 逐条获取分享链接间隔
TITLE_TAG_INTERVAL    = (0.5, 1.0) # LLM 调用间隔

# Phase1 翻页缓存：达到此条数强制写表（避免内存过大）
BATCH_WRITE_THRESHOLD = 200

---
name: zsxq-to-feishu
version: 1.2.0
description: "将知识星球（ZSXQ）分享链接转化为结构化数据，自动提取标签并写入 Feishu 多维表格。触发词：拉取 ZSXQ、整理 ZSXQ 内容、ZSXQ 到飞书、知识星球内容入库。"
metadata:
  requires:
    bins: ["node"]
    scripts: ["extractor.py", "extractor_share.py", "tagger.py", "engine.py", "config.py"]
  scriptsDir: "scripts/"
---

# ZSXQ 精选内容拉取工具

将知识星球分享链接自动整理入库的全流程技能。

**飞书说明文档**：[ZSXQ精选内容拉取工具·完整说明文档](https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh)

> ⚠️ **本文档是唯一真相来源**，代码与文档保持完全同步。每次修改代码后必须同步更新本 SKILL.md。

---

## 目标多维表格

| 字段 | 类型 | 说明 |
|------|------|------|
| 飞书链接 | URL | 指向 Wiki 文档，含 link + text |
| 话题ID | 文本 | **topic_id**，约17位数字，如 `45544844845444248` |
| 标题 | 文本 | 话题完整标题 |
| 作者 | 文本 | 发布者昵称 |
| 发布时间 | 日期 | 毫秒级时间戳（`2026-04-09 14:38`） |
| 标签 | 多选 | 抽象标签 + 具体功能标签 |
| 标签说明 | 文本 | 每个标签的语义解释 |
| 标签频次 | 文本 | 关键词出现次数 |
| 链接 | 文本 | ZSXQ 分享链接（`https://t.zsxq.com/xxxx`） |

**app_token**: `XpGMbvYwsaNvZMsBzZ3cN1DRnOc`
**table_id**: `tblt1Lm7ipCFuyXi`

---

## 完整执行流程

### 第一阶段：提取 ZSXQ 数据

**入口脚本**：`engine.py`

```bash
cd ~/.qclaw/skills/zsxq-to-feishu/scripts
python3 engine.py "https://t.zsxq.com/6L4Ry"
```

`engine.py` 调用 `extractor.py` → Playwright CDP 连接本地 Chrome → 提取数据。

**技术要求**：
- Chrome 开启 Remote Debugging：`/Applications/Google Chrome.app --remote-debugging-port=28800`
- Playwright CDP 模式：`chromium.connectOverCDP('http://localhost:28800')`
- 复用浏览器登录 Cookie，无需重新认证

**提取流程**：
1. Playwright 导航到分享链接 → 自动跳转话题详情页
2. 点击「展开全部」→ 展开话题全文（含评论中的飞书链接）
3. 从 DOM 提取第一个飞书文档链接（`a[href]` 含 `feishu.cn`）
4. 正则匹配正文提取作者 / 时间 / 标题

**返回数据**（`extractor.py` → `engine.py`）：
```python
{
    "success": True,
    "feishu_link": "https://my.feishu.cn/wiki/xxx",
    "title": "话题标题",
    "author": "作者名",
    "date_str": "2026-04-09 14:38",
    "zsxq_url": "https://wx.zsxq.com/dms/xxx/activity/messages"
}
```

**硬过滤**：没有飞书文档链接 → `return {"success": False, "error": "[步骤1失败] 未找到飞书文档链接"}`

**作者正则**（从话题正文提取）：
```
格式：返回 {星球名} {作者} {时间}
正则：/返回\s+[^\s]+\s+([^\s（(]{1,10})\s+\d{4}-\d{2}-\d{2}}/
示例：返回 AI破局俱乐部 行者 2026-04-09 14:38 → author = "行者"
```

**时间正则**：
```
正则：/([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2})/
```

---

### 第二阶段：读取飞书文档

`engine.py` 返回 `feishu_token`，Agent 调用 `feishu_doc` 工具读取正文。

```python
feishu_doc(action="read", doc_token="QVtCw3sIji9qNvkEEjWckpB8ncq")
```

飞书 Token 提取：从 URL `https://my.feishu.cn/wiki/SxRzwvSSWiTa7Kk57gKcQJbGnqg` 取路径最后一段。

---

### 第三阶段：智能标签提取

`engine.py` 的 `process_content()` 函数处理正文内容：

```python
from tagger import extract_tags, format_record_tags

tag_result = extract_tags(feishu_content, title)
# tag_result: {"tags": [...], "tag_desc": "...", "tag_freq": "..."}
```

**抽象标签**（内容类别）：持久化到 `data/abstract_tags.json`，动态追加
- 初始：`写作/提示词/智能体/获客/自媒体`
- 新标签由 **LLM 生成 → Agent 固化到 JSON** → 后续自动复用

**快速判断规则**（不依赖 LLM）：
- `编程开发`：Python/代码/cursor/claude code/...
- `效率工具`：Notion/工作流/自动化/模板/...
- `AI研究`：论文/模型/benchmark/DeepSeek/...
- `学习教育`：教程/课程/入门/指南/...
- `生活应用`：美食/健身/旅行/...

**具体功能标签**（应用场景）：始终由规则动态生成，不固化
- `口语陪练/AI伙伴/PPT制作/Claude Code/Cursor编程/DeepSeek/小红书运营/视频创作/Coze智能体`

**LLM 介入**：`extract_tags()` 返回 `result["llm_needed"] == True` 时，Agent 调 LLM 生成标签后调用 `persist_new_abstract_tags()` 固化到 JSON。

**标签说明格式**：`{标签名}：{一句话说明}，{关键指标}`
**标签频次格式**：`伙伴37次、Agent15次...`

---

### 第四阶段：写入多维表格

Agent 调用 OpenClaw 内置工具写入：

```python
feishu_bitable_create_record(
    app_token="XpGMbvYwsaNvZMsBzZ3cN1DRnOc",
    table_id="tblt1Lm7ipCFuyXi",
    fields={
        "飞书链接": {"link": "https://my.feishu.cn/wiki/xxx", "text": "标题"},
        "话题ID": "45544844845444248",   # ← topic_id，约17位数字
        "标题": "完整标题",
        "作者": "作者名",
        "发布时间": 1775716680000,          # ⚠️ 必须毫秒级
        "标签": ["智能体", "AI伙伴"],       # MultiSelect，新值自动创建
        "标签说明": "...",
        "标签频次": "...",
        "链接": "https://t.zsxq.com/XXXX"
    }
)
```

**时间戳计算**：
```python
from datetime import datetime, timezone, timedelta
cst = timezone(timedelta(hours=8))
dt = datetime(2026, 4, 9, 14, 38, 0, tzinfo=cst)
int(dt.timestamp() * 1000)  # → 1775716680000
```

**已有话题更新**：每次写入前 `list_records` 查询去重，避免重复创建。

---

## 踩坑点速查

| # | 坑 | 原因 | 解决方案 |
|---|-----|------|---------|
| 1 | 直接用 user token 调用 Bitable API → 404 | user token 无 `bitable:app` 权限 | 用 OpenClaw 内置工具（内部用 tenant token） |
| 2 | MultiSelect 写入新标签值报错 | 不知道可以自动创建 | 直接写标签字符串，Feishu 自动创建选项 ✅ |
| 3 | DateTime 字段显示 1970/2038 年 | 传了秒级时间戳 | 乘以 1000：`int(dt.timestamp() * 1000)` |
| 4 | 删除字段失败 | user token 无 `base:field:delete` | 在飞书 UI 中手动删除 |
| 5 | 记录 ID 全部 `RecordIdNotFound` | 手动删列后 table 重置 | 每次写入前 `list_records` 重新查询 |
| 6 | ZSXQ 跳转登录页 | 无头浏览器无登录态 | CDP 模式连接本地 Chrome |
| 7 | feishu_doc 写入文档空 | user token API 块结构 key 错误 | 用 `feishu_doc` 工具（Lark SDK） |

---

## 文件结构

```
zsxq-to-feishu/
├── SKILL.md              ← 本文件，唯一真相来源
├── scripts/
│   ├── config.py         ← 常量 + 时间戳计算 + 字段名
│   ├── extractor.py      ← ZSXQ 元数据提取（Playwright CDP）
│   ├── extractor_share.py← ZSXQ 分享链接提取（CDP + Playwright，备用）
│   ├── tagger.py        ← jieba 分词 + 混合标签提取
│   └── engine.py         ← 主流程编排
└── data/
    └── abstract_tags.json← 抽象标签持久化（动态追加）
```

---

## 触发词

- "拉取 ZSXQ" / "整理 ZSXQ" / "ZSXQ 到飞书"
- "知识星球内容入库" / "抓取 ZSXQ 内容"
- 发送 ZSXQ 分享链接（自动识别处理）

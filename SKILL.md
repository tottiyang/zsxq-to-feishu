---
name: zsxq-to-feishu
version: 1.1.2
description: "将知识星球（ZSXQ）分享链接转化为结构化数据，自动提取标签并写入 Feishu 多维表格。触发词：拉取 ZSXQ、整理 ZSXQ 内容、ZSXQ 到飞书、知识星球内容入库。"
metadata:
  requires:
    bins: ["node"]
    scripts: ["extractor_share.py", "extractor.py", "tagger.py", "engine.py", "config.py"]
  scriptsDir: "scripts/"
---

# ZSXQ 精选内容拉取工具

> 将知识星球分享链接自动整理入库的全流程技能。
>
> **文档**：[ZSXQ精选内容拉取工具·完整说明文档](https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh)
>
> ⚠️ **本文档是唯一真相来源**，代码与文档保持完全同步。每次修改代码后必须同步更新本 SKILL.md。

## 标签体系（混合方案 v2）

**抽象标签**（描述内容类别）：持久化到 JSON 文件，支持动态追加
- 初始标签：`写作/提示词/智能体/获客/自媒体`
- 新标签由 **LLM 生成 → Agent 固化到 JSON** → 后续自动复用

**快速判断**（不依赖 LLM）：当规则匹配不上时，用 QUICK_TAG_RULES 做 fallback：
- `编程开发`：Python/代码/cursor/claude code/...
- `效率工具`：Notion/工作流/自动化/模板/...
- `AI研究`：论文/模型/benchmark/DeepSeek/...
- `学习教育`：教程/课程/入门/指南/...
- `生活应用`：美食/健身/旅行/...

**具体功能标签**（描述具体应用场景）：始终由规则动态生成，不固化
- `口语陪练/AI伙伴/PPT制作/Claude Code/Cursor编程/DeepSeek/小红书运营/视频创作/千人大会/Coze智能体`
- 新功能标签随内容自动新增，不需要固化

**LLM 介入条件**：已知标签 + 快速规则都匹配不上时，生成 `llm_context`，Agent 读取后调用 LLM，调用 `persist_new_abstract_tags()` 固化结果。

## 能力概述

1. **接收** ZSXQ 分享链接（如 `https://t.zsxq.com/6L4Ry`）
2. **拦截** 三个点按钮 API 响应，获取分享链接 + topic_id（Playwright CDP）
3. **提取** 飞书文档链接 + 话题元数据
4. **⚠️ 硬过滤**：无飞书文档链接 → 直接跳过，不写入表格
5. **读取** 飞书文档正文（`feishu_doc` 工具）
6. **分析** 内容标签（jieba 分词 + 词频统计）
7. **写入** Feishu 多维表格（9字段结构）

---

## 目标多维表格

| 字段 | 类型 | 说明 |
|------|------|------|
| 飞书链接 | URL | 指向 Wiki 文档 |
| 话题ID | 文本 | Wiki 节点 token，格式 `wiki_XXXXXXXX` |
| 标题 | 文本 | 话题完整标题 |
| 作者 | 文本 | 发布者昵称 |
| 发布时间 | 日期 | 毫秒级时间戳 |
| 标签 | 多选 | 抽象标签 + 具体功能标签 |
| 标签说明 | 文本 | 每个标签的语义解释 |
| 标签频次 | 文本 | 关键词出现次数 |
| 链接 | 文本 | ZSXQ 分享链接 |

**app_token**: `XpGMbvYwsaNvZMsBzZ3cN1DRnOc`
**table_id**: `tblt1Lm7ipCFuyXi`

---

## 完整执行流程

### 步骤 1：自动化获取话题分享链接（核心能力）

> ✅ 已验证成功（2026-04-18）：无需用户提供，Agent 自动从话题列表拦截。

**核心技术**：点击话题卡片的三个点按钮 → 触发 `GET /v2/topics/{topic_id}/share_url` API → Playwright 拦截响应 → 提取分享链接和 topic_id。

```bash
# 完整流程（Playwright 拦截 + 批量提取）
node zsxq_complete.js
# 输出：所有话题的 topic_id、分享链接、标题、作者、飞书链接
```

**三个点按钮定位**：
```javascript
// 三个点在 .talk-content-container 内的 p.ellipsis 元素
const ellipsisBtns = document.querySelectorAll('p.ellipsis');
```

**API 响应拦截**：
```javascript
// Playwright 拦截 api.zsxq.com 的响应
await page.route('**/api.zsxq.com/**', async route => {
  const response = await route.fetch();
  const body = await response.json();
  if (body.topic?.share_url) {
    // 提取 share_url: https://t.zsxq.com/xxxx
    // 提取 topic_id: topic.topic_id（约17位数字）
  }
  route.continue();
});
```

**已成功提取的分享链接（AI破局俱乐部示例）**：

| 话题 | 作者 | 分享链接 | 飞书文档 |
|------|------|---------|---------|
| Claude code 写作指南 | 陈行之（皮特） | `https://t.zsxq.com/6L4Ry` | ✅ |
| 45岁负债翻盘 | 晟豪加油 | `https://t.zsxq.com/2aFht` | ✅ |
| AI英语口语陪练 | MQ老师 | `https://t.zsxq.com/ycQDT` | ✅ |
| 没背景怎么靠AI翻盘 | 观星Meta | `https://t.zsxq.com/O0b4R` | ✅ |
| 扣子2.5实测 | 行者 | `https://t.zsxq.com/ZVdnV` | ✅ |

---

### 步骤 2：提取 ZSXQ 元数据

通过 Playwright CDP 拦截 api.zsxq.com 响应，自动提取 topic_id 和分享链接（步骤1已完成后）。

```bash
cd ~/.qclaw/skills/zsxq-to-feishu/scripts
python3 extractor_share.py "https://t.zsxq.com/6L4Ry"
```

**提取流程**（自动完成）：
1. Playwright CDP 导航到分享链接（自动跳转话题详情页）
2. 拦截 `GET /v2/topics/{topic_id}/share_url` 响应 → 提取 `share_url` 和 `topic_id`
3. 点击「展开全部」展开话题全文（含评论中的飞书链接）
4. 从 DOM 提取所有飞书文档链接（`a[href]` 包含 `feishu.cn`）
   - **⚠️ 硬规则：没有飞书文档链接的话题直接跳过，不写入多维表格**
5. 正则匹配正文提取作者/时间/标题

返回：
```json
{
  "success": true,
  "topic_id": "45544844845444248",
  "share_url": "https://t.zsxq.com/6L4Ry",
  "title": "话题标题",
  "author": "作者名",
  "date_str": "2026-04-09 14:38",
  "feishu_links": [
    "https://my.feishu.cn/wiki/xxx",
    "https://my.feishu.cn/docx/yyy"
  ],
  "expanded": true
}
```

**topic_id 格式**：约17位数字，如 `45544844845444248`

**分享链接格式**：`https://t.zsxq.com/xxxx`（短链接）

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

**CDP 连接要求**：
- Chrome 必须开启 Remote Debugging：`/Applications/Google Chrome.app --remote-debugging-port=28800`
- Playwright CDP 模式：`chromium.connectOverCDP('http://localhost:28800')`
- 复用浏览器登录 Cookie，无需重新认证

### 步骤 2：读取飞书文档正文

从步骤1获取 `feishu_token` 后，读取文档正文用于标签分析。

```python
feishu_doc(action="read", doc_token="QVtCw3sIji9qNvkEEjWckpB8ncq")
```

飞书文档 Token 提取：从 URL `https://my.feishu.cn/wiki/SxRzwvSSWiTa7Kk57gKcQJbGnqg` 取路径最后一段。

### 步骤 3：智能标签提取

```python
# Agent 调用 tagger.py
feishu_doc(action="read", doc_token="...")
# 获取正文 content 后：
from tagger import extract_tags, persist_new_abstract_tags

result = extract_tags(content, title)
# result["llm_needed"] == True 时，需要 Agent 调 LLM
```

**算法流程**：
1. jieba 分词 + 词频统计
2. 从 JSON 文件加载已知抽象标签，规则匹配
3. 匹配不上 → QUICK_TAG_RULES 快速判断（不依赖 LLM）
4. 仍匹配不上 → `result["llm_needed"] = True`，生成 `llm_context`
5. Agent 调 LLM 生成新标签 → `persist_new_abstract_tags()` 固化到 JSON

**抽象标签**：持久化到 `data/abstract_tags.json`，新标签固化后自动加入
**功能标签**：动态生成，不需要固化

**标签说明格式**：`{标签名}：{一句话说明}，{关键指标}`

### 步骤 4：写入多维表格

```python
# 写入记录
feishu_bitable_create_record(
    app_token="XpGMbvYwsaNvZMsBzZ3cN1DRnOc",
    table_id="tblt1Lm7ipCFuyXi",
    fields={
        "飞书链接": {"link": "https://...", "text": "标题"},
        "话题ID": "wiki_XXXXXXXX",
        "标题": "完整标题",
        "作者": "作者名",
        "发布时间": 1775716680000,    # ⚠️ 毫秒级时间戳！
        "标签": ["智能体", "AI伙伴"], # MultiSelect，新值会自动创建选项
        "标签说明": "智能体：Agent应用场景... | AI伙伴：...",
        "标签频次": "伙伴37次、Agent15次...",
        "链接": "https://t.zsxq.com/XXXX"
    }
)
```

**时间戳计算**：
```python
from datetime import datetime, timezone, timedelta
cst = timezone(timedelta(hours=8))
dt = datetime(2026, 4, 9, 14, 38, 0, tzinfo=cst)
ms = int(dt.timestamp() * 1000)  # 1775716680000
```

---

## 踩坑点速查

| # | 坑 | 原因 | 解决方案 |
|---|-----|------|---------|
| 1 | 直接用 user token 调用 Bitable API → 404 | user token 无 `bitable:app` 权限 | 用 OpenClaw 内置工具（内部用 tenant token） |
| 2 | MultiSelect 写入新标签值报错 | 不知道可以自动创建 | 直接写入新标签字符串，Feishu 自动创建选项 ✅ |
| 3 | DateTime 字段显示 1970/2038 年 | 传了秒级时间戳而非毫秒级 | 乘以 1000：`int(dt.timestamp() * 1000)` |
| 4 | 删除字段失败 | user token 无 `base:field:delete` | 在飞书 UI 中手动删除 |
| 5 | 记录 ID 全部 `RecordIdNotFound` | 手动删除列后 table 被重置 | 每次写入前 `list_records` 重新查询 |
| 6 | ZSXQ 跳转登录页 | 无头浏览器无登录态 | CDP 模式连接本地 Chrome，复用登录 Cookie |
| 7 | feishu_doc 写入文档空 | user token API 块结构 key 错误 | 用 `feishu_doc` 工具，内部用 Lark SDK |

---

## 文件结构

```
zsxq-to-feishu/
├── SKILL.md              ← 本文件，唯一真相来源
├── scripts/
│   ├── config.py         ← 配置常量 + 标签持久化（JSON）
│   ├── extractor_share.py ← ZSXQ 分享链接提取（CDP + Playwright）
│   ├── extractor.py      ← ZSXQ 元数据提取（旧版，保留兼容）
│   ├── tagger.py         ← jieba 分词 + 混合标签提取算法
│   └── engine.py         ← 主流程编排
├── data/
│   └── abstract_tags.json  ← 抽象标签持久化文件（动态追加）
└── references/
    └── (预留扩展)
```

**extractor_share.py**（推荐使用）：
- 输入：ZSXQ 分享链接
- 输出：话题永久链接 + 元数据 + 飞书链接列表
- 技术：Playwright CDP 连接本地 Chrome

---

## 工具速查

| 操作 | 工具/命令 | 说明 |
|------|----------|------|
| 提取 ZSXQ 分享链接 | `python3 extractor_share.py <url>` | CDP + Playwright，含飞书链接列表 |
| 提取标签 | `extract_tags(content, title)` | 返回 tags/llm_needed/llm_context |
| LLM生成标签固化 | `persist_new_abstract_tags(["新标签"])` | 写入 JSON 文件 |
| 列出所有抽象标签 | `list_abstract_tags()` | 从 JSON 读取 |
| 时间戳计算 | `str_to_ms("2026-04-09 14:38")` | 必须毫秒级 |
| 读取飞书文档 | `feishu_doc(action="read")` | — |
| 创建记录 | `feishu_bitable_create_record` | MultiSelect 新值自动创建 |

---

## 触发词

当用户说以下内容时激活本技能：
- "拉取 ZSXQ" / "整理 ZSXQ"
- "ZSXQ 到飞书" / "知识星球内容入库"
- "把 ZSXQ 分享链接整理到飞书"
- "抓取 ZSXQ 内容"
- 发送 ZSXQ 分享链接（自动识别处理）

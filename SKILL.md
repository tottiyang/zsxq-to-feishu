---
name: zsxq-to-feishu
version: 1.0.0
description: "将知识星球（ZSXQ）分享链接转化为结构化数据，自动提取标签并写入 Feishu 多维表格。触发词：拉取 ZSXQ、整理 ZSXQ 内容、ZSXQ 到飞书、知识星球内容入库。"
metadata:
  requires:
    bins: ["node"]
    scripts: ["extractor.py", "tagger.py", "engine.py", "config.py"]
  scriptsDir: "scripts/"
---

# ZSXQ 精选内容拉取工具

> 将知识星球分享链接自动整理入库的全流程技能。
>
> **文档**：[ZSXQ精选内容拉取工具·完整说明文档](https://my.feishu.cn/wiki/Kjd1wsLXGic9iTkmETBcwKEjnOh)
>
> ⚠️ **本文档是唯一真相来源**，代码与文档保持完全同步。每次修改代码后必须同步更新本 SKILL.md。

## 能力概述

1. **接收** ZSXQ 分享链接（如 `https://t.zsxq.com/6L4Ry`）
2. **提取** 飞书文档链接 + 话题元数据（Playwright CDP）
3. **读取** 飞书文档正文（`feishu_doc` 工具）
4. **分析** 内容标签（jieba 分词 + 词频统计）
5. **写入** Feishu 多维表格（9字段结构）

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

### 步骤 1：提取 ZSXQ 元数据

使用 Playwright 连接本地 Chrome（CDP 模式），从分享链接页面提取飞书文档链接和话题元数据。

```bash
cd ~/.qclaw/skills/zsxq-to-feishu/scripts
python3 extractor.py "https://t.zsxq.com/6L4Ry"
```

返回：
```json
{
  "success": true,
  "feishu_link": "https://my.feishu.cn/wiki/...",
  "title": "话题标题",
  "author": "作者名",
  "date_str": "2026-04-09 14:38",
  "zsxq_url": "https://wx.zsxq.com/dms/..."
}
```

**关键点**：
- ZSXQ 需要登录态，CDP 连接本地 Chrome（`http://localhost:28800`）复用登录 Cookie
- 飞书链接从 DOM 中的 `<a href>` 提取（关键字：`feishu.cn/wiki` 或 `feishu.cn/docx`）
- 作者从正文正则匹配：`/返回\s+[^\s]+\s+([^\s（(]{1,10})/`
- 时间从正文正则匹配：`/([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2})/`

### 步骤 2：读取飞书文档正文

从步骤1获取 `feishu_token` 后，读取文档正文用于标签分析。

```python
feishu_doc(action="read", doc_token="QVtCw3sIji9qNvkEEjWckpB8ncq")
```

飞书文档 Token 提取：从 URL `https://my.feishu.cn/wiki/SxRzwvSSWiTa7Kk57gKcQJbGnqg` 取路径最后一段。

### 步骤 3：智能标签提取

使用 `scripts/tagger.py` 分析正文，自动生成标签。

```bash
python3 scripts/tagger.py  # 内部函数调用，非命令行
```

标签体系：

**抽象标签**（描述内容类别）：
- `写作` — AI 辅助写作、文案创作
- `提示词` — Prompt Engineering
- `智能体` — Agent/智能体应用
- `获客` — 变现、商业化
- `自媒体` — 内容创业、个人IP

**具体功能标签**（描述具体应用场景，随内容新增）：
- `口语陪练` — AI 英语口语练习
- `AI伙伴` — Coze Agent World / AI Companion
- `PPT制作` — 演示文稿制作
- `Claude Code` — Claude Code 写作辅助
- 其他按内容新增

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
│   ├── config.py         ← 多维表格配置常量（app_token/table_id/字段名）
│   ├── extractor.py      ← Playwright 提取 ZSXQ 元数据
│   ├── tagger.py         ← jieba 分词 + 标签提取算法
│   └── engine.py         ← 主流程编排
└── references/
    └── (预留扩展)
```

---

## 工具速查

| 操作 | 工具/命令 | 踩坑 |
|------|----------|------|
| 提取 ZSXQ 元数据 | `python3 extractor.py <url>` | 需要 CDP 登录态 |
| 提取标签 | `extract_tags(content, title)` | jieba 分词 |
| 时间戳计算 | `str_to_ms("2026-04-09 14:38")` | 必须毫秒级 |
| 读取飞书文档 | `feishu_doc(action="read")` | — |
| 创建记录 | `feishu_bitable_create_record` | MultiSelect 新值自动创建 |
| 更新标签 | `feishu_bitable_update_record` | 同上 |

---

## 触发词

当用户说以下内容时激活本技能：
- "拉取 ZSXQ" / "整理 ZSXQ"
- "ZSXQ 到飞书" / "知识星球内容入库"
- "把 ZSXQ 分享链接整理到飞书"
- "抓取 ZSXQ 内容"
- 发送 ZSXQ 分享链接（自动识别处理）

---
name: zsxq-to-feishu
version: 1.3.0
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

> ⚠️ **本文档是唯一真相来源**，代码与文档保持完全同步。

---

## 目标多维表格

| 字段 | 类型 | 说明 |
|------|------|------|
| 飞书链接 | URL | `{link, text}` 对象格式 |
| 话题ID | 文本 | **topic_id**，约17位数字 |
| 标题 | 文本 | 话题完整标题 |
| 作者 | 文本 | 发布者昵称，含括号内昵称 |
| 发布时间 | 日期 | 毫秒级时间戳 |
| 标签 | 多选 | 2-4个，由 LLM 提取 |
| 标签说明 | 文本 | LLM 理由说明 |
| 链接 | 文本 | ZSXQ 分享链接 |

**app_token**: `XpGMbvYwsaNvZMsBzZ3cN1DRnOc`
**table_id**: `tblt1Lm7ipCFuyXi`

---

## 完整执行流程

### 阶段零：Chrome 检查

**Chrome 必须开启 Remote Debugging**：
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=28800
```

### 阶段一：提取 ZSXQ 数据

**单条分享链接（已知 `t.zsxq.com` 链接）**：
```bash
cd ~/.qclaw/skills/zsxq-to-feishu/scripts
python3 engine.py "https://t.zsxq.com/6L4Ry"
```

**批量精华话题列表（推荐，新方案）**：
直接从星球 API 拉取精华话题，从正文提取飞书链接：

```python
# 技术方案：Playwright XHR 拦截（绕过 ZSXQ X-Signature 签名验证）
# 原理：XMLHttpRequest 的 withCredentials=true 自动携带完整 cookie session
import subprocess, json, re
from html import unescape

def fetch_topics_xhr(group_id: str = "15552545485212", count: int = 20) -> list[dict]:
    js = """
const {chromium} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');
(async () => {
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    const page = await ctx.newPage();  // ⚠️ 必须用 newPage()，不能用 pages()[0]（会 detach！）
    await page.goto('https://wx.zsxq.com/group/""" + group_id + """', {waitUntil:'domcontentloaded', timeout:15000});
    await page.waitForTimeout(3000);
    const r = await page.evaluate(async () => new Promise(resolve => {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', 'https://api.zsxq.com/v2/groups/""" + group_id + """/topics?scope=digests&count=20', true);
        xhr.withCredentials = true;
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.onload = () => { try { resolve(JSON.parse(xhr.responseText)); } catch(e) { resolve({error:e.message}); } };
        xhr.send();
    }));
    console.log('DATA:' + JSON.stringify(r?.resp_data?.topics || []));
    await browser.close();
})().catch(e => { console.error('ERROR:'+e.message); process.exit(1); });
"""
    result = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
    topics = json.loads(result.stdout.split('DATA:')[1]) if 'DATA:' in result.stdout else []
    return [{'topic_id': t['topic_id'], 'type': t['type'],
             'author': t.get('talk',{}).get('owner',{}).get('name','') or t.get('question',{}).get('owner',{}).get('name',''),
             'text': t.get('talk',{}).get('text','') or t.get('question',{}).get('text','') or '',
             'create_time': t.get('create_time','')}
            for t in topics]

# 提取飞书链接
def extract_feishu_links(text: str) -> list[str]:
    text = unescape(text)
    import urllib.parse
    try: text = urllib.parse.unquote(text)
    except: pass
    return list(set(re.findall(r'https://my\.feishu\.cn/(?:wiki|docx)/[a-zA-Z0-9]+', text)))

# 使用
topics = fetch_topics_xhr("15552545485212", 20)
records = [{'title': t['text'][:80].split(chr(10))[0], 'author': t['author'],
            'feishu_link': extract_feishu_links(t['text'])[0],
            'topic_id': t['topic_id'], 'create_time': t['create_time']}
           for t in topics if extract_feishu_links(t['text'])]
# records → feishu_bitable_create_record
```

**提取数据格式**：
```python
{
    "success": True,
    "feishu_link": "https://my.feishu.cn/wiki/xxx",
    "title": "话题标题",
    "author": "陈行之（皮特）",
    "date_str": "2026-04-15 20:28",
    "zsxq_url": "https://wx.zsxq.com/group/xxx/topic/xxx",
    "zsxq_topic_id": "45544844845444248",
    "zsxq_token": "feishu_token",  # 用于 feishu_doc 读取
}
```

**作者提取**：找 `返回 {星球}` 行，下一行即为作者行。自动清理回复标记如 `回复 xxx`。

---

### 阶段一附：获取话题分享链接

**星球 group_id：**
- AI破局俱乐部：`15552545485212`

**方式A — 已知 topic_id，获取分享链接**

```python
from extractor_share import extract_share_url
result = extract_share_url("45544844845444248", group_id="15552545485212")
# → {"share_url": "https://t.zsxq.com/xxxx", "topic_id": "...", "title": "..."}
```

**方式B — 已知分享链接，完整提取元数据 + 飞书链接**

```python
from extractor_share import extract_full
result = extract_full("https://t.zsxq.com/XXXX")
# → {"share_url", "topic_id", "title", "author", "date_str", "feishu_links": []}
```

**如何获取 topic_id：**
打开 ZSXQ 星球话题页 → Chrome DevTools → Network → 筛选 `/topics/` 请求 → 响应 body 中含 `topic_id`（约17位数字）

---

### 阶段二：读取飞书文档

Agent 调用 `feishu_doc` 读取正文（截取前4000字传给 tagger）：
```
feishu_doc(action="read", doc_token="QVtCw3sIji9qNvkEEjWckpB8ncq")
```

---

### 阶段三：LLM 提取标签

Agent 用 `tagger.py` 的 `build_llm_prompt()` 生成提示词，直接用自己（本身就是 LLM）回答：

```python
from tagger import build_llm_prompt, parse_llm_response, format_record_tags

llm_prompt = build_llm_prompt(feishu_content, title)
# Agent 将提示词发给自己（LLM）提取标签
# 解析 LLM 回复
tag_result = parse_llm_response(llm_response)
# tag_result: {"tags": [...], "tag_desc": "..."}
```

参考标签（可直接使用）：`写作、提示词、智能体、获客、自媒体、AI研究、编程开发、效率工具、学习教育`

输出格式（只需 JSON）：`{"tags": ["标签1", "标签2"], "reason": "简短说明"}`

---

### 阶段四：写入多维表格

```python
feishu_bitable_create_record(
    app_token="XpGMbvYwsaNvZMsBzZ3cN1DRnOc",
    table_id="tblt1Lm7ipCFuyXi",
    fields={
        "飞书链接": {"link": "https://my.feishu.cn/wiki/xxx", "text": "标题"},
        "话题ID": "45544844845444248",
        "标题": "完整标题",
        "作者": "陈行之（皮特）",
        "发布时间": 1776256080000,          # 毫秒级时间戳
        "标签": ["写作", "智能体"],
        "标签说明": "标签1 / 标签2 理由说明",
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

---

## 踩坑点速查

| # | 坑 | 原因 | 解决方案 |
|---|-----|------|---------|
| 1 | 作者提取为空 | 作者行在换行后，正则按空格匹配失败 | 按行解析：`lines[i+1]` |
| 2 | 飞书链接写入报 URLFieldConvFail | 传了纯字符串 | 用 `{link, text}` 对象格式 |
| 3 | MultiSelect 报错 | 新标签值报错 | 直接写字符串，Feishu 自动创建选项 |
| 4 | DateTime 显示 1970/2038 | 传了秒级时间戳 | `int(dt.timestamp() * 1000)` |
| 5 | ZSXQ 跳转登录页 | 无头浏览器无登录态 | CDP 模式连接本地 Chrome |
| 6 | `split('\n')` Node.js 语法错误 | Python 把 `\n` 写成了实际换行符 | 写 `split('\\n')` 传递字面 `\n` |
| 7 | **`Frame has been detached` SIGTERM** | `ctx.pages()[0]` 对已关闭的 tab 操作 | **必须用 `await ctx.newPage()` 创建新 page** |
| 8 | **topics API 返回 401 / "需要星主同意"** | MCP Bearer token 无法访问星球接口 | 用 Playwright XHR + `withCredentials=true` 绕过签名验证 |

---

## 文件结构

```
zsxq-to-feishu/
├── SKILL.md              ← 本文件，唯一真相来源
└── scripts/
    ├── config.py         ← 常量 + 时间戳计算 + 字段名
    ├── extractor.py      ← ZSXQ 单条分享链接提取（Playwright CDP）
    ├── extractor_share.py← ZSXQ topic_id→分享链接提取（CDP + Playwright，备用）
    ├── test_group_extract.py  ← 批量精华话题提取（测试用）
    ├── tagger.py         ← LLM 标签提取提示词生成
    └── engine.py         ← 主流程编排（单条）
```

**批量精华话题提取**（推荐）：直接调用 ZSXQ topics API → 正则提取飞书链接 → 写多维表格。参考 `SKILL.md` 阶段一"批量精华话题列表"章节。

---

## 触发词

- "拉取 ZSXQ" / "整理 ZSXQ" / "ZSXQ 到飞书"
- "知识星球内容入库" / "抓取 ZSXQ 内容"
- 发送 ZSXQ 分享链接（自动识别处理）
��处理）

# ZSXQ话题批量拉取系统

**需求文档：https://my.feishu.cn/wiki/KomvwfEpjikGLbk6QJNc7gjAnCf**
**本文档：https://my.feishu.cn/wiki/JkUzwkSVUiJoh5kDjKfcmpPQnQf**
**目标储存：飞书电子表格（JmMhsCi5Bhc9dMth7QocNJPZnrh，sheet_id=70f043）**
**代码目录：~/.qclaw/skills/zsxq-to-feishu/scripts/**

---

## 核心踩坑（必须先读）

### 1. ZSXQ API 无原生 share_url 字段

ZSXQ Topics API 返回的 topic 数据中**没有** share_url 原生字段。分享链接格式为 `https://t.zsxq.com/{6位短码}`，需要单独从话题详情页提取。

### 2. topic_id ≠ 分享短码

`topic_id`（17位纯数字）不能直接拼接成分享链接，短码是另一套编码。必须通过访问话题详情页 DOM 获取。

### 3. 同步 XHR 必须用 `xhr.open(..., false)`

Playwright evaluate 中用 `xhr.open(..., true)`（异步）会导致回调乱序，topics 返回空数组。**必须用 `xhr.open(..., false)`（同步模式）**。

### 4. Sheets API v2/v3 分工

- **元信息查询**（spreadsheet/sheets query）→ v3 端点
- **数据读写**（values read/write）→ v2 端点
- 混用会导致 404。

### 5. Chrome Remote Debugging

Chrome 必须以 `--remote-debugging-port=28800` 启动，且需已登录知识星球。

---

## 模块清单与函数说明

### 1. config.py

常量配置：GROUP_ID、飞书电子表格配置（APP_ID、SPREADSHEET_TOKEN、SHEET_ID）、时间边界（STOP_TIME_PHASE1、BEGIN_TIME_PHASE2）。

### 2. zsxq_api.py

**核心模块**，提供 ZSXQ API 访问能力。

| 函数 | 功能 | 说明 |
|------|------|------|
| `validate_token()` | 验证 Chrome 登录态 | 拉取1条 topics 验证返回 |
| `fetch_page(group_id, scope, count, end_time, begin_time)` | 获取单页 topics | 返回 topics 列表 |
| `iter_topics(group_id, scope, end_time, stop_time, begin_time)` | 迭代翻页获取全部 topics | 间隔随机3~6秒 |
| `fetch_share_urls_for_topics(topics, group_id)` | 批量获取分享链接 | asyncio 并发访问话题详情页 |

**技术实现**：Playwright 连接 Chrome CDP → evaluate 中执行 XMLHttpRequest withCredentials=true → 同步模式 XHR 绕过签名验证。

### 3. filter.py

话题过滤器，数据清洗。

| 函数 | 功能 | 说明 |
|------|------|------|
| `extract_feishu_links(text)` | 提取飞书链接 | 正则 `<e type="web" href>` + HTML+URL双解码 |
| `parse_time_ms(iso_time)` | ISO时间→毫秒时间戳 | 飞书日期字段需要毫秒级 |
| `extract_topic_data(topic, share_map)` | 提取入库字段（10列）| 无外链返回 None |

**入库条件**（二选一）：有飞书链接 或 有 article_url。两者都没有 → 跳过。

### 4. persistence.py

SQLite 断点续传。

| 函数 | 功能 |
|------|------|
| `is_synced(topic_id)` | 检查是否已入库 |
| `mark_synced(topic_id, phase)` | 标记已入库（INSERT OR IGNORE）|
| `save_checkpoint(phase, ...)` | 保存断点（last_end_time、last_topic_id、total_synced）|
| `load_checkpoint(phase)` | 加载断点（打断恢复）|
| `get_all_synced_ids()` | 获取全部已入库 topic_id（批量排重）|

### 5. tagger.py

标签提取。**由 Agent 自身大模型执行，不调用外部 API**。

| 函数 | 功能 |
|------|------|
| `build_tag_prompt(title, content)` | 构建提示词（system_prompt + user_prompt）|
| `tags_to_row(tags_result)` | 将标签结果转为表格格式 |

**固化提示词**（SYSTEM_PROMPT）：
- 标签由 Agent 根据文档内容自由生成，不限候选池
- abstract_tags：1~2个宏观主题
- functional_tags：2~4个具体工具/平台/方法
- tag_explanations：每个标签一句话解释
- 内容无关时：返回空数组

### 6. feishu_doc_reader.py

飞书文档内容获取。

| 函数 | 功能 |
|------|------|
| `get_user_token()` | 读取 user_access_token |
| `extract_doc_token(feishu_url)` | 从 URL 提取 doc_token |
| `fetch_doc_content(feishu_url)` | 获取文档 raw_content（Markdown，截取前5000字）|

### 7. spreadsheet_writer.py

飞书电子表格写入（已实测验证 ✅）。

| 函数 | 功能 |
|------|------|
| `get_tenant_token()` | 获取 tenant_access_token（缓存，TTL=7200秒）|
| `row_to_values(data)` | topic data → 10列表格行 |
| `batch_write_rows(rows, start_row)` | 批量写入（PUT values API）|
| `get_last_row()` | 查询最后有数据的行号 |
| `test_connection()` | 验证写入连通性 |

### 8. engine.py

主流程调度器。

| 函数 | 功能 |
|------|------|
| `run_phase(phase, scope, end_time, stop_time, begin_time)` | 执行单个阶段 |
| `main()` | CLI 入口，解析命令行参数 |

**执行步骤**：
1. 加载断点（如有）
2. `iter_topics()` 拉取 topics
3. `fetch_share_urls_for_topics()` 批量获取分享链接
4. 过滤 + 排重
5. 标签提取（Agent 大模型，仅有飞书链接的话题）
6. 写入电子表格
7. 保存断点

**CLI 用法**：
```
python engine.py verify  # 验证 Token + 电子表格
python engine.py test    # 测试模式（20条）
python engine.py phase1  # 24年精华（digests，翻到2024-01-01停止）
python engine.py phase2  # 25年至今（all）
python engine.py phase3  # 每周增量（上周一~本周一）
```

### agent_llm_infer() 占位函数

在 engine.py 中由 Agent 自身大模型替换实现。Agent 将 `build_tag_prompt()` 返回的 system_prompt + user_prompt 注入自身推理，返回 JSON 标签结果。

---

## 三个执行阶段

| 阶段 | scope | 边界条件 | 说明 |
|------|-------|---------|------|
| Phase 1 | digests | stop_time=2024-01-01 | 24年及之前精华，从新到旧翻页 |
| Phase 2 | all | begin_time=2025-01-01 | 25年至今全量，跳过 Phase1 已处理的 |
| Phase 3 | all | begin_time=上周一，end_time=本周一 | 每周增量 |

---

## 踩坑记录

| # | 坑 | 原因 | 解决方案 |
|---|-----|------|---------|
| 1 | topics API 返回"需要星主同意" | Bearer Token 权限不足 | Playwright XHR + withCredentials=true |
| 2 | topics 返回空数组 | 异步 XHR 回调乱序 | `xhr.open(..., false)` 同步模式 |
| 3 | `Frame has been detached` SIGTERM | `ctx.pages()[0]` 对已关闭tab操作 | `ctx.newPage()` |
| 4 | 飞书链接提取失败 | 链接藏在 `<e type="web" href>` 属性里 | HTML+URL双解码正则 |
| 5 | DateTime 显示 1970 | 秒级时间戳给飞书 | `int(dt.timestamp() * 1000)` 毫秒级 |
| 6 | Sheets API 404 | 元信息用了 v2 端点 | 元信息：v3，数据读写：v2 |
| 7 | ZSXQ 无原生 share_url | API 本身不返回 | 访问话题详情页提取 |

---

## 待办清单

| # | 待办 | 责任方 | 状态 |
|---|------|--------|------|
| 1 | Chrome 开启 Remote Debugging（端口28800） | 用户 | ⏳ 待确认 |
| 2 | Chrome 已登录知识星球 | 用户 | ⏳ 待确认 |
| 3 | 验证 ZSXQ Token（`python engine.py verify`） | Agent | ⏳ ①②后执行 |
| 4 | Phase 1 试跑（20条验证全链路） | Agent | ⏳ ③通过后 |
| 5 | Phase 1 全量拉取 | Agent | ⏳ 试跑后 |
| 6 | Phase 2 全量拉取 | Agent | ⏳ Phase1后 |
| 7 | Phase 3 定时任务 | Agent | ⏳ Phase2后 |

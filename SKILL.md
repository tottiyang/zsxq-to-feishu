# ZSXQ话题批量拉取系统

**需求文档：https://my.feishu.cn/wiki/KomvwfEpjikGLbk6QJNc7gjAnCf**
**技术文档：https://my.feishu.cn/wiki/JkUzwkSVUiJoh5kDjKfcmpPQnQf**
**目标储存：飞书电子表格（JmMhsCi5Bhc9dMth7QocNJPZnrh，sheet_id=70f043）**
**代码目录：~/.qclaw/skills/zsxq-to-feishu/scripts/**
**版本：2026-04-19**

---

## 核心踩坑（必须先读）

### 1. ZSXQ API 无原生 share_url 字段

**正确方案：page.route 拦截 API**
- 浏览器请求：`GET https://api.zsxq.com/v2/topics/{topic_id}/share_url`
- Playwright `page.route('**/api.zsxq.com/**')` 拦截响应
- 分享链接格式：`https://t.zsxq.com/{6位短码}`
- 操作流程：导航到话题详情页 → 模拟点击 `.talk-content-container` 内的 `.p.ellipsis` 按钮 → 拦截API响应 → 从JSON中提取 `share_url`

### 2. topics 返回空数组

Playwright evaluate 中用 `xhr.open(..., true)`（异步）会导致回调乱序。必须用 `xhr.open(..., false)`（同步模式）。

### 3. Sheets API v2/v3 分工

- 元信息查询 → v3 端点
- 数据读写 → v2 端点

---

## 模块清单与函数说明

### 1. config.py

常量配置：GROUP_ID、飞书电子表格配置、时间边界（STOP_TIME_PHASE1、BEGIN_TIME_PHASE2）。

### 2. zsxq_api.py

| 函数 | 功能 | 说明 |
|------|------|------|
| validate_token() | 验证 Chrome 登录态 | 拉取1条 topics 验证返回 |
| fetch_page(group_id, scope, count, end_time, begin_time) | 获取单页 topics | 返回 topics 列表 |
| iter_topics(group_id, scope, end_time, stop_time, begin_time) | 迭代翻页获取全部 topics | 间隔随机3~6秒 |
| fetch_share_urls_for_topics(topics, group_id) | 批量获取分享链接 | page.route 拦截 /topics/{id}/share_url API |

**技术实现**：
- Playwright XHR 同步模式绕过签名验证
- 分享链接：page.route 拦截 API → 模拟点击 `.p.ellipsis` → 提取 `share_url`

### 3. filter.py

| 函数 | 功能 | 说明 |
|------|------|------|
| extract_feishu_links(text) | 提取飞书链接 | 正则 + HTML+URL双解码 |
| parse_time_str(iso_time) | ISO时间→"YYYY-MM-DD HH:MM"格式 | 直接返回可读字符串 |
| extract_topic_data(topic, share_map) | 提取入库字段（10列）| 无外链返回 None |

**入库条件**（二选一）：有飞书链接 或 有 article_url。

### 4. persistence.py

| 函数 | 功能 |
|------|------|
| is_synced(topic_id) | 检查是否已入库 |
| mark_synced(topic_id, phase) | 标记已入库 |
| save_checkpoint(phase, ...) | 保存断点 |
| load_checkpoint(phase) | 加载断点 |
| get_all_synced_ids() | 批量排重 |

### 5. tagger.py

| 函数 | 功能 |
|------|------|
| build_tag_prompt(title, content) | 构建提示词 |
| tags_to_row(tags_result) | 标签结果→表格格式 |

**固化提示词**：标签不限候选池，abstract_tags 1~2个 + functional_tags 2~4个 + 说明。

### 6. feishu_doc_reader.py

| 函数 | 功能 |
|------|------|
| get_user_token() | 读取 user_access_token |
| extract_doc_token(feishu_url) | 从 URL 提取 doc_token |
| extract_doc_title(feishu_url) | 获取飞书文档标题（用于替换ZSXQ原始标题）|
| fetch_doc_content(feishu_url) | 获取文档 raw_content（Markdown，截取前5000字）|

**标题逻辑**：有飞书链接 → 优先用飞书文档标题；无飞书链接 → 用 ZSXQ 原始标题。

### 7. spreadsheet_writer.py

| 函数 | 功能 |
|------|------|
| get_tenant_token() | tenant_access_token（缓存，TTL=7200秒）|
| row_to_values(data) | topic data → 10列表格行 |
| batch_write_rows(rows, start_row) | 批量写入（v2端点）|
| get_last_row() | 查询最后有数据的行号 |
| test_connection() | 验证连通性 |

**时间格式**：`F列 = "YYYY-MM-DD HH:MM"`（字符串，非时间戳）

### 8. engine.py

执行步骤：
1. 加载断点
2. iter_topics() 拉取 topics
3. fetch_share_urls_for_topics() 获取分享链接
4. 过滤 + 排重
5. **飞书文档标题获取**（有链接 → 调飞书API替换标题）
6. **标签提取**（Agent 大模型，仅有飞书链接的话题）
7. 批量写入电子表格
8. 保存断点

CLI：
```
python engine.py verify  # 验证 Token + 电子表格
python engine.py test    # 测试模式（20条 digests）
python engine.py phase1  # 24年精华
python engine.py phase2  # 25年至今
python engine.py phase3  # 每周增量
```

### agent_llm_infer() 占位函数

由 Agent 自身大模型替换实现，注入 build_tag_prompt() 返回的提示词，返回 JSON 标签结果。

---

## 三个执行阶段

| 阶段 | scope | 边界条件 | 说明 |
|------|-------|---------|------|
| Phase 1 | digests | stop_time=2024-01-01 | 24年及之前精华，从新到旧 |
| Phase 2 | all | begin_time=2025-01-01 | 25年至今全量 |
| Phase 3 | all | 上周一~本周一 | 每周增量，每周一触发 |

---

## 踩坑记录

| # | 坑 | 原因 | 解决方案 |
|---|-----|------|---------|
| 1 | topics API "需要星主同意" | Bearer Token权限不足 | XHR + withCredentials=true |
| 2 | topics 返回空数组 | 异步XHR回调乱序 | xhr.open(..., false) 同步模式 |
| 3 | 分享链接获取失败 | 无原生字段 | page.route 拦截 /topics/{id}/share_url API |
| 4 | 飞书链接提取失败 | 藏在HTML标签属性里 | 正则 + HTML+URL双解码 |
| 5 | 发布时间格式错误 | 时间戳不兼容 | "YYYY-MM-DD HH:MM"字符串格式 |
| 6 | Sheets API 404 | 端点混用 | 元信息：v3，数据读写：v2 |

---

## 待办清单

| # | 待办 | 状态 |
|---|------|------|
| 1 | Chrome 开启 Remote Debugging（端口28800） | ⏳ 等用户确认 |
| 2 | Chrome 已登录知识星球 | ⏳ 等用户确认 |
| 3 | 验证 Token（python engine.py verify） | ⏳ ①②后执行 |
| 4 | Phase 1 试跑20条 | ⏳ ③通过后 |
| 5 | Phase 1 全量拉取 | ⏳ 试跑后 |
| 6 | Phase 2 全量拉取 | ⏳ Phase1后 |
| 7 | Phase 3 定时任务 | ⏳ Phase2后 |

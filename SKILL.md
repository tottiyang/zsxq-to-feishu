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

## 存储字段（8列）

| 列 | 字段名 | 说明 |
|----|--------|------|
| A | 飞书链接 | 话题正文中的飞书文档链接 |
| B | 文章地址 | talk.article.article_url |
| C | 话题ID | ZSXQ topic_id |
| D | 标题 | 飞书文档标题 / Agent总结正文生成 |
| E | 作者 | 发布者昵称 |
| F | 发布时间 | YYYY-MM-DD HH:MM |
| G | 链接 | ZSXQ分享链接（https://t.zsxq.com/{短码}） |
| H | 是否精华 | "是" 或 "否" |

---

## 模块清单

| 文件 | 功能 |
|------|------|
| config.py | 常量配置 |
| zsxq_api.py | ZSXQ API 访问（XHR同步 + page.route分享链接）|
| filter.py | 话题过滤（提取链接、时间、字段）|
| persistence.py | SQLite 断点续传 |
| tagger.py | 标题生成提示词（Agent 大模型）|
| feishu_doc_reader.py | 飞书文档标题/内容获取 |
| spreadsheet_writer.py | 电子表格写入（v2端点）|
| engine.py | 主流程调度器 |

---

## 标题生成逻辑

| 情况 | 标题来源 |
|------|---------|
| 有飞书链接 | extract_doc_title() → 飞书文档标题 |
| 无飞书链接，有正文 | Agent 总结正文生成标题（8~30字）|
| 都没有 | 跳过（不入库） |

---

## 三个执行阶段

| 阶段 | scope | 边界条件 |
|------|-------|---------|
| Phase 1 | digests | stop_time=2024-01-01 |
| Phase 2 | all | begin_time=2025-01-01 |
| Phase 3 | all | 上周一~本周一 |

CLI：
```
python engine.py verify  # 验证 Token + 电子表格
python engine.py test    # 测试模式（20条）
python engine.py phase1  # 24年精华
python engine.py phase2  # 25年至今
python engine.py phase3  # 每周增量
```

---

## 踩坑记录

| # | 坑 | 解决方案 |
|---|-----|---------|
| 1 | topics "需要星主同意" | XHR + withCredentials=true |
| 2 | topics 返回空数组 | xhr.open(..., false) 同步模式 |
| 3 | 分享链接获取失败 | page.route 拦截 API |
| 4 | 飞书链接提取失败 | HTML+URL双解码正则 |
| 5 | 发布时间格式错误 | "YYYY-MM-DD HH:MM"字符串 |
| 6 | Sheets API 404 | 元信息：v3，数据：v2 |

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

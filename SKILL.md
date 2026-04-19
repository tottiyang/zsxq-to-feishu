# ZSXQ话题拉取系统 — Skill 文档

**需求文档**：https://my.feishu.cn/wiki/KomvwfEpjikGLbk6QJNc7gjAnCf
**技术方案**：https://my.feishu.cn/wiki/JkUzwkSVUiJoh5kDjKfcmpPQnQf
**检查简报**：https://my.feishu.cn/wiki/DicewCWUpiJYNjk9TvnclU7Unld
**目标储存**：飞书电子表格（JmMhsCi5Bhc9dMth7QocNJPZnrh，sheet_id=70f043）
**代码目录**：`~/.qclaw/skills/zsxq-to-feishu/scripts/`
**版本**：2026-04-19

---

## 快速开始

```bash
cd ~/.qclaw/skills/zsxq-to-feishu/scripts

# 1. 验证全链路
python3 engine.py verify

# 2. 测试模式（20条精华）
python3 engine.py test

# 3. 执行拉取
python3 engine.py phase1   # 24年精华
python3 engine.py phase2   # 25年至今
python3 engine.py phase3   # 每周增量
```

---

## 文件结构

```
zsxq-to-feishu/
├── SKILL.md                    # 本文档
└── scripts/
    ├── config.py               # 常量配置（端口、Token、限速参数）
    ├── zsxq_api.py             # ZSXQ API（topics + 分享链接）
    ├── filter.py               # 话题过滤（提取飞书链接、入库字段）
    ├── persistence.py           # SQLite 断点续传
    ├── tagger.py               # 标题/标签生成提示词
    ├── feishu_doc_reader.py    # 飞书文档标题/内容获取
    ├── spreadsheet_writer.py   # 电子表格写入
    ├── engine.py               # 主流程（三个阶段）
    └── zsxq_sync_state.db     # SQLite 断点数据库
```

---

## 存储字段（10列）

| 列 | 字段名 | 说明 |
|----|--------|------|
| A | 飞书链接 | 话题正文中的飞书文档链接 |
| B | 文章地址 | talk.article.article_url |
| C | 话题ID | ZSXQ topic_id（约17位数字） |
| D | 标题 | 飞书文档标题 / Agent总结正文生成 |
| E | 作者 | 发布者昵称 |
| F | 发布时间 | 格式：YYYY-MM-DD HH:MM |
| G | 分享链接 | ZSXQ分享链接（https://t.zsxq.com/{短码}） |
| H | 是否精华 | "是" 或 "否" |
| I | 标签 | 仅飞书链接话题，由大模型根据文档内容生成 |
| J | 标签说明 | 每个标签的生成原因 |

---

## 核心设计决策

1. **直接 HTTP + Cookie**：不依赖 Chrome CDP，用 `http.client` 直接请求，Header 附 Cookie
2. **分享链接**：直接 GET `/v2/topics/{id}/share_url`，逐条限速 1~2 秒
3. **标签范围**：仅"有飞书链接"的话题生成标签（需求规范）
4. **缓冲写入**：满200条写一次电子表格，防止内存爆炸
5. **断点续传**：SQLite checkpoint，每次翻页后保存

---

## 已知限制

- ZSXQ 付费星球 API 需加入星球后 Token 才有效
- 分享链接 API 返回"主题不存在" = 话题已被删除
- Phase1 全量拉取预计耗时较长（翻页多 + 每条限速）

---

## Agent 交互流程

当用户提出 ZSXQ/知识星球相关需求时：

1. 读取【检查简报】确认当前状态
2. 运行 `python3 engine.py verify` 确认链路通畅
3. 按需执行 phase
4. 读取电子表格验证结果
5. 发现新问题 → 更新检查简报 + commit + push

---

*更新日期：2026-04-19*

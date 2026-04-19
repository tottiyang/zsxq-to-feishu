"""
engine.py — ZSXQ话题拉取系统主流程

三个阶段：
- Phase 1: 24年精华（scope=digests，翻到2024-01-01停止）
- Phase 2: 25年至今全量（scope=all）
- Phase 3: 每周增量（每周一拉取上周新增话题）

标签生成范围（需求规范）：
- 仅"有飞书链接"的话题需要生成标签
- 无飞书链接的话题：tags_str=""，tag_notes="{}"

使用方式：
    python engine.py verify  # 验证 ZSXQ Token + 电子表格写入
    python engine.py test   # 测试模式（20条）
    python engine.py phase1 # 拉取24年精华
    python engine.py phase2  # 拉取25年至今
    python engine.py phase3  # 每周增量
"""

import time, random, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import (
    GROUP_ID, STOP_TIME_PHASE1, BEGIN_TIME_PHASE2,
    TITLE_TAG_INTERVAL, BATCH_WRITE_THRESHOLD,
    SPREADSHEET_TOKEN, SHEET_ID
)
from zsxq_api import iter_topics, validate_token, fetch_page, fetch_share_urls
from filter import extract_topic_data
from feishu_doc_reader import extract_doc_title, fetch_doc_content
from tagger import build_title_prompt, parse_title_result, build_tag_prompt, tags_to_row
from spreadsheet_writer import batch_write_rows, row_to_values, get_last_row, test_connection
from persistence import SyncState


# ─────────── 工具函数 ───────────

def _sleep(msg: str = ""):
    """带随机抖动的安全间隔"""
    t = random.uniform(*TITLE_TAG_INTERVAL)
    if msg:
        print(f"    ⏳ 等待 {t:.1f}s {msg}")
    time.sleep(t)


# ─────────── 单条话题完整处理 ───────────

def process_topic(topic: dict, share_map: dict, state: SyncState) -> dict | None:
    """
    对单条 topic 执行：过滤 → 标题生成 → 标签生成（仅飞书链接）
    返回入库数据 dict，或 None（跳过）
    """
    tid = str(topic["topic_id"])
    data = extract_topic_data(topic, share_map)

    if not data:
        state.mark_synced(tid, "skip_no_link")
        return None

    # ── 标题生成 ──
    title_ready = False

    if data.get("feishu_url"):
        try:
            doc_title = extract_doc_title(data["feishu_url"])
            if doc_title and doc_title.strip():
                data["title"] = doc_title.strip()
                title_ready = True
        except Exception as e:
            print(f"    ⚠️ 文档标题获取失败: {e}")

    if not title_ready and data.get("clean_text"):
        try:
            sys_p, usr_p = build_title_prompt(data["clean_text"])
            summary = agent_llm_infer(sys_p, usr_p)
            generated = parse_title_result(summary)
            if generated:
                data["title"] = generated
                title_ready = True
            _sleep("标题生成")
        except Exception as e:
            print(f"    ⚠️ 标题生成异常: {e}")

    if not title_ready:
        data["title"] = f"无标题_{tid[-6:]}"

    # ── 标签生成（仅飞书链接） ──
    if data.get("has_feishu_link") and data.get("feishu_url"):
        try:
            doc_content = fetch_doc_content(data["feishu_url"])
            if doc_content:
                sys_p, usr_p = build_tag_prompt(data.get("title", "无标题"), doc_content)
                tags_result = agent_llm_infer(sys_p, usr_p)
                data["tags_str"], data["tag_notes"] = tags_to_row(tags_result)
                _sleep("标签生成")
        except Exception as e:
            print(f"    ⚠️ 标签生成异常: {e}")
            data["tags_str"] = ""
            data["tag_notes"] = "{}"
    else:
        data["tags_str"] = ""
        data["tag_notes"] = "{}"

    state.mark_synced(tid, "done")
    return data


# ─────────── Phase 执行 ───────────

def run_phase(phase: str, scope: str,
              end_time: str = None, stop_time: str = None,
              begin_time: str = None):
    print(f"\n{'='*60}")
    print(f"开始执行: {phase} (scope={scope})")
    print(f"  stop_time={stop_time}, begin_time={begin_time}, end_time={end_time}")
    print('='*60)

    state = SyncState()

    # 1. 加载断点
    checkpoint = state.load_checkpoint(phase)
    if checkpoint:
        print(f"  ✓ 从断点恢复: last_end={checkpoint['last_end_time'][:19]}, "
              f"total={checkpoint['total_synced']}")
        end_time = checkpoint.get("last_end_time") or end_time
    else:
        print(f"  ↗ 无断点，从头开始")

    # 2. 拉取 topics
    topics = iter_topics(
        group_id=GROUP_ID, scope=scope,
        end_time=end_time, stop_time=stop_time, begin_time=begin_time)

    if not topics:
        print("  ↘ 无新增 topics，退出")
        return

    print(f"  ↗ 拉取完成，共 {len(topics)} 条，开始获取分享链接...")

    # 3. 批量获取分享链接（逐条限速）
    def _on_progress(cur, total, tid, url):
        if cur % 20 == 0 or cur == total:
            print(f"    分享链接进度: {cur}/{total}")

    share_map = fetch_share_urls(topics, on_progress=_on_progress)

    # 4. 排重过滤 + 处理 + 缓冲写入
    synced_ids = state.get_all_synced_ids()
    to_write = []
    stats = {"dup": 0, "skip_no_link": 0, "ok": 0, "fail": 0}
    prev_checkpoint_total = checkpoint["total_synced"] if checkpoint else 0

    for i, topic in enumerate(topics):
        tid = str(topic["topic_id"])

        if tid in synced_ids:
            stats["dup"] += 1
            continue

        data = process_topic(topic, share_map, state)
        if not data:
            stats["skip_no_link"] += 1
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(topics)}] 跳过无链接话题，累计: {stats['skip_no_link']}")
            continue

        to_write.append(row_to_values(data))
        stats["ok"] += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(topics)}] 处理中，已入库缓冲: {len(to_write)} 条")

        # 缓冲超过阈值时写入（避免内存爆炸）
        if len(to_write) >= BATCH_WRITE_THRESHOLD:
            _flush_write(to_write, state, phase, topics, prev_checkpoint_total)
            to_write = []

    # 5. 最终写入
    _flush_write(to_write, state, phase, topics, prev_checkpoint_total)

    print(f"\n  📊 统计: 入库 {stats['ok']} 条, 重复跳过 {stats['dup']} 条, "
          f"无链接跳过 {stats['skip_no_link']} 条")
    print(f"  ✓ {phase} 完成")


def _flush_write(to_write: list, state: SyncState, phase: str,
                  all_topics: list, prev_total: int):
    """写入缓冲并保存断点"""
    if not to_write:
        return
    last_row = get_last_row()
    result = batch_write_rows(to_write, start_row=last_row + 1)
    written = len(to_write)
    cells = result.get("data", {}).get("updatedCells", 0)
    print(f"    ✓ 写入 {written} 条 (rows {last_row+1}~{last_row+written}), "
          f"updatedCells={cells}")
    # 断点：以最后一条 topic 为锚点
    if all_topics:
        state.save_checkpoint(phase,
            last_end_time=all_topics[-1]["create_time"],
            last_topic_id=str(all_topics[-1]["topic_id"]),
            total_synced=prev_total + written)


# ─────────── 测试模式 ───────────

def run_test():
    print("=" * 60)
    print("测试模式：20条精华话题跑全链路")
    print("=" * 60)

    topics = fetch_page(GROUP_ID, "digests", 20)
    print(f"\n① 获取 {len(topics)} 条 topics")

    print("\n② 获取分享链接...")
    def _on_progress(cur, total, tid, url):
        if cur % 5 == 0 or cur == total:
            print(f"    进度: {cur}/{total}, url={url[:40] if url else '(空)'}")
    share_map = fetch_share_urls(topics, on_progress=_on_progress)

    state = SyncState()
    to_write = []

    for i, topic in enumerate(topics):
        tid = str(topic["topic_id"])
        data = process_topic(topic, share_map, state)
        if data:
            to_write.append(row_to_values(data))
            print(f"    ✓ [{i+1}/{len(topics)}] {tid} → {data.get('title','')[:40]}")
        else:
            print(f"    -  [{i+1}/{len(topics)}] {tid} 无链接跳过")

    if to_write:
        last_row = get_last_row()
        result = batch_write_rows(to_write, start_row=last_row + 1)
        print(f"\n④ 写入 {len(to_write)} 条, code={result.get('code')}, "
              f"updatedCells={result.get('data',{}).get('updatedCells')}")
    print(f"\n🎉 测试完成，共入库 {len(to_write)} 条")


# ─────────── 验证模式 ───────────

def run_verify():
    print("=" * 60)
    print("验证模式：逐项验证全链路")
    print("=" * 60)

    # ① ZSXQ Token
    print("\n① 验证 ZSXQ Token...")
    assert validate_token(), "❌ Token 验证失败"
    print("✅ ZSXQ Token 正常")

    # ② 拉取1条真实话题
    print("\n② 拉取真实话题...")
    topics = fetch_page(GROUP_ID, "digests", 1)
    assert topics, "❌ 无法拉取 topics"
    topic = topics[0]
    tid = topic["topic_id"]
    print(f"✅ 拉取成功: topic_id={tid}, title={topic.get('title','')[:40]}")

    # ③ 分享链接
    print("\n③ 获取分享链接...")
    share_map = fetch_share_urls([topic])
    share_url = share_map.get(str(tid), "")
    print(f"   分享链接: {share_url or '(空)'}")
    if share_url:
        print("✅ 分享链接获取成功")
    else:
        print("⚠️ 分享链接为空（话题可能已被删除）")

    # ④ 过滤 + 入库字段
    print("\n④ 验证 extract_topic_data...")
    data = extract_topic_data(topic, share_map)
    assert data, "❌ extract_topic_data 返回空"
    print(f"   feishu_url: {data.get('feishu_url','')[:60] or '(空)'}")
    print(f"   article_url: {data.get('article_url','')[:60] or '(空)'}")
    print(f"   author: {data.get('author','')}")
    print(f"   has_feishu_link: {data.get('has_feishu_link')}")
    print("✅ 过滤逻辑正常")

    # ⑤ 飞书文档标题（有链接才测试）
    doc_title = None
    if data.get("feishu_url"):
        print("\n⑤ 验证飞书文档标题获取...")
        try:
            doc_title = extract_doc_title(data["feishu_url"])
            if doc_title:
                print(f"✅ 文档标题: {doc_title[:50]}")
            else:
                print("⚠️ 文档标题为空")
        except Exception as e:
            print(f"⚠️ 文档标题获取失败: {e}")

    # ⑥ 标签生成（有链接才测试）
    if data.get("has_feishu_link") and data.get("feishu_url"):
        print("\n⑥ 验证标签生成...")
        try:
            content = fetch_doc_content(data["feishu_url"])
            if content:
                sys_p, usr_p = build_tag_prompt(doc_title or data.get("title","无标题"), content)
                tags_result = agent_llm_infer(sys_p, usr_p)
                tags_str, tag_notes = tags_to_row(tags_result)
                print(f"✅ 标签: {tags_str or '(空)'}")
            else:
                print("⚠️ 文档内容为空，跳过标签测试")
        except Exception as e:
            print(f"⚠️ 标签生成失败: {e}")

    # ⑦ 表格写入
    print("\n⑦ 验证飞书表格写入...")
    test_connection()

    # 模拟写入
    test_data = dict(data)
    test_data["title"] = doc_title or data.get("title") or f"验证标题_{tid[-6:]}"
    row = row_to_values(test_data)
    last = get_last_row()
    result = batch_write_rows([row], start_row=last + 1)
    assert result.get("code") == 0, f"❌ 写入失败: {result}"
    print(f"✅ 模拟写入成功: row={last+1}, updatedCells={result.get('data',{}).get('updatedCells')}")

    print("\n" + "=" * 60)
    print("🎉 全链路验证通过！")
    print("=" * 60)


# ─────────── LLM 调用 ───────────

def agent_llm_infer(system_prompt: str, user_prompt: str) -> dict:
    """
    调用 MiniMax LLM 生成标题/标签
    MiniMax 返回: {"choices":[{"message":{"content":"..."}}]}
    从 content 中提取 JSON（去掉 思考标签和 markdown 代码块）
    """
    import urllib.request, json, re

    api_key = "sk-cp-WvWcTwaPyIlqlwwaHMQYbl_KoRQAv3O58ApgJLInk-Ussgbmy1HnNnil5vq1fj3eX1W7sEWDRhqANesMgzwq29NGscekqCg7MpxVFw5x_mT2PXxNzhaOQKc"
    url = "https://api.minimaxi.com/v1/chat/completions"

    payload = {
        "model": "MiniMax-M2.7",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 512
    }

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        raw = data["choices"][0]["message"].get("content", "")

    # 去掉 思考标签和 markdown
    text = re.sub(r"<begin_thinking>.*?</end_thinking>", "", raw, flags=re.DOTALL)
    parts = text.split("
</think>

")
    json_text = parts[-1].strip() if len(parts) > 1 else text.strip()
    json_text = re.sub(r"```(?:json)?\s*", "", json_text).strip()

    # 提取 {"title":...} 块（最后一个，即真实答案）
    matches = list(re.finditer(r'\{[^{}]*"title"[^{}]*\}', json_text, re.DOTALL))
    if matches:
        try:
            return json.loads(matches[-1].group())
        except Exception:
            pass

    # 尝试完整解析（标签结果可能无 title 字段）
    try:
        brace_start = json_text.rfind('{')
        if brace_start >= 0:
            return json.loads(json_text[brace_start:])
    except Exception:
        pass

    return {"Title": json_text[:100]}


# ─────────── 入口 ───────────

def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "test"

    if phase == "test":
        run_test()
    elif phase == "verify":
        run_verify()
    elif phase == "phase1":
        run_phase(phase="phase1_digests_2024", scope="digests",
                  stop_time=STOP_TIME_PHASE1)
    elif phase == "phase2":
        run_phase(phase="phase2_all_2025", scope="all",
                  begin_time=BEGIN_TIME_PHASE2)
    elif phase == "phase3":
        from datetime import datetime, timedelta
        today = datetime.now()
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        run_phase(phase="phase3_weekly", scope="all",
                  begin_time=last_monday.strftime("%Y-%m-%dT00:00:00+0800"),
                  end_time=this_monday.strftime("%Y-%m-%dT00:00:00+0800"))
    else:
        print(f"未知参数: {phase}")
        print("用法: python engine.py [test|verify|phase1|phase2|phase3]")


if __name__ == "__main__":
    main()

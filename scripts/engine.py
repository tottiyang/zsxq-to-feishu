"""
engine.py — ZSXQ话题拉取系统主流程

三个阶段：
- Phase 1: 24年精华（scope=digests，翻到2024-01-01停止）
- Phase 2: 25年至今全量（scope=all）
- Phase 3: 每周增量（每周一拉取上周新增话题）

使用方式：
    python engine.py verify  # 验证 ZSXQ Token + 电子表格写入
    python engine.py test    # 测试模式（20条）
    python engine.py phase1  # 拉取24年精华
    python engine.py phase2  # 拉取25年至今
    python engine.py phase3  # 每周增量
"""

import time, random, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import GROUP_ID, STOP_TIME_PHASE1, BEGIN_TIME_PHASE2
from zsxq_api import iter_topics, validate_token, fetch_page, fetch_share_urls_for_topics
from filter import extract_topic_data
from tagger import build_tag_prompt, tags_to_row
from feishu_doc_reader import fetch_doc_content
from spreadsheet_writer import batch_write_rows, row_to_values, get_last_row, test_connection
from persistence import SyncState


def run_phase(phase: str, scope: str,
              end_time: str = None, stop_time: str = None,
              begin_time: str = None):
    print(f"\n{'='*60}")
    print(f"开始执行: {phase} (scope={scope})")
    print('='*60)

    state = SyncState()

    # 1. 加载断点
    checkpoint = state.load_checkpoint(phase)
    if checkpoint:
        print(f"  从断点恢复: last_time={checkpoint['last_end_time'][:19]}, "
              f"total={checkpoint['total_synced']}")
        end_time = checkpoint["last_end_time"]
    else:
        print(f"  无断点，从头开始")

    # 2. 拉取 topics
    topics = iter_topics(
        group_id=GROUP_ID, scope=scope,
        end_time=end_time, stop_time=stop_time, begin_time=begin_time)

    if not topics:
        print("  无新增 topics，退出")
        return

    # 3. 批量获取分享链接
    print(f"  开始获取分享链接（共 {len(topics)} 条）...")
    share_map = fetch_share_urls_for_topics(topics, GROUP_ID)
    print(f"  分享链接获取完成：{sum(1 for v in share_map.values() if v)} 条有效链接")

    # 4. 批量排重
    synced_ids = state.get_all_synced_ids()
    total_topics = len(topics)
    to_write = []
    skipped_no_link = 0
    skipped_dupe = 0

    for i, topic in enumerate(topics):
        tid = str(topic["topic_id"])
        if tid in synced_ids:
            skipped_dupe += 1
            continue

        data = extract_topic_data(topic, share_map)
        if not data:
            state.mark_synced(tid, phase)
            skipped_no_link += 1
            print(f"  [{i+1}/{total_topics}] {tid} 无外链，跳过")
            continue

        # 5. 标签提取（仅有飞书链接的话题，由 Agent 大模型执行）
        if data.get("needs_tags") and data.get("feishu_url"):
            try:
                content = fetch_doc_content(data["feishu_url"])
                if content:
                    sys_prompt, usr_prompt = build_tag_prompt(data["title"], content)
                    # ============================================================
                    # 【关键】Agent 大模型推理
                    # Agent 将 system_prompt + user_prompt 注入自身大模型，
                    # 返回格式：{"abstract_tags": [...], "functional_tags": [...],
                    #           "tag_explanations": {...}}
                    # ============================================================
                    tags_result = agent_llm_infer(sys_prompt, usr_prompt)
                    tags_str, tag_notes = tags_to_row(tags_result)
                    data["tags_str"] = tags_str
                    data["tag_notes"] = tag_notes
                    print(f"  [{i+1}/{total_topics}] ✓ {data['title'][:40]} | 标签: {tags_str}")
                else:
                    data["tags_str"] = ""
                    data["tag_notes"] = "{}"
            except Exception as e:
                print(f"  标签提取异常: {e}")
                data["tags_str"] = ""
                data["tag_notes"] = "{}"
            time.sleep(random.uniform(1, 2))
        else:
            data["tags_str"] = ""
            data["tag_notes"] = "{}"

        row = row_to_values(data)
        to_write.append(row)
        state.mark_synced(tid, phase)

    print(f"\n  统计: 入库 {len(to_write)} 条, 重复跳过 {skipped_dupe} 条, "
          f"无链接跳过 {skipped_no_link} 条")

    # 6. 写入电子表格
    if to_write:
        last_row = get_last_row()
        result = batch_write_rows(to_write, start_row=last_row + 1)
        print(f"  写入: code={result.get('code')}, "
              f"updatedCells={result.get('data',{}).get('updatedCells')}")

    # 7. 保存断点
    if topics:
        state.save_checkpoint(phase,
            last_end_time=topics[-1]["create_time"],
            last_topic_id=str(topics[-1]["topic_id"]),
            total_synced=(checkpoint["total_synced"] if checkpoint else 0) + len(to_write))

    print(f"  ✓ {phase} 完成")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "test"

    if phase == "test":
        print("测试模式：拉取20条验证全链路")
        topics = fetch_page(GROUP_ID, "digests", 20)
        print(f"获取 {len(topics)} 条 topics")

    elif phase == "phase1":
        run_phase(phase="phase1_digests_2024", scope="digests",
                  stop_time=STOP_TIME_PHASE1)

    elif phase == "phase2":
        run_phase(phase="phase2_all_2025", scope="all",
                  begin_time=BEGIN_TIME_PHASE2)

    elif phase == "phase3":
        from datetime import datetime, timedelta
        today = datetime.now()
        last_monday = today - timedelta(days=today.weekday() + 7)
        this_monday = today - timedelta(days=today.weekday())
        run_phase(phase="phase3_weekly", scope="all",
                  end_time=this_monday.strftime("%Y-%m-%dT00:00:00+0800"),
                  begin_time=last_monday.strftime("%Y-%m-%dT00:00:00+0800"))

    elif phase == "verify":
        print("验证模式")
        assert validate_token(), "ZSXQ Token 验证失败"
        test_connection()

    else:
        print(f"未知阶段: {phase}")
        print("用法: python engine.py [test|phase1|phase2|phase3|verify]")


if __name__ == "__main__":
    main()


def agent_llm_infer(system_prompt: str, user_prompt: str) -> dict:
    """
    占位函数，由 Agent 自身大模型执行推理。
    Agent 将 system_prompt + user_prompt 注入自身大模型，返回 JSON 标签结果。
    固化提示词见 tagger.py。
    """
    raise NotImplementedError("此函数由 Agent 执行时替换实现")

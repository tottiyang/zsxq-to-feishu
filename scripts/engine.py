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
from feishu_doc_reader import extract_doc_title, fetch_doc_content
from tagger import build_title_prompt, parse_title_result, build_tag_prompt, tags_to_row
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

    # 4. 过滤 + 排重
    synced_ids = state.get_all_synced_ids()
    total_topics = len(topics)
    to_write = []
    skipped_no_link = 0
    skipped_dupe = 0
    skipped_title_fail = 0

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

        # 5. 标题生成
        # 三路径：
        #   a) 有飞书链接 → extract_doc_title() 取文档标题
        #   b) 无飞书链接但有正文 → Agent 总结正文生成标题
        #   c) 都失败 → 跳过
        title_ready = False
        if data.get("feishu_url"):
            try:
                doc_title = extract_doc_title(data["feishu_url"])
                if doc_title:
                    data["title"] = doc_title
                    print(f"  [{i+1}/{total_topics}] 飞书标题: {doc_title[:40]}")
                    title_ready = True
                else:
                    print(f"  [{i+1}/{total_topics}] 文档标题为空，将总结正文")
            except Exception as e:
                print(f"  文档标题获取失败: {e}")

        if not title_ready and data.get("clean_text"):
            # 无飞书链接 或 文档标题获取失败 → Agent 总结正文生成标题
            try:
                sys_p, usr_p = build_title_prompt(data["clean_text"])
                summary = agent_llm_infer(sys_p, usr_p)
                generated = parse_title_result(summary)
                if generated:
                    data["title"] = generated
                    print(f"  [{i+1}/{total_topics}] 总结标题: {generated[:40]}")
                else:
                    print(f"  [{i+1}/{total_topics}] 标题生成失败，跳过")
                    state.mark_synced(tid, phase)
                    skipped_title_fail += 1
                    continue
            except Exception as e:
                print(f"  标题生成异常: {e}，跳过")
                state.mark_synced(tid, phase)
                skipped_title_fail += 1
                continue
            time.sleep(random.uniform(0.5, 1.5))

        if not data.get("title"):
            print(f"  [{i+1}/{total_topics}] 无法生成标题，跳过")
            state.mark_synced(tid, phase)
            skipped_title_fail += 1
            continue

        # 6. 标签生成（仅飞书链接话题）
        if data.get("feishu_url"):
            try:
                content = fetch_doc_content(data["feishu_url"])
                if content:
                    title_for_tag = data.get("title") or "无标题"
                    sys_p, usr_p = build_tag_prompt(title_for_tag, content)
                    tags_result = agent_llm_infer(sys_p, usr_p)
                    data["tags_str"], data["tag_notes"] = tags_to_row(tags_result)
                    print(f"  [{i+1}/{total_topics}] 标签: {data['tags_str'][:30]}")
                else:
                    data["tags_str"] = ""
                    data["tag_notes"] = "{}"
            except Exception as e:
                print(f"  标签生成异常: {e}，设为空")
                data["tags_str"] = ""
                data["tag_notes"] = "{}"
        else:
            data["tags_str"] = ""
            data["tag_notes"] = "{}"

        # 7. 写入表格
        row = row_to_values(data)
        to_write.append(row)
        state.mark_synced(tid, phase)

    print(f"\n  统计: 入库 {len(to_write)} 条, 重复跳过 {skipped_dupe} 条, "
          f"无链接跳过 {skipped_no_link} 条, 标题失败跳过 {skipped_title_fail} 条")

    # 8. 写入电子表格
    if to_write:
        last_row = get_last_row()
        result = batch_write_rows(to_write, start_row=last_row + 1)
        print(f"  写入: code={result.get('code')}, "
              f"updatedCells={result.get('data',{}).get('updatedCells')}")

    # 9. 保存断点
    if topics:
        state.save_checkpoint(phase,
            last_end_time=topics[-1]["create_time"],
            last_topic_id=str(topics[-1]["topic_id"]),
            total_synced=(checkpoint["total_synced"] if checkpoint else 0) + len(to_write))

    print(f"  ✓ {phase} 完成")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "test"

    if phase == "test":
        print("=" * 50)
        print("测试模式：20条全类型话题跑全链路")
        print("=" * 50)

        # ① 拉取20条（混合精华+非精华）
        topics = fetch_page(GROUP_ID, "digests", 20)
        print(f"\n① 获取 {len(topics)} 条 topics")

        # ② 获取分享链接
        share_map = fetch_share_urls_for_topics(topics, GROUP_ID)
        print(f"② 分享链接获取完成：{sum(1 for v in share_map.values() if v)} 条有效")

        # ③ 过滤+标题+标签
        state = SyncState()
        to_write = []
        for i, topic in enumerate(topics):
            tid = str(topic["topic_id"])
            data = extract_topic_data(topic, share_map)
            if not data:
                print(f"③ [{i+1}/{len(topics)}] {tid} 无外链，跳过")
                continue

            # 标题
            title_ok = False
            if data.get("feishu_url"):
                doc_title = extract_doc_title(data["feishu_url"])
                if doc_title:
                    data["title"] = doc_title
                    print(f"③ [{i+1}/{len(topics)}] 飞书标题: {doc_title[:35]}")
                    title_ok = True
            if not title_ok and data.get("clean_text"):
                try:
                    sys_p, usr_p = build_title_prompt(data["clean_text"])
                    result = agent_llm_infer(sys_p, usr_p)
                    data["title"] = parse_title_result(result) or f"无标题_{tid[-6:]}"
                    print(f"③ [{i+1}/{len(topics)}] 总结标题: {data['title'][:35]}")
                    title_ok = True
                    time.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    print(f"    标题异常: {e}，设为默认标题")
                    data["title"] = f"无标题_{tid[-6:]}"
                    title_ok = True
            if not title_ok:
                data["title"] = f"无标题_{tid[-6:]}"

            # 标签（仅飞书链接）
            if data.get("feishu_url"):
                try:
                    content = fetch_doc_content(data["feishu_url"])
                    if content:
                        sys_p, usr_p = build_tag_prompt(data["title"], content)
                        tags_result = agent_llm_infer(sys_p, usr_p)
                        data["tags_str"], data["tag_notes"] = tags_to_row(tags_result)
                        print(f"    标签: {data['tags_str'][:30]}")
                        time.sleep(random.uniform(0.5, 1.5))
                    else:
                        data["tags_str"] = ""
                        data["tag_notes"] = "{}"
                except Exception as e:
                    print(f"    标签异常: {e}")
                    data["tags_str"] = ""
                    data["tag_notes"] = "{}"
            else:
                data["tags_str"] = ""
                data["tag_notes"] = "{}"

            to_write.append(row_to_values(data))
            print(f"    ✓ [{i+1}/{len(topics)}] 话题ID={tid}")

        # ④ 写入表格
        if to_write:
            print(f"\n④ 准备写入 {len(to_write)} 条...")
            last_row = get_last_row()
            result = batch_write_rows(to_write, start_row=last_row + 1)
            print(f"    code={result.get('code')}, updatedCells={result.get('data',{}).get('updatedCells')}")
        print(f"\n🎉 测试完成，共入库 {len(to_write)} 条")

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
        print("=" * 50)
        print("验证模式：逐项验证全链路")
        print("=" * 50)

        # ① ZSXQ Token
        print("\n① 验证 ZSXQ Token...")
        assert validate_token(), "❌ ZSXQ Token 验证失败"
        print("✅ ZSXQ Token 正常")

        # ② 拉取1条真实话题
        print("\n② 拉取真实话题数据...")
        topics = fetch_page(GROUP_ID, "digests", 1)
        assert topics, "❌ 无法拉取 topics"
        topic = topics[0]
        print(f"✅ 拉取成功: topic_id={topic['topic_id']}")

        # 预定义变量（某些分支可能不执行）
        doc_title = None
        generated = ""
        tags_str = ""
        tag_notes = "{}"

        # ③ 飞书文档标题获取（有飞书链接的话题）
        print("\n③ 验证飞书文档标题获取...")
        share_map = fetch_share_urls_for_topics(topics, GROUP_ID)
        data = extract_topic_data(topic, share_map)
        assert data, "❌ extract_topic_data 返回空（无外链）"
        doc_title = None
        if data.get("feishu_url"):
            doc_title = extract_doc_title(data["feishu_url"])
            print(f"✅ 飞书文档标题: {doc_title[:50] if doc_title else '(空)'}")
        else:
            print("⚠️ 本条无飞书链接，跳过标题获取测试")

        # ④ Agent 大模型标题生成
        print("\n④ 验证 Agent 标题生成...")
        if data.get("clean_text"):
            sys_p, usr_p = build_title_prompt(data["clean_text"])
            result = agent_llm_infer(sys_p, usr_p)
            generated = parse_title_result(result)
            assert generated, "❌ 标题生成为空"
            print(f"✅ 标题生成成功: {generated[:40]}")
        else:
            print("⚠️ 本条无正文，跳过标题生成测试")

        # ⑤ Agent 大模型标签生成（仅飞书链接话题）
        print("\n⑤ 验证 Agent 标签生成（有飞书链接）...")
        if data.get("feishu_url"):
            content = fetch_doc_content(data["feishu_url"])
            if content:
                title_for_tag = doc_title or data.get("title") or "无标题"
                sys_p, usr_p = build_tag_prompt(title_for_tag, content)
                tags_result = agent_llm_infer(sys_p, usr_p)
                tags_str, tag_notes = tags_to_row(tags_result)
                print(f"✅ 标签生成成功: {tags_str or '(空)'}")
            else:
                print("⚠️ 文档内容为空，跳过标签测试")
        else:
            print("⚠️ 本条无飞书链接，跳过标签测试")

        # ⑥ Feishu 表格写入
        print("\n⑥ 验证 Feishu 表格写入...")
        test_connection()
        print("✅ 表格写入连通性正常")

        # ⑦ 模拟写入一行（verify 用虚拟数据）
        test_data = {
            "feishu_url": data.get("feishu_url", ""),
            "article_url": data.get("article_url", ""),
            "topic_id": data["topic_id"],
            "title": data.get("title") or generated or "验证标题",
            "author": data.get("author", ""),
            "create_time": data.get("create_time", ""),
            "create_time_str": data.get("create_time_str", ""),
            "share_url": data.get("share_url", ""),
            "is_digest": data.get("is_digest", "否"),
            "tags_str": tags_str if data.get("feishu_url") else "",
            "tag_notes": tag_notes if data.get("feishu_url") else "{}",
        }
        row = row_to_values(test_data)
        result = batch_write_rows([row], start_row=get_last_row() + 1)
        assert result.get("code") == 0, f"❌ 表格写入失败: {result}"
        print(f"✅ 模拟写入成功: updatedCells={result.get('data',{}).get('updatedCells')}")

        print("\n" + "=" * 50)
        print("🎉 全链路验证通过！")
        print("=" * 50)

    else:
        print(f"未知阶段: {phase}")
        print("用法: python engine.py [test|phase1|phase2|phase3|verify]")


if __name__ == "__main__":
    main()


def agent_llm_infer(system_prompt: str, user_prompt: str) -> dict:
    """
    占位函数，由 Agent 自身大模型执行推理。
    Agent 将 system_prompt + user_prompt 注入自身大模型，返回 JSON 结果。
    标题生成：tagger.py build_title_prompt()
    标签生成：tagger.py build_tag_prompt()
    """
    raise NotImplementedError("此函数由 Agent 执行时替换实现")

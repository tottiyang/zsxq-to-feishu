# -*- coding: utf-8 -*-
"""
ZSXQ 主页 → 拦截话题列表 API → 获取 topic_id → 提取飞书链接 → 入库多维表格

用法:
    python3 test_group_extract.py [limit]
    python3 test_group_extract.py 5   # 默认抓5个
"""
import json
import subprocess
import sys

GROUP_ID = "15552545485212"   # AI破局俱乐部


# ────────────────────────────────────────────────────────────────
# Step 1: CDP 访问主页，拦截话题列表 API，取 topic_id
# ────────────────────────────────────────────────────────────────
def fetch_topic_ids(limit: int = 5) -> list[dict]:
    """访问 ZSXQ 主页，拦截 /topics/ API，提取 topic_id、标题、作者、发布时间"""
    js_code = f"""
const {{ chromium }} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {{
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    // 复用现有 page（不要 newPage，Chrome CDP 不支持）
    const page = await ctx.newPage();
    if (!page) {{ console.log('ERROR:No page found'); await browser.close(); return; }}

    const topics = [];

    // 拦截 API
    await page.route('**/api.zsxq.com/**', async route => {{
        const url = route.request().url();
        if (!url.includes('/topics')) {{ await route.continue(); return; }}
        if (url.includes('/share_url')) {{ await route.continue(); return; }}
        try {{
            const resp = await route.fetch();
            const body = await resp.json();
            const raw = body.topics || body.resp_data?.topics || [];
            for (const t of raw) {{
                if (topics.length >= {limit}) break;
                const tid = String(t.topic_id || '');
                if (!tid) continue;
                topics.push({{
                    topic_id: tid,
                    title: (t.text || '').slice(0, 80),
                    author: t.author?.name || '',
                    create_time: t.create_time || '',
                }});
            }}
        }} catch(e) {{}}
        await route.continue();
    }});

    // 访问主页
    await page.goto('https://wx.zsxq.com/group/{GROUP_ID}', {{ waitUntil: 'networkidle', timeout: 20000 }});
    await page.waitForTimeout(3000);

    // 访问话题列表页
    if (topics.length < {limit}) {{
        await page.goto('https://wx.zsxq.com/d2g/{GROUP_ID}/topics/overview?count=20&detail_type=1', {{
            waitUntil: 'networkidle', timeout: 20000
        }});
        await page.waitForTimeout(3000);
    }}

    // DOM fallback
    if (topics.length < {limit}) {{
        const domTopics = await page.evaluate(() => {{
            const links = Array.from(document.querySelectorAll('a[href]'));
            const seen = new Set();
            return links
                .filter(a => /\\/(\\d{{15,20}})\\/activity/.test(a.href))
                .map(a => {{
                    const m = a.href.match(/\\/(\\d{{15,20}})\\/activity/);
                    return m ? m[1] : null;
                }})
                .filter(id => id && !seen.has(id) && seen.add(id))
                .slice(0, 20);
        }});
        for (const tid of domTopics) {{
            if (topics.length >= {limit}) break;
            topics.push({{ topic_id: tid, title: '', author: '', create_time: '' }});
        }}
    }}

    // 去重
    const seen = new Set();
    const unique = topics.filter(function(t) {{
        if (seen.has(t['topic_id'])) return false;
        seen.add(t['topic_id']);
        return true;
    }});

    console.log('RESULT:' + JSON.stringify(unique.slice(0, {limit})));
    await browser.close();
}})();
"""
    result = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, timeout=60)
    out = result.stdout.strip()
    if result.returncode != 0:
        return {"success": False, "error": result.stderr}
    if out.startswith("RESULT:"):
        raw = out[7:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "error": f"JSON解析失败: {raw[:200]}"}
    return {"success": False, "error": f"未知输出: {result.stdout[:200]}"}


# ────────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"[Step 1] 访问 AI破局俱乐部 主页，拦截话题列表，抓取 {limit} 个卡片...")

    topics_result = fetch_topic_ids(limit)
    if isinstance(topics_result, dict) and not topics_result.get("success"):
        print(f"❌ Step 1 失败: {topics_result.get('error', '未知错误')}")
        sys.exit(1)

    topics = topics_result if isinstance(topics_result, list) else []
    print(f"  ✅ 获取到 {len(topics)} 个话题:")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. [{t['topic_id']}] {t.get('title', '')[:50]}")

    print(f"\n[Step 2] 逐个提取飞书链接...")
    import os as _os
    _os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
    from extractor_share import extract_share_url, extract_full

    records = []
    for i, topic in enumerate(topics, 1):
        tid = topic["topic_id"]
        print(f"\n  [{i}/{len(topics)}] topic_id={tid}")

        # 方式A: 用 topic_id 直接获取分享链接
        share_result = extract_share_url(tid, group_id=GROUP_ID)
        if share_result.get("success") is False:
            print(f"    ⚠️  extract_share_url 失败: {share_result.get('error', '')[:80]}")
            share_url = None
        else:
            share_url = share_result.get("share_url") or None
            print(f"    ✅ 分享链接: {share_url}")

        if not share_url:
            print(f"    ⏭ 跳过（无分享链接）")
            continue

        # 方式B: 完整提取（含飞书链接）
        print(f"    正在提取飞书链接...")
        full_result = extract_full(share_url)
        if full_result.get("success") is False:
            print(f"    ⚠️  extract_full 失败: {full_result.get('error', '')[:80]}")
            continue

        feishu_links = full_result.get("feishu_links") or []
        if feishu_links:
            print(f"    ✅ 飞书链接: {feishu_links[0]}")
            records.append({
                "share_url": share_url,
                "topic_id": tid,
                "title": full_result.get("title") or topic.get("title", ""),
                "author": full_result.get("author") or topic.get("author", ""),
                "date_str": full_result.get("date_str") or "",
                "feishu_link": feishu_links[0],
            })
        else:
            print(f"    ⚠️  无飞书链接")

    print(f"\n[Step 3] 共获取 {len(records)} 条可入库记录:")
    for r in records:
        print(f"  - {r['title'][:40]} | {r['feishu_link']}")

    if records:
        print(f"\n下一步：调用 feishu_bitable_create_record 写入多维表格（app_token=XpGMbvYwsaNvZMsBzZ3cN1DRnOc, table_id=tblt1Lm7ipCFuyXi）")
        print(f"字段: topic_id / title / author / date_str / feishu_link")

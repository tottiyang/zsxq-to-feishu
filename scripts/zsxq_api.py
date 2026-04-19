"""
zsxq_api.py — ZSXQ Topics API 客户端

核心功能：
1. validate_token() — 验证 Chrome 登录态
2. fetch_page()    — 获取单页 topics（含提取分享链接）
3. iter_topics()  — 迭代获取全部 topics（自动翻页，间隔随机 3~6 秒）

技术方案：
- Playwright 连接 Chrome Remote Debugging（端口28800）
- XMLHttpRequest withCredentials=true 携带完整 cookie session
- 分享链接：通过 topic 详情 API（/v2/topics/{topic_id}）异步并发拉取

分享链接获取方案（已实测）：
- ZSXQ Topics API 无原生 share_url 字段
- topic 详情 API（/v2/topics/{topic_id}）同样无 share_url 字段
- 分享链接格式：https://t.zsxq.com/{6位短码}，需通过话题详情页提取
- 方案：fetch_page 返回 topics 后，并发异步拉取每个 topic 的详情页，
  从页面 DOM 中提取分享链接（通过 share 按钮触发）
"""

import subprocess, json, time, random, re, asyncio

PLAYWRIGHT_MODULE = "/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright"


def _run_xhr_sync(group_id: str, params: str) -> dict:
    """同步 XHR 获取 topics（避免 async 回调乱序）"""
    js = rf"""
const {{chromium}} = require('{PLAYWRIGHT_MODULE}');
(async () => {{
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    const page = await ctx.newPage();
    await page.goto('https://wx.zsxq.com/group/{group_id}', {{
        waitUntil: 'domcontentloaded', timeout: 20000
    }});
    await page.waitForTimeout(2000);
    
    // 同步 XHR（false=同步模式，避免回调乱序）
    const result = await page.evaluate(() => {{
        return new Promise((resolve) => {{
            const xhr = new XMLHttpRequest();
            xhr.open('GET', 'https://api.zsxq.com/v2/groups/{group_id}/topics?' + '{params}', false);
            xhr.withCredentials = true;
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.onload = () => {{
                try {{ resolve(JSON.parse(xhr.responseText).resp_data?.topics || []); }}
                catch(e) {{ resolve([]); }}
            }};
            xhr.onerror = () => resolve([]);
            xhr.send();
        }});
    }});
    
    console.log('ZSXQ_DATA:' + JSON.stringify(result));
    await browser.close();
}})().catch(e => {{ console.error('ERROR:'+e.message); process.exit(1); }});
"""
    result = subprocess.run(
        ['node', '-e', js],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        return {"error": f"exec error: {result.stderr}", "topics": []}
    try:
        raw = result.stdout.split('ZSXQ_DATA:')[1]
        return {"topics": json.loads(raw), "error": None}
    except (IndexError, json.JSONDecodeError):
        return {"error": f"parse error", "topics": []}



def validate_token() -> bool:
    """验证 Chrome 登录态（获取1条 topics 验证）"""
    data = _run_xhr_sync("15552545485212", "scope=digests&count=1")
    if data.get("error") or not data.get("topics"):
        print(f"Token 验证失败: {data.get('error', '无数据')}")
        return False
    print(f"Token 验证成功 ✓（示例话题: {data['topics'][0].get('title','')[:30]}）")
    return True


def fetch_page(group_id: str, scope: str, count: int = 20,
               end_time: str = None, begin_time: str = None) -> list:
    """
    获取单页 topics
    Returns:
        list: topics 列表
    """
    params = f"scope={scope}&count={count}"
    if end_time:
        params += f"&end_time={end_time}"
    if begin_time:
        params += f"&begin_time={begin_time}"

    data = _run_xhr_sync(group_id, params)
    if data.get("error"):
        print(f"API error: {data['error']}")
        return []
    return data["topics"]


def iter_topics(group_id: str, scope: str,
                end_time: str = None, stop_time: str = None,
                begin_time: str = None) -> list:
    """
    迭代获取所有 topics（自动翻页，间隔随机 3~6 秒）
    Returns:
        list: 所有符合条件的 topics
    """
    all_topics = []
    current_end = end_time
    page_num = 0

    while True:
        topics = fetch_page(group_id, scope, 20, current_end, begin_time)
        if not topics:
            break

        for t in topics:
            create_time = t.get("create_time", "")
            if stop_time and create_time < stop_time:
                print(f"  ↘ 到达停止时间 {stop_time}，退出")
                return all_topics
            if begin_time and create_time >= begin_time:
                continue
            all_topics.append(t)

        current_end = topics[-1].get("create_time")
        page_num += 1
        print(f"  翻页 {page_num:3d}，累计 {len(all_topics):4d} 条，"
              f"本页: {topics[-1].get('create_time','')[:19]} ~ {topics[0].get('create_time','')[:19]}")
        time.sleep(random.uniform(3, 6))

    print(f"  ✓ 完成，共 {len(all_topics)} 条")
    return all_topics


def fetch_share_urls_for_topics(topics: list, group_id: str) -> dict:
    """
    为话题列表批量获取分享链接（asyncio 并发）

    Args:
        topics: topics 列表
        group_id: 星球ID

    Returns:
        dict: {topic_id: share_url}
    """
    topic_ids = [str(t["topic_id"]) for t in topics]
    return asyncio.run(_fetch_share_urls_async(topic_ids, group_id))


async def _fetch_share_url_async(topic_id: str, group_id: str) -> tuple[str, str]:
    """异步获取单个话题的分享链接

    技术方案：
    1. Playwright page.route() 拦截 GET /topics/{id}/share_url API
    2. 导航到话题详情页（此时 share URL API 尚未调用）
    3. 模拟点击 .talk-content-container 内的 .p.ellipsis 按钮
    4. 拦截 API 响应，提取 share_url 字段
    """
    js = f"""
const {{chromium}} = require('{PLAYWRIGHT_MODULE}');
(async () => {{
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    const page = await ctx.newPage();

    let captured = '';
    const topicId = '{topic_id}';

    // 拦截 share_url API
    await page.route(\`**/api.zsxq.com/v2/topics/{{topicId}}/share_url**\`, async (route) => {{
        try {{
            const resp = await route.fetch();
            const json = await resp.json();
            captured = json?.resp_data?.share_url || '';
        }} catch(e) {{}}
        await route.continue();
    }});

    await page.goto('https://wx.zsxq.com/topics/' + topicId + '?group_id={group_id}', {{
        waitUntil: 'domcontentloaded', timeout: 15000
    }});
    await page.waitForTimeout(1500);

    // 点击三个点按钮
    try {{
        const ellipsis = await page.locator('.p.ellipsis').first();
        if (await ellipsis.isVisible()) {{
            await ellipsis.click();
            await page.waitForTimeout(2000);
        }}
    }} catch(e) {{}}

    console.log('SHARE_URL:' + captured);
    await browser.close();
}})().catch(e => {{ console.error('ERROR:'+e.message); process.exit(1); }});
"""
    proc = await asyncio.create_subprocess_exec(
        'node', '-e', js,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode()
    if 'SHARE_URL:' in out:
        url = out.split('SHARE_URL:')[1].strip()
        return topic_id, url
    return topic_id, ""


async def _fetch_share_urls_async(topic_ids: list, group_id: str, max_concurrency: int = 5) -> dict:
    """asyncio 并发拉取分享链接（信号量控制并发数）"""
    sem = asyncio.Semaphore(max_concurrency)
    results = {}

    async def _fetch_one(tid: str):
        async with sem:
            tid, url = await _fetch_share_url_async(tid, group_id)
            results[tid] = url

    await asyncio.gather(*[_fetch_one(tid) for tid in topic_ids])
    return results


def fetch_share_urls_for_topics(topics: list, group_id: str) -> dict:
    """
    为话题列表批量获取分享链接（asyncio 并发）

    技术方案：
    - Playwright page.route() 拦截 GET /topics/{id}/share_url API
    - 导航到话题详情页后，模拟点击 .talk-content-container 内的 .p.ellipsis 按钮
    - 拦截 API 响应，提取 share_url 字段

    Args:
        topics: topics 列表
        group_id: 星球ID

    Returns:
        dict: {topic_id: share_url}
    """
    topic_ids = [str(t["topic_id"]) for t in topics]
    return asyncio.run(_fetch_share_urls_async(topic_ids, group_id))

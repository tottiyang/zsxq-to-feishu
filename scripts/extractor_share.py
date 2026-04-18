# -*- coding: utf-8 -*-
"""
ZSXQ 分享链接提取器（v2.0·API 拦截方案）

核心能力：
1. 点击话题卡片三个点 → 拦截 GET /v2/topics/{topic_id}/share_url 响应
2. 获取 topic_id 和分享链接
3. 展开话题全文，提取飞书文档链接

技术方案：Playwright CDP 模式连接本地 Chrome（localhost:28800）
"""

import json
import subprocess
import sys
import time


def extract_share_url(topic_id: str, group_id: str = "15552545485212") -> dict:
    """
    通用方法：通过 topic_id 调用 ZSXQ API 获取分享链接

    参数:
        topic_id: 话题 ID（约17位数字，如 "45544844845444248"）
        group_id: 星球 ID（默认 AI破局俱乐部 15552545485212）

    返回:
        {"share_url": "https://t.zsxq.com/xxxx", "topic_id": "...", "text": "话题标题"}
    """
    js_code = f"""
const {{ chromium }} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {{
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    const page = ctx.pages()[0];

    // 注入拦截器：捕获 api.zsxq.com 的 share_url 响应
    let shareResult = null;
    await page.route('**/api.zsxq.com/**', async route => {{
        const req = route.request();
        const url = req.url();
        if (url.includes('/topics/') && url.includes('/share_url')) {{
            try {{
                const resp = await route.fetch();
                const body = await resp.json();
                if (body.topic) {{
                    shareResult = {{
                        share_url: body.topic.share_url || '',
                        topic_id: body.topic.topic_id || '',
                        text: body.topic.text || ''
                    }};
                    console.log('SHARE_RESULT:' + JSON.stringify(shareResult));
                }}
            }} catch(e) {{
                console.log('INTERCEPT_ERROR:' + e.message);
            }}
        }}
        await route.continue();
    }});

    // 导航到话题详情页（自动触发 share_url API）
    await page.goto('https://wx.zsxq.com/dms/{group_id}/{topic_id}/activity/messages', {{
        waitUntil: 'networkidle', timeout: 20000
    }});
    await page.waitForTimeout(3000);

    if (shareResult) {{
        console.log('RESULT:' + JSON.stringify(shareResult));
    }} else {{
        console.log('ERROR:未获取到分享链接，请检查 topic_id 和登录态');
    }}

    await browser.close();
}})();
"""
    result = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True, text=True, timeout=60
    )
    out = result.stdout.strip()
    if out.startswith("RESULT:"):
        raw = out[7:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "error": f"JSON解析失败: {raw[:200]}"}
    elif "ERROR:" in out:
        return {"success": False, "error": out}
    else:
        return {"success": False, "error": f"未知输出: {out[:200]}"}


def extract_full(topic_share_url: str) -> dict:
    """
    从话题分享链接完整提取：分享链接 + 元数据 + 飞书链接

    流程：
    1. Playwright 导航到分享链接（自动跳转话题详情页）
    2. 拦截 share_url API 响应
    3. 点击「展开全部」
    4. 提取飞书链接 + 元数据
    """
    js_code = f"""
const {{ chromium }} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {{
    const browser = await chromium.connectOverCDP('http://localhost:28800');
    const ctx = browser.contexts()[0];
    const page = ctx.pages()[0];

    // 注入 share_url 拦截器
    let shareResult = null;
    await page.route('**/api.zsxq.com/**', async route => {{
        const req = route.request();
        const url = req.url();
        if (url.includes('/topics/') && url.includes('/share_url')) {{
            try {{
                const resp = await route.fetch();
                const body = await resp.json();
                if (body.topic) {{
                    shareResult = {{
                        share_url: body.topic.share_url || '',
                        topic_id: body.topic.topic_id || '',
                        title: body.topic.text || ''
                    }};
                }}
            }} catch(e) {{}}
        }}
        await route.continue();
    }});

    // Step 1: 导航到分享链接
    await page.goto('{topic_share_url}', {{ waitUntil: 'networkidle', timeout: 20000 }});
    await page.waitForTimeout(4000);

    // Step 2: 获取元数据（作者/时间/标题）
    const meta = await page.evaluate(() => {{
        const body = document.body.innerText;
        let author = null;
        let dateStr = null;
        const title = (document.title || '').replace(' -知识星球', '').trim();

        // 作者：从正文匹配 "返回 {星球名} {作者} {时间}"
        const authorMatch = body.match(/返回\\s+\\S+\\s+([^\\s（(]{1,10}?)\\s+\\d{{4}}-\\d{{2}}-\\d{{2}}/);
        if (authorMatch) author = authorMatch[1];

        // 时间
        const timeMatch = body.match(/([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\\s+[0-9]{{2}}:[0-9]{{2}})/);
        if (timeMatch) dateStr = timeMatch[1];

        return {{ title, author, dateStr, url: window.location.href }};
    }});

    // Step 3: 点击"展开全部"
    let expanded = false;
    try {{
        const btn = page.locator('text="展开全部"').first();
        if (await btn.count() > 0) {{
            await btn.click({{ timeout: 3000 }});
            await page.waitForTimeout(3000);
            expanded = true;
        }}
    }} catch(e) {{}}

    // Step 4: 提取飞书链接
    const feishuLinks = await page.evaluate(() => {{
        const seen = new Set();
        const links = [];
        for (const a of document.querySelectorAll('a[href]')) {{
            const href = a.href || '';
            if (/feishu\\.cn/i.test(href)) {{
                const clean = href.replace(/\\?.*$/, '');
                if (!seen.has(clean)) {{
                    seen.add(clean);
                    links.push(clean);
                }}
            }}
        }}
        return links;
    }});

    const result = {{
        success: true,
        topic_id: shareResult?.topic_id || '',
        share_url: shareResult?.share_url || meta.url,
        title: meta.title || shareResult?.title || '',
        author: meta.author || '',
        date_str: meta.dateStr || '',
        feishu_links: feishuLinks,
        expanded: expanded
    }};

    console.log('RESULT:' + JSON.stringify(result));
    await browser.close();
}})();
"""
    result = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True, text=True, timeout=60
    )
    out = result.stdout.strip()
    if out.startswith("RESULT:"):
        raw = out[7:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "error": f"JSON解析失败: {raw[:200]}"}
    elif "ERROR:" in out:
        return {"success": False, "error": out}
    else:
        return {"success": False, "error": f"未知输出: {out[:200]}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 extractor_share.py full <分享链接>    # 完整提取（链接+元数据+飞书链接）")
        print("  python3 extractor_share.py id <topic_id>     # 仅获取分享链接")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "full":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://t.zsxq.com/6L4Ry"
        print(f"正在完整提取: {url}")
        result = extract_full(url)
    elif cmd == "id":
        tid = sys.argv[2] if len(sys.argv) > 2 else input("输入 topic_id: ")
        print(f"正在获取分享链接: {tid}")
        result = extract_share_url(tid)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))

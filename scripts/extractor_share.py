# -*- coding: utf-8 -*-
"""
ZSXQ 分享链接提取器（新版·完整流程）

从 ZSXQ 分享链接提取：
1. ZSXQ 话题详情永久链接（从 window.location.href 获取）
2. 话题元数据（作者/时间/标题）
3. 飞书文档链接（从展开内容中提取）

技术方案：Playwright CDP 模式连接本地 Chrome，复用登录态
CDP 地址: http://localhost:28800
"""

import json
import subprocess
import sys
import time


def extract_from_share(share_url: str) -> dict:
    """
    从 ZSXQ 分享链接提取完整数据

    参数:
        share_url: ZSXQ 分享链接，如 https://t.zsxq.com/6L4Ry

    返回:
        {
            "success": true,
            "zsxq_url": "https://wx.zsxq.com/dms/...",  # ← 话题永久链接
            "title": "话题标题",
            "author": "作者名",
            "date_str": "2026-04-09 14:38",
            "feishu_links": ["https://my.feishu.cn/wiki/xxx", ...]
        }

    踩坑记录:
        - 直接用 user token → user token 无 ZSXQ 登录态，必须走 CDP
        - "展开全部"按钮点击 → 展开话题正文 + 评论中的飞书链接
        - window.location.href 在话题详情页直接获取话题永久链接
    """
    js_code = f"""
const {{ chromium }} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {{
  const browser = await chromium.connectOverCDP('http://localhost:28800');
  const ctx = browser.contexts()[0];
  const page = ctx.pages()[0];

  // 注入 history 拦截器，捕获 Angular SPA 的 pushState 导航
  await page.evaluate(() => {{
    window.__navLog = [];
    window.__pushState = history.pushState;
    history.pushState = function(s, t, u) {{
      window.__navLog.push({{ type: 'pushState', url: u }});
      return window.__pushState.apply(history, arguments);
    }};
    window.__replaceState = history.replaceState;
    history.replaceState = function(s, t, u) {{
      window.__navLog.push({{ type: 'replaceState', url: u }});
      return window.__replaceState.apply(history, arguments);
    }};
  }});

  try {{
    // Step 1: 导航到分享链接（会自动跳转到话题详情页）
    await page.goto('{share_url}', {{ waitUntil: 'networkidle', timeout: 20000 }});
    await page.waitForTimeout(3000);

    const urlAfterNav = page.url();
    console.log('导航后URL: ' + urlAfterNav);

    // Step 2: 从 window.location.href 获取话题永久链接
    // 格式: https://wx.zsxq.com/dms/{topic_id}/activity/messages
    let zsxqUrl = urlAfterNav;
    if (!zsxqUrl.includes('/dms/') && !zsxqUrl.includes('/d2g/')) {{
      // 可能还在重定向，等一下
      await page.waitForTimeout(5000);
      zsxqUrl = page.url();
    }}

    // Step 3: 提取话题元数据
    const meta = await page.evaluate(() => {{
      const body = document.body.innerText;

      // 标题：从页面 title 提取，移除 " -知识星球" 后缀
      let title = (document.title || '').replace(' -知识星球', '').trim();

      // 作者：从正文匹配 "返回 {星球名} {作者名} {时间}"
      // 格式如: "返回 AI破局俱乐部 行者 2026-04-09 14:38"
      // 作者在时间前面，不含括号和空格后缀
      let author = null;
      const authorMatch = body.match(/返回\\s+[^\\s群]\\S+\\s+([^\\s（(]{{1,10}})\\s+\\d{{4}}-\\d{{2}}-\\d{{2}}/);
      if (authorMatch) {{
        author = authorMatch[1];
      }} else {{
        // Fallback: 找 "名字" 后跟日期时间
        const altMatch = body.match(/([^\s（(]{{2,10}})\\s+\\d{{4}}-\\d{{2}}-\\d{{2}}\\s+\\d{{2}}:\\d{{2}}/);
        if (altMatch) author = altMatch[1];
      }}

      // 发布时间
      let dateStr = null;
      const timeMatch = body.match(/([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\\s+[0-9]{{2}}:[0-9]{{2}})/);
      if (timeMatch) dateStr = timeMatch[1];

      return {{ title, author, dateStr, url: window.location.href }};
    }});

    // Step 4: 展开话题（如果有"展开全部"按钮）
    let expanded = false;
    let expandBtn = null;
    try {{
      // 查找"展开全部"按钮
      expandBtn = page.locator('text="展开全部"').first();
      const count = await page.locator('text="展开全部"').count();
      if (count > 0) {{
        await expandBtn.click({{ timeout: 5000 }});
        await page.waitForTimeout(3000);
        expanded = true;
        console.log('已点击展开全部');
      }}
    }} catch(e) {{
      console.log('展开全部未找到: ' + e.message);
    }}

    // Step 5: 提取飞书链接
    const feishuLinks = await page.evaluate(() => {{
      const anchors = Array.from(document.querySelectorAll('a[href]'));
      const seen = new Set();
      const links = [];
      for (const a of anchors) {{
        const href = a.href || '';
        if (/feishu\\.cn/i.test(href)) {{
          // 去掉 ?from=copylink 等参数
          const clean = href.replace(/\\?.*$/, '');
          if (!seen.has(clean)) {{
            seen.add(clean);
            links.push(clean);
          }}
        }}
      }}
      return links;
    }});

    // 最终确认 URL（可能经过 pushState 导航）
    const finalUrl = await page.evaluate(() => window.location.href);
    const pushUrls = await page.evaluate(() => JSON.stringify(window.__navLog || []));

    const result = {{
      success: true,
      zsxq_url: finalUrl,
      title: meta.title,
      author: meta.author,
      date_str: meta.dateStr,
      feishu_links: feishuLinks,
      expanded: expanded,
      nav_log: JSON.parse(pushUrls || '[]')
    }};

    console.log('RESULT:' + JSON.stringify(result));
  }} catch (err) {{
    console.log('ERROR:' + err.message);
  }} finally {{
    await browser.close();
  }}
}})();
"""

    result = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True,
        text=True,
        timeout=60,
    )

    out = result.stdout.strip()
    err = result.stderr.strip()

    if err:
        print(f"[stderr] {err[:200]}")

    if out.startswith("RESULT:"):
        raw = out[7:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "error": f"JSON解析失败: {raw[:200]}"}
    elif out.startswith("ERROR:"):
        return {"success": False, "error": out[6:]}
    else:
        return {"success": False, "error": f"未知输出: {out[:200]}"}


def extract_feishu_token(feishu_url: str) -> str:
    """从飞书 URL 提取 token"""
    import re
    match = re.search(r'/([A-Za-z0-9]+)(?:\?|$)', feishu_url)
    return match.group(1) if match else ""


if __name__ == "__main__":
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://t.zsxq.com/6L4Ry"
    print(f"正在提取: {test_url}")
    result = extract_from_share(test_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

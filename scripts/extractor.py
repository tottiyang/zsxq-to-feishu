# -*- coding: utf-8 -*-
"""
ZSXQ 分享链接数据提取器
从知识星球分享链接提取：飞书文档链接 + 话题元数据

技术方案：Playwright 连接本地 Chrome CDP，复用登录态
CDP 地址: http://localhost:28800
"""

import json
import subprocess
import sys


def extract_zsxq_share(share_url: str) -> dict:
    """
    从 ZSXQ 分享链接提取元数据

    参数:
        share_url: ZSXQ 分享链接，如 https://t.zsxq.com/6L4Ry

    返回:
        {
            "feishu_link": "https://my.feishu.cn/wiki/...",
            "title": "话题标题",
            "author": "作者名",
            "date_str": "2026-04-09 14:38",
            "zsxq_url": "实际访问的完整URL"
        }

    踩坑记录:
        - ZSXQ 需要登录态，普通无头浏览器会跳转到登录页
        - 解决方案：Playwright CDP 模式连接本地 Chrome，复用登录 Cookie
    """
    js_code = f"""
const {{ chromium }} = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {{
  const browser = await chromium.connectOverCDP('http://localhost:28800');
  const context = browser.contexts()[0];
  const page = context.pages()[0];

  try {{
    await page.goto('{share_url}', {{ waitUntil: 'networkidle', timeout: 20000 }});
    await page.waitForTimeout(2000);

    // 提取飞书文档链接（从 DOM 中的链接元素）
    const feishuData = await page.evaluate(() => {{
      const links = Array.from(document.querySelectorAll('a[href]'));
      const feishu = links.find(a =>
        a.href.includes('feishu.cn/wiki') || a.href.includes('feishu.cn/docx')
      );
      return {{
        feishuLink: feishu ? feishu.href : null,
        feishuText: feishu ? feishu.innerText : null
      }};
    }});

    // 提取话题元数据（从页面 DOM）
    const meta = await page.evaluate(() => {{
      const body = document.body.innerText;

      // 标题：从页面 title 提取，移除 " -知识星球" 后缀
      let title = document.title.replace(' -知识星球', '').trim();

      // 作者：从正文匹配 "返回 {星球名} {作者名} {时间}"
      // 格式如: "返回 AI破局俱乐部 行者 2026-04-09 14:38"
      const authorMatch = body.match(/返回\\s+[^\\s]+\\s+([^\\s（(]{{1,10}})/);
      const author = authorMatch ? authorMatch[1] : null;

      // 发布时间：从正文匹配 "YYYY-MM-DD HH:mm"
      const timeMatch = body.match(/([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\\s+[0-9]{{2}}:[0-9]{{2}})/);
      const dateStr = timeMatch ? timeMatch[1] : null;

      return {{ title, author, dateStr, url: document.URL }};
    }});

    const result = {{
      success: true,
      feishu_link: feishuData.feishuLink,
      title: meta.title,
      author: meta.author,
      date_str: meta.dateStr,
      zsxq_url: meta.url
    }};

    console.log(JSON.stringify(result));
  }} catch (err) {{
    console.log(JSON.stringify({{ success: false, error: err.message }}));
  }} finally {{
    await browser.close();
  }}
}})();
"""

    result = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()}

    try:
        data = json.loads(result.stdout.strip())
        return data
    except json.JSONDecodeError:
        return {"success": False, "error": f"JSON解析失败: {result.stdout[:200]}"}


def extract_feishu_token(feishu_url: str) -> str:
    """
    从飞书文档 URL 提取 token

    示例:
        url = "https://my.feishu.cn/wiki/SxRzwvSSWiTa7Kk57gKcQJbGnqg"
        token = extract_feishu_token(url)  # "SxRzwvSSWiTa7Kk57gKcQJbGnqg"
    """
    import re
    match = re.search(r'/([A-Za-z0-9]+)(?:\?|$)', feishu_url)
    if match:
        return match.group(1)
    return ""


if __name__ == "__main__":
    # 测试
    test_url = "https://t.zsxq.com/6L4Ry"
    if len(sys.argv) > 1:
        test_url = sys.argv[1]

    print(f"正在提取: {test_url}")
    result = extract_zsxq_share(test_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

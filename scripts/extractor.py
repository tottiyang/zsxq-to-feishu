# -*- coding: utf-8 -*-
"""
ZSXQ 分享链接数据提取器
从知识星球分享链接提取：飞书文档链接 + 话题元数据 + ZSXQ topic_id

技术方案：Playwright 连接本地 Chrome CDP，复用登录态
CDP 地址: http://localhost:28800
"""

import json
import re
import subprocess
import sys


def extract_zsxq_share(share_url: str) -> dict:
    """
    从 ZSXQ 分享链接提取元数据

    参数:
        share_url: ZSXQ 分享链接，如 https://t.zsxq.com/6L4Ry

    返回:
        {
            "success": True,
            "feishu_link": "https://my.feishu.cn/wiki/...",
            "zsxq_topic_id": "45544844845444248",   # ZSXQ topic_id，约17位数字
            "title": "话题标题",
            "author": "作者名",
            "date_str": "2026-04-09 14:38",
            "zsxq_url": "实际访问的完整URL"
        }

    踩坑记录:
        - ZSXQ 需要登录态，普通无头浏览器会跳转到登录页
        - 解决方案：Playwright CDP 模式连接本地 Chrome，复用登录 Cookie
        - ❌ 不能在 Python f-string 里写 JS 代码：{{ 在 f-string 里变成 {，
          JS destructuring const { x } 需要 {，但 { 会被 Python 当插值表达式
        - ✅ 正确方案：用字符串拼接，把 share_url 用 %s 占位，JS 部分完整保留
    """
    # 用 %s 占位 share_url，JS 代码完整保留（无任何转义问题）
    js_code = """
const { chromium } = require('/Users/totti/.npm/_npx/705bc6b22212b352/node_modules/playwright');

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:28800');
  const context = browser.contexts()[0];
  const page = context.pages()[0];

  try {
    await page.goto('%s', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(2000);

    // 提取飞书文档链接（从 DOM 中的链接元素）
    const feishuData = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a[href]'));
      const feishu = links.find(a =>
        a.href.includes('feishu.cn/wiki') || a.href.includes('feishu.cn/docx')
      );
      return {
        feishuLink: feishu ? feishu.href : null,
        feishuText: feishu ? feishu.innerText : null
      };
    });

    // 提取话题元数据（从页面 DOM）
    const meta = await page.evaluate(() => {
      const body = document.body.innerText;

      // 标题：移除末尾的 " -知识星球" 及各种变体
      let title = document.title.replace(/\s*[-−]\s*知识星球\s*$/, '').trim();

      // 作者：从正文按行提取
      // 结构：第N行 "返回 {星球名}" → 第N+1行 "{作者名}" → 第N+2行 "{日期}"
      const lines = body.split('\\n');
      let author = null;
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        // 找 "返回 {星球名}" 所在行
        if (/^返回\s+/.test(line)) {
          // 作者在下一行
          const next = lines[i + 1] ? lines[i + 1].trim() : '';
          // 清理回复标记，取纯名字
          author = next.replace(/\s*回复\s*.*$/, '').trim();
          break;
        }
      }

      // 发布时间：找 "返回 {星球}" 行的下下行（第N+2行）
      let dateStr = null;
      for (let i = 0; i < lines.length - 2; i++) {
        const line = lines[i].trim();
        if (/^返回\s+/.test(line)) {
          const dateLine = lines[i + 2] ? lines[i + 2].trim() : '';
          const dateMatch = dateLine.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/);
          dateStr = dateMatch ? dateMatch[1] : null;
          break;
        }
      }

      return { title, author, dateStr, url: document.URL };
    });

    const result = {
      success: true,
      feishu_link: feishuData.feishuLink,
      title: meta.title,
      author: meta.author,
      date_str: meta.dateStr,
      zsxq_url: meta.url
    };

    console.log(JSON.stringify(result));
  } catch (err) {
    console.log(JSON.stringify({ success: false, error: err.message }));
  } finally {
    await browser.close();
  }
})();
""" % share_url

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
    except json.JSONDecodeError:
        return {"success": False, "error": "JSON解析失败: " + result.stdout[:200]}

    if not data.get("success"):
        return {"success": False, "error": data.get("error", "未知错误")}

    # ── ZSXQ topic_id 提取（Python 端，从 URL 解析）────────────
    zsxq_url = data.get("zsxq_url", "")
    data["zsxq_topic_id"] = _parse_topic_id(zsxq_url)
    return data


def _parse_topic_id(zsxq_url: str) -> str:
    """
    从 ZSXQ URL 解析 topic_id

    格式:
      https://wx.zsxq.com/dms/{group_id}/{topic_id}/activity/messages
      https://wx.zsxq.com/d2g/{group_id}/{topic_id}/activity
    示例:
      https://wx.zsxq.com/dms/15552545485212/8855218548218/activity/messages
      → topic_id = 8855218548218
    """
    if not zsxq_url:
        return ""
    # 按优先级尝试不同 pattern
    for pattern in [
        r'/group/\d+/topic/(\d+)',       # /group/{gid}/topic/{tid}  ← 实际URL格式
        r'/dms/\d+/(\d+)/activity',     # /dms/{gid}/{tid}/activity
        r'/d2g/\d+/(\d+)',              # /d2g/{gid}/{tid}
        r'/(\d{15,20})/activity',        # fallback: 15-20位数字段
    ]:
        m = re.search(pattern, zsxq_url)
        if m:
            return m.group(1)
    return ""


def extract_feishu_token(feishu_url: str) -> str:
    """
    从飞书文档 URL 提取 token

    示例:
        url = "https://my.feishu.cn/wiki/SxRzwvSSWiTa7Kk57gKcQJbGnqg"
        token = extract_feishu_token(url)  # "SxRzwvSSWiTa7Kk57gKcQJbGnqg"
    """
    match = re.search(r'/([A-Za-z0-9]+)(?:\?|$)', feishu_url)
    return match.group(1) if match else ""


if __name__ == "__main__":
    test_url = "https://t.zsxq.com/6L4Ry"
    if len(sys.argv) > 1:
        test_url = sys.argv[1]

    print("正在提取: " + test_url)
    result = extract_zsxq_share(test_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

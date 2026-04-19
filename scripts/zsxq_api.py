"""
zsxq_api.py — ZSXQ Topics API 客户端（已验证 ✅ 2026-04-19）

核心功能：
1. validate_token()     — 验证 ZSXQ Token 是否有效
2. fetch_page()        — 获取单页 topics
3. iter_topics()       — 迭代翻页获取全部 topics（随机 3~6 秒间隔）
4. fetch_share_urls()  — 批量获取分享链接（逐条限速 1~2 秒）

技术方案：
- 直接 HTTP 请求（urllib）带 Cookie，不依赖 Chrome CDP 翻页
  Header: Cookie: zsxq_access_token=<TOKEN>
- 分享链接：同样直接 HTTP GET，带 Cookie
  GET https://api.zsxq.com/v2/topics/{topic_id}/share_url
  成功: {"succeeded":true,"resp_data":{"share_url":"https://t.zsxq.com/xxx"}}
  失败: {"succeeded":false,"error":"主题不存在或已被删除"}
"""

import http.client, json, ssl, time, random
from config import GROUP_ID, ZSXQ_TOKEN, CHROME_DEBUG_PORT, TOPICS_FETCH_INTERVAL, SHARE_URL_INTERVAL

_ctx = ssl.create_default_context()

def _api_headers(extra: dict = None) -> dict:
    h = {
        "Cookie": f"zsxq_access_token={ZSXQ_TOKEN}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://wx.zsxq.com/",
    }
    if extra:
        h.update(extra)
    return h


# ─────────── Token 验证 ───────────

def validate_token() -> bool:
    """验证 ZSXQ Token 是否有效（拉取1条 topics 验证）"""
    topics = fetch_page(GROUP_ID, "digests", count=1)
    if not topics:
        print("Token 验证失败：无数据返回")
        return False
    t = topics[0]
    print(f"Token 验证成功 ✓ 示例话题: {t.get('title','')[:40]}")
    return True


# ─────────── 单页获取 ───────────

def fetch_page(group_id: str, scope: str, count: int = 20,
               end_time: str = None, begin_time: str = None) -> list:
    """
    获取单页 topics
    Returns:
        list: topics 列表（每条含 topic_id/type/create_time/user/talk 等）
    """
    params = f"scope={scope}&count={count}"
    if end_time:
        params += f"&end_time={end_time}"
    if begin_time:
        params += f"&begin_time={begin_time}"

    conn = http.client.HTTPSConnection("api.zsxq.com", context=_ctx, timeout=15)
    try:
        conn.request("GET", f"/v2/groups/{group_id}/topics?{params}",
                     headers=_api_headers())
        resp = conn.getresponse()
        body = resp.read()
        d = json.loads(body)
        if not d.get("succeeded"):
            err = d.get("error", "?")
            print(f"API 错误: {err}")
            return []
        rd = d.get("resp_data", {})
        return rd.get("topics", []) if isinstance(rd, dict) else []
    except Exception as e:
        print(f"fetch_page 异常: {e}")
        return []
    finally:
        conn.close()


# ─────────── 迭代翻页 ───────────

def iter_topics(group_id: str, scope: str,
                end_time: str = None, stop_time: str = None,
                begin_time: str = None,
                max_pages: int = None) -> list:
    """
    迭代翻页获取全部 topics（随机 3~6 秒间隔，避免触发限流）
    达到 stop_time 时停止（不包含 stop_time 时刻的数据）

    Args:
        group_id: 星球ID
        scope: "digests"（精华）或 "all"（全部）
        end_time: 本次翻页起点时间（ISO格式）
        stop_time: 停止时间（不含，iter_topics 不再请求）
        begin_time: 只获取此时间之后的数据（用于排除已处理数据）
        max_pages: 最多翻页次数（用于测试）

    Returns:
        list: 所有符合条件的 topics（从新到旧）
    """
    all_topics = []
    current_end = end_time
    page_num = 0

    while True:
        page_num += 1
        topics = fetch_page(group_id, scope, 20, current_end, begin_time)

        if not topics:
            print(f"  ↘ 翻页 {page_num} 无数据，退出")
            break

        first_time = topics[0].get("create_time", "")
        last_time = topics[-1].get("create_time", "")

        for t in topics:
            create_time = t.get("create_time", "")
            if stop_time and create_time < stop_time:
                print(f"  ↘ 到达停止时间 {stop_time}，退出（last={create_time}）")
                return all_topics
            all_topics.append(t)

        print(f"  翻页 {page_num:3d}，累计 {len(all_topics):5d} 条，"
              f"本页: {last_time[:19]} ~ {first_time[:19]}")

        current_end = topics[-1].get("create_time")
        interval = random.uniform(*TOPICS_FETCH_INTERVAL)
        time.sleep(interval)

        if max_pages and page_num >= max_pages:
            print(f"  ↘ 达到最大翻页数 {max_pages}，退出")
            break

    print(f"  ✓ 完成，共 {len(all_topics)} 条")
    return all_topics


# ─────────── 分享链接获取 ───────────

def fetch_share_url(topic_id: str) -> str:
    """
    获取单个话题的分享链接
    GET https://api.zsxq.com/v2/topics/{topic_id}/share_url

    Returns:
        str: 分享链接 或 空字符串（失败/不存在）
    """
    conn = http.client.HTTPSConnection("api.zsxq.com", context=_ctx, timeout=10)
    try:
        conn.request("GET", f"/v2/topics/{topic_id}/share_url",
                     headers=_api_headers())
        resp = conn.getresponse()
        body = resp.read()
        d = json.loads(body)
        if d.get("succeeded"):
            return d.get("resp_data", {}).get("share_url", "")
        return ""
    except Exception:
        return ""
    finally:
        conn.close()


def fetch_share_urls(topics: list, on_progress: callable = None) -> dict:
    """
    批量获取分享链接（逐条限速 1~2 秒，避免 API 过载）

    Args:
        topics: topics 列表
        on_progress: 进度回调 fn(current, total, topic_id, url)

    Returns:
        dict: {topic_id: share_url}，获取失败的 value 为空字符串
    """
    result = {}
    total = len(topics)

    for i, topic in enumerate(topics):
        tid = str(topic["topic_id"])
        url = fetch_share_url(tid)
        result[tid] = url
        if on_progress:
            on_progress(i + 1, total, tid, url)
        # 限速：避免触发 API 429
        if i < total - 1:
            time.sleep(random.uniform(*SHARE_URL_INTERVAL))

    success = sum(1 for v in result.values() if v)
    print(f"  分享链接获取完成：{success}/{total} 条有效链接")
    return result

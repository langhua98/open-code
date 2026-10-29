#!/usr/bin/env python3
"""抖音关键词搜索：按「最新发布」搜视频，绕开推荐算法（信息茧房），结果存成表格。

Usage:
    export PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright
    python3 douyin_search_cdp.py "贵州 赶集" [count] [--days N] [--hot]

    count    想要多少条（默认 30，最多 200）
    --days N 只要最近 N 天发的：1 / 7 / 180（抖音筛选只有这几档；默认 7）
    --hot    按最多点赞排（默认按最新发布）

Prereq: a REAL login at ~/.douyin_state.json (sessionid) -- logged out, Douyin shows a login
wall instead of results. Run scripts/douyin_login_qr.py first.

How: opens https://www.douyin.com/search/<kw>?type=video&sort_type=..&publish_time=.., scrolls,
and reads the page's own signed search responses (aweme/v1/web/search/item/ or
general/search/single/) through CDP Network.getResponseBody -- same trick as
douyin_user_works_cdp.py (replaying the URL gives 403 Sign Invalid).
If the page ignores the sort/time in the URL, the script clicks 筛选 -> 最新发布 / 一周内 itself.
It prints which sort_type / publish_time the page really requested (SORT line) -- report that
honestly instead of assuming the filter worked.

NOT yet verified end-to-end (written 2026-10-29 without a logged-in test account). If it finds
nothing, check the SORT/REQ lines and send the screenshot /home/user/douyin_search.png.

Output: /home/user/douyin_search.json, /home/user/douyin_search.csv,
        stdout SUMMARY_BEGIN..SUMMARY_END ready-to-send text. Forward that + MEDIA:<csv>.
"""
import base64
import csv
import json
import os
import sys
import time
import urllib.parse

from playwright.sync_api import Error as PwError
from playwright.sync_api import sync_playwright

STATE = os.path.expanduser("~/.douyin_state.json")
OUT = "/home/user/douyin_search.json"
CSV = "/home/user/douyin_search.csv"
SHOT = "/home/user/douyin_search.png"
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}
STEALTH = ["/opt/MediaCrawler/libs/stealth.min.js"]
SEARCH_APIS = ("aweme/v1/web/search/item/", "aweme/v1/web/general/search/single/",
               "aweme/v1/web/general/search/stream/")
FILTER_TEXT = {"sort": {"2": "最新发布", "1": "最多点赞"}, "time": {"1": "一天内", "7": "一周内", "180": "半年内"}}

found = {}
seen_q = []


def args():
    a = [x for x in sys.argv[1:]]
    hot = "--hot" in a
    days = "7"
    if "--days" in a:
        i = a.index("--days")
        days = a[i + 1] if i + 1 < len(a) else "7"
        del a[i:i + 2]
    a = [x for x in a if x != "--hot"]
    if not a:
        print(__doc__)
        sys.exit(1)
    kw = a[0]
    count = min(int(a[1]), 200) if len(a) > 1 and a[1].isdigit() else 30
    days = days if days in ("0", "1", "7", "180") else "7"
    return kw, count, "1" if hot else "2", days


def logged_in_jar():
    try:
        jar = json.load(open(STATE)).get("cookies", [])
    except (OSError, ValueError):
        return False
    return any(c.get("name") in LOGIN_COOKIES and c.get("value") for c in jar)


def bj(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime((ts or 0) + 8 * 3600)) if ts else ""


def harvest(payload):
    n0 = len(found)
    for d in payload.get("data") or []:
        a = d.get("aweme_info") if isinstance(d, dict) else None
        if not a and isinstance(d, dict):  # general/search wraps some cards one level deeper
            for sub in (d.get("aweme_mix_info") or {}).get("mix_items") or []:
                harvest({"data": [{"aweme_info": sub}]})
            continue
        aid = a.get("aweme_id")
        if not aid or aid in found:
            continue
        st = a.get("statistics") or {}
        au = a.get("author") or {}
        found[aid] = {
            "aweme_id": aid, "create_time": a.get("create_time"), "time": bj(a.get("create_time")),
            "desc": (a.get("desc") or "").replace("\n", " ").strip(),
            "author": au.get("nickname") or "", "author_sec_uid": au.get("sec_uid") or "",
            "author_url": f"https://www.douyin.com/user/{au['sec_uid']}" if au.get("sec_uid") else "",
            "digg": st.get("digg_count"), "comment": st.get("comment_count"), "share": st.get("share_count"),
            "duration_s": round(((a.get("video") or {}).get("duration") or 0) / 1000, 1),
            "url": f"https://www.douyin.com/video/{aid}",
        }
    print(f"PAGE new={len(found) - n0} total={len(found)} has_more={payload.get('has_more')}", flush=True)


def click_text(pg, text):
    try:
        pg.get_by_text(text, exact=True).filter(visible=True).first.click(timeout=3000)
        pg.wait_for_timeout(1500)
        return True
    except PwError:
        return False


def main():
    kw, count, sort_type, days = args()
    if not logged_in_jar():
        print("NO_SESSION_COOKIE: not logged in -> run scripts/douyin_login_qr.py first (search needs a login)")
        return 2
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path=os.environ.get("DOUYIN_CHROME") or None,
                              args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(storage_state=STATE, viewport={"width": 1280, "height": 900}, locale="zh-CN",
                            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"))
        stealth = next((s for s in STEALTH if os.path.exists(s)), None)
        if stealth:
            ctx.add_init_script(path=stealth)
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)
        cdp.send("Network.enable")
        ids = set()

        def on_request(ev):
            url = ev.get("request", {}).get("url", "")
            if any(api in url for api in SEARCH_APIS):
                ids.add(ev["requestId"])
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
                seen_q.append((q.get("sort_type"), q.get("publish_time"), q.get("filter_selected")))

        def on_finished(ev):
            if ev["requestId"] not in ids:
                return
            try:
                mb = cdp.send("Network.getResponseBody", {"requestId": ev["requestId"]})
            except Exception as e:  # noqa: BLE001 -- never let the handler die silently
                print("CDP_BODY_ERR", str(e)[:80], flush=True)
                return
            body = mb.get("body", "")
            if mb.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", "ignore")
            try:
                harvest(json.loads(body))
            except ValueError:
                pass  # general/search/stream sends chunks; the item API is the main source

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.loadingFinished", on_finished)

        q = urllib.parse.quote(kw)
        url = f"https://www.douyin.com/search/{q}?type=video&sort_type={sort_type}&publish_time={days}"
        for attempt in range(3):
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                break
            except PwError as e:
                if attempt == 2:
                    raise
                print("page load failed, retrying:", str(e).splitlines()[0], flush=True)
                pg.wait_for_timeout(3000)
        pg.wait_for_timeout(8000)
        print("SORT requested", seen_q[:1] or "none yet", flush=True)

        # the URL filter is not always honoured: set it through the 筛选 panel if the page didn't ask for it
        if not seen_q or seen_q[-1][0] != sort_type:
            if click_text(pg, "筛选"):
                ok1 = click_text(pg, FILTER_TEXT["sort"][sort_type])
                ok2 = days == "0" or click_text(pg, FILTER_TEXT["time"].get(days, "一周内"))
                print("FILTER clicked", ok1, ok2, flush=True)
                pg.wait_for_timeout(5000)

        idle = 0
        while len(found) < count and idle < 8:
            n = len(found)
            pg.mouse.wheel(0, 6000)
            try:
                pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            except PwError:
                pass
            pg.wait_for_timeout(2500)
            idle = idle + 1 if len(found) == n else 0
        try:
            pg.screenshot(path=SHOT)
        except PwError:
            pass
        print("SORT seen", sorted({x[:2] for x in seen_q if x[0] or x[1]}) or "none", flush=True)
        b.close()

    rows = sorted(found.values(), key=lambda x: -(x["create_time"] or 0)) if sort_type == "2" \
        else sorted(found.values(), key=lambda x: -(x["digg"] or 0))
    rows = rows[:count]
    json.dump({"keyword": kw, "sort_type": sort_type, "publish_time": days, "count": len(rows), "items": rows},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time", "author", "desc", "digg", "comment", "duration_s", "url", "author_url"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("SAVED", OUT, len(rows), "items")
    print("CSV", CSV)
    print("SUMMARY_BEGIN")
    print(f"「{kw}」{'最新发布' if sort_type == '2' else '最多点赞'}，{ {'0': '不限时间', '1': '一天内', '7': '一周内', '180': '半年内'}[days] }，共 {len(rows)} 条")
    for r in rows[:10]:
        print(f"  {r['time'][5:16]} @{r['author'][:12]} {r['desc'][:28]} {r['url']}")
    print("SUMMARY_END", flush=True)
    return 0 if rows else 3


if __name__ == "__main__":
    sys.exit(main())

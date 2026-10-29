#!/usr/bin/env python3
"""Dump a Douyin account's works by reading the page's own signed aweme/post JSON via CDP.

Usage:
    export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers   # run with /opt/mc-venv/bin/python
    python3 douyin_user_works_cdp.py [sec_uid]

Prereq: a REAL login state at ~/.douyin_state.json (must carry a sessionid cookie —
        run scripts/douyin_login_qr.py first; this script refuses to run otherwise,
        because a session-less jar only ever yields 8 decoy works / 1 request).

What is verified: stats extraction, CDP Network.getResponseBody body capture (the path that
works where pg.on("response").text() returns 0 bytes and replaying the signed URL returns
403 Sign Invalid), and the per-page harvest printout.

Verified 2026-10-29 with a real login: 193/193 works of a 193-work account, 11 pages
(wheel + scrollTo on every scrollable div + nudging the 作品 tab, give up after 20 idle rounds).
`CDP_BODY_ERR ... No resource with given identifier` / `NON_JSON_BODY` lines are harmless noise.

Output: /home/user/douyin_works.json  {sec_uid, account, count, pages, works[]}
        /home/user/douyin_works.csv   one row per work (opens in Excel / WPS)
        stdout SUMMARY_BEGIN..SUMMARY_END  ready-to-send text (top 5 by likes + latest 5):
        forward it plus MEDIA:/home/user/douyin_works.csv -- don't re-read the JSON, that costs tokens.

Argument: sec_uid (MS4wLjABAAAA...) or a www.douyin.com/user/... link.
"""
import base64
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

import re
_ARG = sys.argv[1] if len(sys.argv) > 1 else ""
_M = re.search(r"MS4wLjABAAAA[\w-]{10,200}", _ARG)
SEC_UID = _M.group(0) if _M else _ARG  # a www.douyin.com/user/... link works too
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
STATE = os.path.expanduser("~/.douyin_state.json")
COOKIES = os.path.expanduser("~/.douyin_cookies.json")
OUT = "/home/user/douyin_works.json"
CSV = "/home/user/douyin_works.csv"
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}

works, pages = {}, []


def precheck():
    """Refuse to scrape on a fake login — see references/account-scraping.md §7."""
    jar = []
    if os.path.exists(STATE):
        jar = json.load(open(STATE)).get("cookies", [])
    if not jar and os.path.exists(COOKIES):
        jar = json.load(open(COOKIES))
    got = LOGIN_COOKIES & {c["name"] for c in jar}
    if not got:
        print("NO_SESSION_COOKIE: jar has no sessionid -> fake/aborted login.")
        print("Move ~/.douyin_state.json and ~/.douyin_cookies.json aside and re-run")
        print("scripts/douyin_login_qr.py to get a scannable QR.")
        return False
    return True


def harvest(payload):
    n0 = len(works)
    for a in payload.get("aweme_list") or []:
        aid = a.get("aweme_id")
        if not aid or aid in works:
            continue
        st = a.get("statistics") or {}
        vid = a.get("video") or {}
        works[aid] = {
            "aweme_id": aid,
            "desc": (a.get("desc") or "").replace("\n", " ").strip(),
            "create_time": a.get("create_time"),
            "time": time.strftime("%Y-%m-%d %H:%M", time.gmtime((a.get("create_time") or 0) + 8 * 3600))  # 北京时间
            if a.get("create_time") else "",
            "duration_s": round((vid.get("duration") or 0) / 1000, 1),
            "digg": st.get("digg_count"),
            "comment": st.get("comment_count"),
            "share": st.get("share_count"),
            "collect": st.get("collect_count"),
            "play": st.get("play_count"),
            "url": f"https://www.douyin.com/video/{aid}",
            "cover": ((vid.get("cover") or {}).get("url_list") or [""])[0],
        }
    pages.append({"n": len(payload.get("aweme_list") or []),
                  "has_more": payload.get("has_more"),
                  "cursor": payload.get("max_cursor"),
                  "new": len(works) - n0})
    print(f"PAGE n={pages[-1]['n']} has_more={pages[-1]['has_more']} total={len(works)}", flush=True)


def write_csv(rows):
    import csv
    cols = ["time", "aweme_id", "desc", "duration_s", "digg", "comment", "share", "collect", "play", "url"]
    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel opens it right
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def wan(n):
    return f"{n / 10000:.1f}万" if isinstance(n, (int, float)) and n >= 10000 else str(n or 0)


def summary(stats, rows):
    """Ready-to-send text: the agent can forward it as is (no need to re-read the JSON)."""
    print("SUMMARY_BEGIN")
    print(f"{stats.get('nickname') or SEC_UID}｜粉丝 {stats.get('fans', '?')}｜获赞 {stats.get('like', '?')}"
          f"｜作品 {stats.get('works', '?')}，抓到 {len(rows)} 条")
    if rows:
        print("点赞最多：")
        for r in sorted(rows, key=lambda x: -(x.get("digg") or 0))[:5]:
            print(f"  {wan(r.get('digg'))}赞 {r['time'][:10]} {r['desc'][:30]} {r['url']}")
        print("最新：")
        for r in rows[:5]:
            print(f"  {r['time'][:10]} {wan(r.get('digg'))}赞 {r['desc'][:30]} {r['url']}")
    print("SUMMARY_END", flush=True)


def main():
    if not SEC_UID:
        print("usage: python3 douyin_user_works_cdp.py <sec_uid>")
        return 1
    if not precheck():
        return 2

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(storage_state=STATE, user_agent=UA,
                            viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)
        cdp.send("Network.enable")
        post_ids = set()

        def on_request(ev):
            if "aweme/v1/web/aweme/post/" in ev.get("request", {}).get("url", ""):
                post_ids.add(ev["requestId"])

        def on_finished(ev):
            if ev["requestId"] not in post_ids:
                return
            try:
                mb = cdp.send("Network.getResponseBody", {"requestId": ev["requestId"]})
            except Exception as e:            # never let the handler die silently
                print("CDP_BODY_ERR", e, flush=True)
                return
            body = mb.get("body", "")
            if mb.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", "ignore")
            try:
                j = json.loads(body)
            except Exception:
                print("NON_JSON_BODY", len(body), flush=True)
                return
            if j.get("aweme_list") is not None:
                harvest(j)

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.loadingFinished", on_finished)

        pg.goto(f"https://www.douyin.com/user/{SEC_UID}",
                wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(9000)

        try:
            stats = pg.evaluate("""() => {
                const g = k => { const e = document.querySelector('[data-e2e="'+k+'"]'); return e ? e.textContent.trim() : ''; };
                const n = document.querySelector('[data-e2e="user-name"]') || document.querySelector('h1');
                return {nickname: n ? n.textContent.trim() : '', follow: g('user-info-follow'),
                        fans: g('user-info-fans'), like: g('user-info-like'), works: g('user-tab-count')};
            }""")
        except Exception as e:
            stats = {"error": str(e)}
        print("STATS", json.dumps(stats, ensure_ascii=False), flush=True)

        # Real login gives 20 works/page, has_more=1, ~10 pages for a 193-work account.
        # A bare mouse.wheel loop stalled after 2 pages (one request per 60 s of scrolling),
        # so: wheel + scroll every scrollable container + nudge the 作品 tab, and only give
        # up after 20 idle rounds (not 10).
        stall, last_n = 0, -1
        for _ in range(200):
            pg.mouse.wheel(0, 6000)
            try:
                pg.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('div'))
                        .filter(e => e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 200);
                    els.forEach(e => e.scrollTo(0, e.scrollHeight));
                    window.scrollTo(0, document.body.scrollHeight);
                }""")
            except Exception:
                pass
            pg.wait_for_timeout(2500)
            if pages and pages[-1]["has_more"] == 0:
                break
            if len(pages) != last_n:
                last_n, stall = len(pages), 0
                continue
            stall += 1
            if stall in (5, 12):
                try:
                    pg.get_by_text("作品", exact=False).first.click(timeout=3000)
                except Exception:
                    pass
                pg.wait_for_timeout(1500)
            if stall >= 20:
                break

        result = {"sec_uid": SEC_UID, "account": stats, "count": len(works),
                  "pages": len(pages),
                  "works": sorted(works.values(), key=lambda x: -(x["create_time"] or 0))}
        json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        write_csv(result["works"])
        print("SAVED", OUT, len(works), "works /", len(pages), "pages", flush=True)
        print("CSV", CSV, flush=True)
        summary(stats, result["works"])
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

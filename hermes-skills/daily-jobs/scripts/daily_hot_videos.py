#!/usr/bin/env python3
"""每日热点视频：抖音热榜前 N 条（默认 10），每条下载一个视频，直接发到微信（不发链接）。

给 Hermes 的定时任务用（cronjob no_agent=True，输出原样发给用户，不经过大模型，不花 token）：
    cp daily_hot_videos.py daily_hot_videos.sh ~/.hermes/scripts/ && chmod +x ~/.hermes/scripts/daily_hot_videos.sh
    定时任务的 script 填 daily_hot_videos.sh（它用 /opt/mc-venv 的 Python，重启也在）

手动跑：bash ~/.hermes/scripts/daily_hot_videos.sh [N]

怎么拿视频：热榜接口（不用登录）每条带一个 sentence_id。用 ~/.douyin_state.json 里的真登录
开 www.douyin.com/hot/<sentence_id>，抖音会跳到这条热点当前的头条视频 /video/<作品号>（热榜里的
group_id 常常是几年前的老作品号，直接开会 core_dep 或拿不到数据，只在没跳转时兜底用），从页面自己的 aweme/detail 回包（CDP Network.getResponseBody，
跟 douyin_user_works_cdp.py 一样）或页面里的 RENDER_DATA 取视频地址，下载到 /home/user/hot_videos/。
微信发文件有超时（定时任务每个文件 30 秒），所以挑不超过 LIMIT_MB 的清晰度；都超了就用 ffmpeg 压到 540p。

输出：一段文字（热榜 10 条 + 哪几条没拿到视频）+ 每个视频一行 MEDIA:/home/user/hot_videos/xx.mp4，
Hermes 会把 MEDIA 行当文件发出去。没登录时只打印一句要重新扫码登录。
"""
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HOT = ("https://www.douyin.com/aweme/v1/web/hot/search/list/"
       "?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1")
STATE = os.path.expanduser("~/.douyin_state.json")
OUT_DIR = "/home/user/hot_videos"
LIMIT_MB = 15
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}
STEALTH = "/opt/MediaCrawler/libs/stealth.min.js"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def hot_list(n):
    for i in range(3):
        try:
            req = urllib.request.Request(HOT, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            inner = d.get("data") or {}
            words = inner.get("word_list") or (inner.get("data") or {}).get("word_list") or []
            return words[:n]
        except OSError as e:
            log("hot list:", e)
            time.sleep(3)
    return []


def heat(v):
    return f"{v / 10000:.0f}万" if isinstance(v, (int, float)) and v >= 10000 else str(v or "")


def under_display():
    """没有屏幕就在 xvfb-run 里重跑自己：有界面的 Chromium 不容易被抖音认出来（和保活脚本一样）"""
    if os.environ.get("DISPLAY") or os.environ.get("DOUYIN_QR_XVFB"):
        return True
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        return False
    os.environ["DOUYIN_QR_XVFB"] = "1"
    os.execv(xvfb, [xvfb, "-a", "-s", "-screen 0 1280x900x24", sys.executable, *sys.argv])


def logged_in():
    try:
        jar = json.load(open(STATE)).get("cookies", [])
    except (OSError, ValueError):
        return False
    return any(c["name"] in LOGIN_COOKIES and c.get("value") for c in jar)


def find_aweme(obj, aweme_id):
    """在任意嵌套 JSON 里找 aweme_id 对得上、带 video 的那一块"""
    stack = [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if str(x.get("aweme_id") or x.get("awemeId") or "") == aweme_id and isinstance(x.get("video"), dict):
                return x
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return None


def addr_urls(pa):
    """play_addr 有两种样子：接口回包是 {url_list: [...]}，RENDER_DATA 是 [{src: ...}]"""
    if isinstance(pa, dict):
        return pa.get("url_list") or [], pa.get("data_size") or 0
    if isinstance(pa, list):
        return [x.get("src") for x in pa if isinstance(x, dict)], 0
    return [], 0


def candidates(aweme):
    """视频地址，H.264 优先、清晰度从高到低：[(大小字节，不知道是 0, 地址)]"""
    v = aweme.get("video") or {}
    out = []
    for br in v.get("bit_rate") or v.get("bitRateList") or []:
        urls, size = addr_urls(br.get("play_addr") or br.get("playAddr"))
        # H.264 排在 H.265 前面：微信里哪台手机都能播
        rank = (not (br.get("is_h265") or br.get("isH265")), br.get("bit_rate") or br.get("bitRate") or 0)
        out += [(rank, size or br.get("dataSize") or 0, u) for u in urls if u]
    out.sort(key=lambda x: x[0], reverse=True)
    urls, size = addr_urls(v.get("play_addr") or v.get("playAddr"))
    out += [((False, 0), size, u) for u in urls if u]
    return [(size, ("https:" + u) if u.startswith("//") else u) for _, size, u in out]


def shrink(path):
    """超过 LIMIT_MB 就用 ffmpeg 压到 540p；没有 ffmpeg 或压不下来返回 False"""
    if os.path.getsize(path) <= LIMIT_MB * 1024 * 1024:
        return True
    if not shutil.which("ffmpeg"):
        return False
    small = path[:-4] + "_s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", "scale=-2:540", "-c:v", "libx264",
                    "-crf", "30", "-preset", "veryfast", "-c:a", "aac", "-b:a", "64k",
                    "-movflags", "+faststart", small], timeout=300, check=False)
    if os.path.exists(small) and 0 < os.path.getsize(small) <= LIMIT_MB * 1024 * 1024:
        os.replace(small, path)
        return True
    return False


def open_video(pg, sentence_id, group_id):
    """开热点页，等它跳到头条视频，返回作品号；没跳转就退回去开 group_id 的作品页"""
    if sentence_id:
        pg.goto(f"https://www.douyin.com/hot/{sentence_id}", wait_until="domcontentloaded", timeout=45000)
        for _ in range(15):
            m = re.search(r"/video/(\d{6,25})", pg.url)
            if m:
                return m.group(1)
            pg.wait_for_timeout(1000)
    if not group_id:
        return None
    pg.goto(f"https://www.douyin.com/video/{group_id}", wait_until="domcontentloaded", timeout=45000)
    return group_id


def grab(ctx, pg, cdp, bodies, sentence_id, group_id, path):
    """开热点的头条视频，拿到作品数据，下载视频。成功返回 None，失败返回原因"""
    bodies.clear()
    try:
        aweme_id = open_video(pg, sentence_id, group_id)
    except Exception as e:  # noqa: BLE001
        return f"打不开作品页（{type(e).__name__}）"
    if not aweme_id:
        return "没有视频"
    aweme = None
    for _ in range(15):
        pg.wait_for_timeout(1000)
        for b in list(bodies):
            aweme = find_aweme(b, aweme_id)
            if aweme:
                break
        if aweme:
            break
    if not aweme:  # 有的页面把作品数据直接写在 RENDER_DATA 里
        try:
            raw = pg.evaluate('() => (document.getElementById("RENDER_DATA") || {}).textContent || ""')
            aweme = find_aweme(json.loads(urllib.parse.unquote(raw)), aweme_id) if raw else None
        except Exception:  # noqa: BLE001
            aweme = None
    if not aweme:
        reason = next((f"抖音不给看（{(b.get('filter_detail') or {}).get('filter_reason')}）"
                       for b in bodies if isinstance(b, dict) and b.get("filter_detail")), "页面里没拿到作品数据")
        return reason
    if aweme.get("images"):
        return "这条是图文，不是视频"
    urls = candidates(aweme)
    if not urls:
        return "作品里没有视频地址"
    # 先挑已知大小不超限的里面最清楚的；其余按原顺序试
    fit = [u for s, u in urls if s and s <= LIMIT_MB * 1024 * 1024]
    rest = [u for s, u in urls if u not in fit]
    for url in fit[:2] + rest[:3]:
        try:
            r = ctx.request.get(url, headers={"Referer": "https://www.douyin.com/"}, timeout=120000)
        except Exception as e:  # noqa: BLE001
            log(aweme_id, "download:", e)
            continue
        if not r.ok:
            log(aweme_id, "download status", r.status)
            continue
        body = r.body()
        if len(body) < 50000:
            log(aweme_id, "too small", len(body))
            continue
        with open(path, "wb") as f:
            f.write(body)
        if shrink(path):
            return None
        os.remove(path)
        return f"视频太大（{len(body) // 1048576}MB），压不到 {LIMIT_MB}MB 以内"
    return "视频下载失败"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    words = hot_list(n)
    if not words:
        log("没拿到抖音热榜")
        return 0  # 什么也不打印 = 定时任务不发空消息
    if not logged_in():
        print("📰 今日抖音热点：抖音没登录（或登录掉了），拿不到视频。跟我说「抖音扫码登录」重新登录一下。")
        return 0

    headful = under_display()
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(OUT_DIR, "*.mp4")):  # 只留今天的
        os.remove(old)
    lines, media, missed = [], [], []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=not headful, executable_path=os.environ.get("DOUYIN_CHROME") or None,
                              args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        # 不改 UA：改成和浏览器版本对不上的 UA，作品接口会回 "Sign Invalid"
        ctx = b.new_context(storage_state=STATE, viewport={"width": 1280, "height": 900}, locale="zh-CN")
        if os.path.exists(STEALTH):
            ctx.add_init_script(path=STEALTH)
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)
        cdp.send("Network.enable")
        wanted, bodies = set(), []

        def on_request(ev):
            if "/aweme/v1/web/aweme/detail/" in ev.get("request", {}).get("url", ""):
                wanted.add(ev["requestId"])

        def on_finished(ev):
            if ev["requestId"] not in wanted:
                return
            try:
                mb = cdp.send("Network.getResponseBody", {"requestId": ev["requestId"]})
                body = mb.get("body", "")
                if mb.get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8", "ignore")
                bodies.append(json.loads(body))
            except Exception:  # noqa: BLE001 -- 拿不到这一个回包就算了，还有 RENDER_DATA
                pass

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.loadingFinished", on_finished)

        for i, w in enumerate(words, 1):
            word = (w.get("word") or "").strip()
            lines.append(f"{i}. {word}  🔥{heat(w.get('hot_value'))}")
            sentence_id = str(w.get("sentence_id") or "")
            group_id = str(w.get("group_id") or "")
            sentence_id = sentence_id if re.fullmatch(r"\d{1,25}", sentence_id) else ""
            group_id = group_id if re.fullmatch(r"\d{6,25}", group_id) else ""
            safe = re.sub(r'[\\/:*?"<>|\s]+', "", word)[:20] or str(i)
            path = os.path.join(OUT_DIR, f"{i:02d}_{safe}.mp4")
            why = grab(ctx, pg, cdp, bodies, sentence_id, group_id, path)
            log(i, word, "ok" if why is None else why)
            if why is None:
                media.append(path)
            else:
                missed.append(f"{i}（{why}）")
        ctx.storage_state(path=STATE)  # 顺便把刷新过的登录存回去
        b.close()

    text = f"📰 今日抖音热点 {time.strftime('%m-%d')}，视频 {len(media)} 条\n\n" + "\n".join(lines)
    if missed:
        text += "\n\n没拿到视频：" + "、".join(missed)
    print(text)
    for m in media:
        print(f"MEDIA:{m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

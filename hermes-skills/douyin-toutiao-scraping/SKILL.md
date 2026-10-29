---
name: douyin-toutiao-scraping
description: Scrape Douyin (抖音) and Toutiao (今日头条) content — hot search lists, trending boards, user accounts/作品 (share-link → sec_uid → headless browser), and QR-code login → cookie-jar reuse. Use when the user asks to crawl 抖音/头条 热点/热搜/新闻, a 抖音 user's profile/videos, or wants you to log into Douyin and save the cookie.
---

# Douyin / Toutiao Hot Content Scraping

ByteDance platforms (Douyin, Toutiao) are heavily anti-scraped (login walls, `X-Bogus`/`_signature` signing, captchas), but their **hot-search APIs are reachable directly** without signing in most server environments. Go straight to the JSON API — do NOT bother scraping the rendered HTML page.

## Verified-working endpoints

### Douyin 抖音热榜 (hot search list)
```
GET https://www.douyin.com/aweme/v1/web/hot/search/list/
Query: device_platform=webapp&aid=6383&channel=channel_pc_web
Headers: User-Agent (desktop Chrome), Referer: https://www.douyin.com/
```
Returns HTTP 200 JSON. Real data lives at **`data.data.word_list`** (note the DOUBLE `data` nesting — a common bug is reading only one level). Each item:
- `word` → the hot topic title
- `hot_value` → heat value (integer; divide by 10000 to show "万")
- Also present under `data.data`: `trending_list`, `trending_desc`, `active_time`, `banner_dark`/`banner_light`.

The page `https://www.douyin.com/hot` returns only a JS bootstrap shell (empty `<body>` + script) — it's useless for scraping; the API is the real source.

### Toutiao 今日头条热榜 (hot board)
```
GET https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc
Headers: desktop Chrome User-Agent
```
Returns `{"data": [...]}` where each item has `Title`, `Url`, `ClusterId`, `Label`. Good fallback when Douyin blocks or when the user wants news-flavored hot items (Toutiao is the same ByteDance ecosystem).

## Account / 作品 scraping (share link → sec_uid → headless browser)

### Step 0 — which Python to use

On the 小橘 Space use the image's own venv: `/opt/mc-venv/bin/python` already has Playwright and
`requests`, and its Chromium is in `/opt/pw-browsers`. Both survive restarts. Anything you
`pip install` into plain `python3` or download to `~/.cache` is **gone after every restart**
(that's why the 抖音登录保活 cron once died with `No module named 'playwright'`). So in every shell:

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
PY=/opt/mc-venv/bin/python
```
Don't install Playwright again. Only on another box without that venv: `python3 -m pip install playwright requests`,
`PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright python3 -m playwright install chromium` (never `--with-deps`, it needs root).

When the user shares a Douyin profile link (`v.douyin.com/...`, often "查看TA的更多作品"), the working flow:

1. **Resolve the short link to get `sec_uid`.** `v.douyin.com/xxx` → 302 → `https://www.iesdouyin.com/share/user/<SEC_UID>?...&sec_uid=<SEC_UID>...`. Read the `Location` header with `allow_redirects=False`; `sec_uid` is a base64-ish `MS4wLjABAAAA...` token.
2. **The post API does NOT work unsigned.** `GET https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id=<sec_uid>...` → `403 Blocked by ArgusSecurityPlugin Uifid Not Found` (needs `X-Bogus`/`_signature` + `msToken`). The legacy `iesdouyin.com/web/api/v2/aweme/post/` returns empty 200 (dead).
3. **The profile HTML is a JS shell** (~2KB, no SSR data) — `requests` alone gets nothing.
4. **Use Playwright headless Chromium** to render `https://www.douyin.com/user/<sec_uid>`, then read the DOM:
   - Account stats are on `data-e2e` attributes: `user-info-follow` (关注), `user-info-fans` (粉丝), `user-info-like` (获赞), `user-tab-count` (作品数).
   - Works are `a[href*="/video/"]` links; link text = video title. Scroll `page.mouse.wheel(0, 3000)` repeatedly to trigger lazy-load.
5. **Unauthenticated cap**: without a login Cookie, Douyin only exposes ~8 works of a large account (the full list stays behind the sign wall). To grab everything, ask the user for a logged-in browser Cookie and inject via `context.add_cookies(...)`.
   - The 8 items are **not a truncated slice of the real feed** — they are a "猜你喜欢" style drip: unrelated categories (games, shoes, 装修, 美妆, 罗翔…) mixed in with maybe one or two real works. Compare against `user-tab-count` (e.g. 193) and say plainly that the list is decoy data, not the user's actual works. Never present those 8 as "their videos".
   - Practical skill: cross-check each title against the account's known niche before reporting. If the categories scatter, the scrape hit the unauthenticated drip, not the profile.
6. **Cookie persistence (user asked for this)**: after QR login, save the cookie jar to `/home/user/.douyin_cookies.json` and reuse it on later runs — use `scripts/douyin_login_qr.py` (below) which waits for login then `json.dump(context.cookies())`. Never re-ask the user to scan if that file exists and is fresh; refresh only when the profile renders logged-out.
7. **QR login is the case where honesty matters most**: make clear that only the *account stats* are real in an unauthenticated run, and state upfront that the cookie equals an account credential stored in plaintext — then offer to delete it after use. The user explicitly asked for QR login + cookie reuse, so do both, but disclose.

### QR login flow (verified end-to-end)

Run `scripts/douyin_login_qr.py` in the **background with `watch_patterns`, NOT `notify_on_complete`**:
`terminal(background=True, watch_patterns=["QR_REFRESHED", "SMS_SENT", "SMS_CLICK_FAILED", "SMS_BAD_CODE", "SMS_RESULT", "LOGGED_IN", "TIMEOUT"])`.
Then `process(action="wait", timeout=20)` once to get the first `QR_READY` line and send that QR at once.
Why: the script runs for minutes and only exits after login. With `notify_on_complete` you hear nothing
until then, so you never see `SMS_SENT` or a new QR — that's how a user scanned, got asked for an SMS
code on the page, and nobody told them (2026-10-29). With `watch_patterns` each of those lines wakes you
(at most one per 15 s). If the user says 扫了/没收到/怎么样了, run `process(action="log", session_id=...)` and
act on the newest lines below. Don't `wait` on it for minutes:

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers; PY=/opt/mc-venv/bin/python
DOUYIN_SEC_UID=<sec_uid> $PY scripts/douyin_login_qr.py 300
```

It re-runs itself under `xvfb-run` (real, headful Chromium on a virtual screen) — Douyin kills QRs from headless Chromium almost immediately, that's why the user saw "二维码已过期" right after scanning. Never switch it back to headless, never hand-write a new login script.

**What to do on each output line:**
- `QR_READY <path> <time>` → **send that exact path immediately** with `MEDIA:<path>` + "打开抖音 App → 左上角 → 扫一扫，扫完在手机上点确认". **Each QR works for only 60 seconds from `<time>`** — Douyin then silently replaces it (no "已过期" text on the page). **Do NOT run vision_analyze first** — that plus waiting on the process made the last QR ~55 s old when it arrived, i.e. dead. The script already refuses to save a QR that hasn't loaded. Tell the user: 收到就马上扫，一分钟内有效.
- `QR_EXPIRED <path>` → that QR is dead (60 s passed) and its file is deleted. Don't send it, don't send any older image.
- `QR_REFRESHED <path> <time>` → comes about every 60 s until the user scans. Send the new path at once, say "上一张过期了，扫这张".
- `QR_NOT_LOADED <path>` → the QR never appeared. Don't send anything to scan; tell the user and offer to retry.
- `VERIFY <path> <words>` → Douyin wants 身份验证 (new device). The script picks **接收短信验证码** itself (刷脸 ends in 流程错误 here) — wait for the next line.
- `SMS_CLICK_FAILED <path> try n/6` → it picked 短信 but the page didn't say 短信已发送 yet; it retries by itself (it clicks with the real X11 mouse through XTEST, like `scripts/xinput.py`, so you normally do nothing). Tell the user "短信还没发出去，正在重试". After try 6/6, click 接收短信验证码 yourself with `scripts/xinput.py` (references/xvfb-browser-control.md) and check the page says 短信已发送至.
- `SMS_SENT <path>` → the page says 短信已发送, so an SMS code is on its way to the user's phone. Ask: "抖音给你发了短信验证码，把 6 位数字发我". When they answer, run `echo <digits> > ~/.douyin_sms_code` — the script types it and presses 验证 (`SMS_SUBMITTED … -> ok`, then `SMS_RESULT <screenshot>`, then `LOGGED_IN` if it passed). Wrong/expired code: ask again and write the file again; the script keeps waiting. **Don't kill the login script and don't click around with XTEST** — see `references/login-verification.md`.
- `ALREADY_LOGGED_IN` → no QR needed, cookies refreshed (check `login cookies:` isn't `[]`). `LOGGED_IN` → done. `TIMEOUT` → say so, offer to retry.

**Never send a QR image that is not the path from the newest `QR_READY`/`QR_REFRESHED` line.** Only one `/home/user/douyin_qr_<HHMMSS>.png` exists at a time; the file name is the time it was drawn. If you're unsure, `ls /home/user/douyin_qr_*.png` — no file means no valid QR. The old `/home/user/douyin_qr_crop.png` is obsolete (the script deletes it); never send it.

**Pitfalls found the hard way:**
- **60-second QRs.** `get_qrcode` / `check_qrconnect` return `expire_time` = issue + 60 s and the page swaps the image without any notice. The script watches the QR `<img>` src and reports each swap (`QR_EXPIRED` + `QR_REFRESHED`).
- **Headless = dead QR.** See above. Headful + `xvfb-run` + `--disable-blink-features=AutomationControlled` + MediaCrawler's `stealth.min.js` (`/opt/MediaCrawler/libs/`) is the same recipe the Space's video crawler logs in with.
- **The QR box first shows only a TikTok logo**; the QR image arrives a few seconds later. The script waits for the real `<img>` (≥100 px) before screenshotting `#animate_qrcode_container`.
- **`canvas.toDataURL()` / `<img src>` returns a BLANK white PNG (~1.5 KB)** on douyin.com. Screenshot the element instead.
- **Login detection**: scanning alone does not log in (user must tap 确认登录 in-app). A real login always sets `sessionid`; the script counts only localStorage `HasUserLogin`=1, cookie `LOGIN_STATUS`=1 or a non-empty `sessionid`/`sessionid_ss`/`sid_tt`/`sid_guard`, and prints `login cookies: [...]`. The old DOM guess (avatar visible, no login button) was true while logged out and reported LOGGED_IN with nobody scanning. **Never tell the user "登录成功" if `login cookies:` is empty `[]`.**
- **`Execution context was destroyed, most likely because of a navigation`** — Douyin reloads right after the scan is confirmed and right after load with a saved login. The script's `dom()` helper waits and retries; check `ctx.cookies()` first.
- **One run at a time**: the script stops any earlier run of itself (pid file `~/.douyin_login.pid`). Don't start a second one while the first is still waiting for a scan — re-running means a new QR and the old one is dead.
- **Keep the user informed**: send the QR the moment it prints and reply in the chat; don't sit in a long tool loop without answering.

### One message → full works list (fixed script, cheap)

When the user sends a profile link and wants its videos:
```bash
cd ~/.hermes/skills/web-scraping/douyin-toutiao-scraping
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers; PY=/opt/mc-venv/bin/python
$PY scripts/douyin_user_works_cdp.py "<sec_uid or https://www.douyin.com/user/... link>"
```
(`v.douyin.com/...` short link: resolve it first — read the 302 `Location` with `allow_redirects=False`, `sec_uid` is in it.)
Verified 193/193 with a real login. When it ends, forward the text between `SUMMARY_BEGIN` and `SUMMARY_END` **as is** plus `MEDIA:/home/user/douyin_works.csv`. Don't re-read the JSON or take screenshots — the summary already has top 5 by likes, latest 5 and links. Needs the real login (`NO_SESSION_COOKIE` → log in first).

### Keyword search, newest first (out of the 信息茧房)

Logged-in search still ranks by the user's taste; **sorting by 最新发布 within a time window** is what shows videos the feed never would:
```bash
$PY scripts/douyin_search_cdp.py "贵州 赶集" 30 --days 7      # 最新发布，一周内
$PY scripts/douyin_search_cdp.py "非遗 手艺" 50 --days 180 --hot   # 最多点赞，半年内
```
Forward `SUMMARY_BEGIN..SUMMARY_END` + `MEDIA:/home/user/douyin_search.csv`. The `SORT seen` line says which sort/time the page really used — if it's not what was asked, say so. Not verified end-to-end yet (written without a test login): if it returns 0, send `/home/user/douyin_search.png` and report.
**Only search keywords the user gave you.** Never pick keywords yourself and run them (the owner cancelled a run where you did). If the user asks vaguely, *suggest* a few (topics they never watch like 非遗手艺、县城纪录; place + daily life like 新疆 放牧、贵州 赶集; small hashtags) and wait for them to choose.

### Into the 小橘视频 pipeline

To get found videos/accounts into the owner's Telegram channel, use the `xiaoju-pipeline` skill (`POST $XIAOJU_STREAMER_URL/hermes/links`): video links go to review, profile links become 小号. Take the links from the CSV `url` / `author_url` columns.

**`/tmp` is not writable in this environment** — write QR/screenshots to `/home/user/`. Details and an inline reference implementation in `references/qr-login.md`.

See `references/account-scraping.md` for the full recipe + error transcripts, and `scripts/douyin_user_crawl.py` for a re-runnable Playwright crawler.

## Steps
1. Use **Python `requests`** (the box may not have `curl` — don't assume it does). `pip install requests` if missing.
2. Set a desktop Chrome `User-Agent` and a `Referer: https://www.douyin.com/`.
3. Fetch the API, parse `data.data.word_list`, print `word` + `hot_value` (format `hot_value/10000` → `X.X万`).
4. Run the script, show the user the top ~20 items compactly (full list is usually 49–50 items).

## Pitfalls
- **Double `data` nesting**: data is at `resp["data"]["data"]["word_list"]`, not `resp["data"]["word_list"]`. If `word_list` comes back `None`, print `list(resp.keys())` and `list(resp["data"].keys())` to inspect structure before guessing.
- **Hot list is a mixed bag**: news + entertainment + hashtag challenges + drama marketing. Don't present it as pure "news" — it's the native Douyin 热榜 flavor.
- **Anti-scrape reality**: hot-list/search endpoints usually work unsigned; but account videos, comment dumps, and full detail pages typically need signed params and login. Probe first, then tell the user honestly what's reachable vs. what needs credentials.
- **Uninstalled ≠ unavailable**: if `playwright`/`requests` seem missing, you are on the wrong Python: use `/opt/mc-venv/bin/python` (Step 0).

## Scripts
- `scripts/douyin_hot.py` — re-runnable fetcher that prints the ranked hot list. Copy and modify for new targets (e.g. swap the URL for Toutiao, or extend `word_list` parsing to other fields).
- `scripts/douyin_user_crawl.py` — Playwright crawler that renders a profile from a `sec_uid` (or resolves a `v.douyin.com` short link) and extracts account stats + works. Needs `pip install playwright` and a Chromium build.
- `scripts/douyin_user_works_cdp.py` — a profile's full works list (CDP response bodies), CSV + ready summary.
- `scripts/douyin_search_cdp.py` — keyword search, newest/most-liked within N days, CSV + summary.
- `scripts/douyin_login_qr.py` — generates a scannable login QR (headful Chromium under xvfb, element screenshot, timestamped file), handles the 短信 身份验证, polls for the scan, and saves `~/.douyin_cookies.json` + `~/.douyin_state.json`. Run it in the background. Companion notes: `references/qr-login.md`.

## Extending
For comments/individual video detail pages, probe `aweme/v1/web/...` endpoints the same way (UA + Referer) and check for `status_code`/`status_msg` signaling a signing requirement. For account profiles, use the headless-browser path above. Offer to wire any successful fetcher into a `cronjob` for daily push (e.g. "每天早上 9 点推当天抖音热点到微信").

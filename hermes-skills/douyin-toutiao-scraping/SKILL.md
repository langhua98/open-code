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

### Step 0 — Playwright setup when `--with-deps` can't run

On a box without root, `python3 -m playwright install --with-deps chromium` dies with
`su: Authentication failure`, and the default download dir is unwritable
(`EACCES: permission denied, mkdir '/opt/pw-browsers/__dirlock'`). Working recipe:

```bash
python3 -m pip install playwright requests
export PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright   # same shell as the run
python3 -m playwright install chromium        # NO --with-deps (that step needs root)
```
Only `pip install playwright` on its own is not enough — the browser binary is a separate download.
Verify with `ls $PLAYWRIGHT_BROWSERS_PATH` → expect `chromium-1248`, `chromium_headless_shell-1248`, `ffmpeg-1013`.
If launch then complains about missing system libs, use `launch(headless=True, args=["--no-sandbox"])`.

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

Run `scripts/douyin_login_qr.py` in the **background** (`terminal(background=True, notify_on_complete=True)`) because it blocks while polling for the scan, then **read its output right away** (don't `wait` for the process — it runs for minutes):

```bash
export PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright
DOUYIN_SEC_UID=<sec_uid> python3 scripts/douyin_login_qr.py 300
```

It re-runs itself under `xvfb-run` (real, headful Chromium on a virtual screen) — Douyin kills QRs from headless Chromium almost immediately, that's why the user saw "二维码已过期" right after scanning. Never switch it back to headless, never hand-write a new login script.

**What to do on each output line:**
- `QR_READY <path> <time>` → **send that exact path immediately** with `MEDIA:<path>` + "打开抖音 App → 左上角 → 扫一扫，扫完在手机上点确认". **Each QR works for only 60 seconds from `<time>`** — Douyin then silently replaces it (no "已过期" text on the page). **Do NOT run vision_analyze first** — that plus waiting on the process made the last QR ~55 s old when it arrived, i.e. dead. The script already refuses to save a QR that hasn't loaded. Tell the user: 收到就马上扫，一分钟内有效.
- `QR_EXPIRED <path>` → that QR is dead (60 s passed) and its file is deleted. Don't send it, don't send any older image.
- `QR_REFRESHED <path> <time>` → comes about every 60 s until the user scans. Send the new path at once, say "上一张过期了，扫这张".
- `QR_NOT_LOADED <path>` → the QR never appeared. Don't send anything to scan; tell the user and offer to retry.
- `VERIFY <path> <words>` → Douyin wants an extra check (SMS / 刷脸). Send the screenshot and tell the user to follow the prompt in the 抖音 App.
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
- **Uninstalled ≠ unavailable**: if `playwright`/`requests` are missing, install them (`pip install playwright requests`, then `PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright python3 -m playwright install chromium` — never `--with-deps`, it needs root). See `references/account-scraping.md` §0.

## Scripts
- `scripts/douyin_hot.py` — re-runnable fetcher that prints the ranked hot list. Copy and modify for new targets (e.g. swap the URL for Toutiao, or extend `word_list` parsing to other fields).
- `scripts/douyin_user_crawl.py` — Playwright crawler that renders a profile from a `sec_uid` (or resolves a `v.douyin.com` short link) and extracts account stats + works. Needs `pip install playwright` and a Chromium build.
- `scripts/douyin_login_qr.py` — generates a scannable login QR (headful Chromium under xvfb, element screenshot, timestamped file), polls for the scan, and saves `~/.douyin_cookies.json` + `~/.douyin_state.json`. Run it in the background. Companion notes: `references/qr-login.md`.

## Extending
For comments/individual video detail pages, probe `aweme/v1/web/...` endpoints the same way (UA + Referer) and check for `status_code`/`status_msg` signaling a signing requirement. For account profiles, use the headless-browser path above. Offer to wire any successful fetcher into a `cronjob` for daily push (e.g. "每天早上 9 点推当天抖音热点到微信").

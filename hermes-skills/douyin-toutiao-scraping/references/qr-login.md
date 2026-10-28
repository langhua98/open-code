# Douyin QR-code login → cookie jar

Recipe for getting a logged-in Douyin cookie after the user offers
"我登录给你，你保存cookie". Always use `scripts/douyin_login_qr.py`; don't
hand-write a new login script.

## Why QR and not user-supplied cookie text

Asking the user to open devtools and paste `document.cookie` is error-prone:
`document.cookie` cannot see `HttpOnly` cookies, so the jar is incomplete and
the post API still 403s. Driving the QR login inside the browser captures the
**full** `context.cookies()` including HttpOnly entries.

## Flow (what the script does)

1. No `$DISPLAY` → re-run itself under `xvfb-run -a` so Chromium is **headful**
   on a virtual screen. Launch with `--disable-blink-features=AutomationControlled`
   and inject `/opt/MediaCrawler/libs/stealth.min.js` (fallback: hide
   `navigator.webdriver`).
2. Stop an earlier run of itself (`~/.douyin_login.pid`), delete every old
   `/home/user/douyin_qr_*.png` (and the obsolete `douyin_qr_crop.png`).
3. Load `~/.douyin_state.json` if present; still logged in → `ALREADY_LOGGED_IN`.
4. Open the login panel (it often pops up by itself; else click 登录).
5. Wait until `#animate_qrcode_container img` has really loaded
   (`naturalWidth >= 100`; before that the box shows only a TikTok logo), then
   screenshot that element to `/home/user/douyin_qr_<HHMMSS>.png`, upscale 2x,
   print `QR_READY <path> <HH:MM:SS>`. Not loaded in 30 s → `QR_NOT_LOADED`.
6. Poll every second: logged in → save cookies + `storage_state`, `LOGGED_IN`.
   **Each QR works for 60 s** (`expire_time` in `get_qrcode`/`check_qrconnect` =
   issue + 60 s) and the page swaps the image silently, no "已过期" text. When the
   QR `<img>` src changes → delete the old file, `QR_EXPIRED`, screenshot the new
   one, `QR_REFRESHED <path> <time>`. (If a "点击刷新" button shows, it's clicked.) Verification dialog
   (身份验证/安全验证/刷脸…) → full screenshot, `VERIFY <path> <words>`.
7. On exit every QR file is deleted, so nothing stale is left to send.

## Sending

Send the path from the newest `QR_READY` / `QR_REFRESHED` line **immediately**
(`MEDIA:<path>` + 打开抖音 App → 左上角 → 扫一扫，扫完点确认). The QR works for
60 seconds from the time in that line. Do not run `vision_analyze` first.

## Gotchas

| Symptom | Cause / fix |
|---|---|
| User scans at once and the app says 二维码已过期 | headless Chromium: Douyin invalidates its QRs. Use the script (headful under xvfb + stealth) |
| QR "expired" though the user was quick | QRs live 60 s and the image sat ~55 s before it was sent (process wait + vision_analyze). Send on `QR_READY`/`QR_REFRESHED` at once |
| Sent picture is an old QR | only send the newest printed path; old files are deleted on expiry/refresh/exit |
| Picture shows just the TikTok logo, no code | QR image hadn't loaded yet; the script now waits for it (`QR_NOT_LOADED` if it never comes) |
| Saved QR is a plain-white ~1.5 KB PNG | `canvas.toDataURL()` / `<img src>` give nothing usable; screenshot the element |
| `su: Authentication failure` during install | `--with-deps` needs root; install chromium without it |
| `EACCES ... /opt/pw-browsers/__dirlock` | set `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright` |
| `ModuleNotFoundError: No module named 'playwright'` right after installing | a *different* python is on PATH than the one pip targeted; check `python3 -c "import sys; print(sys.executable)"` |
| Poll never sees `sessionid` | the user scanned but didn't tap 确认登录 in the app. Not logged in -- don't report success |
| LOGGED_IN / ALREADY_LOGGED_IN although nobody scanned, no `sessionid` saved | old DOM guess (avatar + no login button) is true logged out; the script now only trusts HasUserLogin / LOGIN_STATUS / sessionid. Delete `~/.douyin_state.json` and `~/.douyin_cookies.json` from such a run |
| `/tmp` writes fail | use `/home/user/` |
| `Page.query_selector: Execution context was destroyed ... navigation` | Douyin navigates after the scan is confirmed and after load with a saved state; the script's `dom()` retries |
| Two QR runs at once, both broken | the script stops the earlier run; don't start a second while one waits |

## Credential disclosure (do this every time)

State plainly that the cookie jar equals account credentials, lives in plaintext
at `~/.douyin_cookies.json`, and offer to delete it once the crawl is done.

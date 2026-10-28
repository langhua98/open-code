# Douyin QR-code login → cookie jar

Session-tested (headless Chromium, no display) recipe for getting a logged-in
Douyin cookie after the user offers "我登录给你，你保存cookie".

## Why QR and not user-supplied cookie text

Asking the user to open devtools and paste `document.cookie` is error-prone —
`document.cookie` cannot see `HttpOnly` cookies, so the resulting jar is
incomplete and the post API still 403s. Generating a QR and driving the login
inside the browser session captures the **full** `context.cookies()` including
HttpOnly entries.

## Flow

1. `pip install playwright requests pillow`; Chromium via
   `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m playwright install chromium`
   (never `--with-deps`, it needs root).
2. Open the profile URL (not the bare homepage — clicking login from a profile
   keeps the post-login session on the page you care about).
3. Click the login trigger. Selectors that worked, in priority order:
   - `#douyin-header-menuCt [data-e2e="login-button"]`
   - `[data-e2e="login-button"]`
   - `button:has-text("登录")`
   Wait ~4 s after the click for the modal + QR to render.
4. **Capture the QR by screenshotting the viewport and clipping**, not by
   reading the canvas:

```python
pg.screenshot(path="/home/user/douyin_login_full.png")
w, h = 1280, 900
box = {"x": int(w*0.26), "y": int(h*0.34),
       "width": int(w*0.20), "height": int(h*0.32)}
pg.screenshot(path="/home/user/douyin_qr_crop.png", clip=box)
```

   Then upscale for phone scanning (Pillow):

```python
from PIL import Image
im = Image.open("/home/user/douyin_qr_crop.png")
im.resize((im.width*2, im.height*2), Image.LANCZOS).save("/home/user/douyin_qr_crop.png")
```

5. **Verify before sending.** `vision_analyze("/home/user/douyin_qr_crop.png",
   "图里有完整的抖音登录二维码吗？")`. If the answer is "blank white" the crop box
   is wrong (or the modal hadn't rendered) — adjust and re-crop. Never ship an
   unverified QR to the user.
6. Send with `MEDIA:/home/user/douyin_qr_crop.png` + instructions
   (打开抖音 App → 左上角 → 扫一扫), then poll.
7. Poll every ~3 s for up to N seconds:
   - DOM: avatar/user-info present **and** `[data-e2e="login-button"]` gone.
   - Cookie fallback: `{"sessionid","sessionid_ss"} & {c["name"] for c in ctx.cookies()}`.
8. Persist: `json.dump(ctx.cookies(), open("~/.douyin_cookies.json","w"))` and
   `ctx.storage_state(path="~/.douyin_state.json")` (storage_state restores
   localStorage too, useful for `msToken`-style tokens).
9. Reuse next time: `ctx = browser.new_context(storage_state="~/.douyin_state.json")`.

## Gotchas

| Symptom | Cause / fix |
|---|---|
| Saved QR is a plain-white ~1.5 KB PNG | `canvas.toDataURL()` and `<img src>` give nothing usable; screenshot+clip instead |
| `su: Authentication failure` during install | `--with-deps` needs root; install chromium without it |
| `EACCES ... /opt/pw-browsers/__dirlock` | set `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright` |
| `ModuleNotFoundError: No module named 'playwright'` right after installing | a *different* python is on PATH than the one pip targeted; check `python3 -c "import sys; print(sys.executable)"` |
| Poll never sees `sessionid` | the user scanned but didn't confirm in the app; also some login flows use other cookie names — prefer DOM detection |
| QR image uploads but user says "扫不了" | crop too tight / no quiet zone; widen the clip box |
| `/tmp` writes fail | use `/home/user/` for screenshots |
| `Page.query_selector: Execution context was destroyed ... navigation` (every 2nd login) | Douyin navigates after the scan is confirmed and after load with a saved state. Wrap every DOM call (the script's `dom()` helper: catch, `wait_for_load_state`, retry) and check `ctx.cookies()` first |
| Second run shows a QR although you're already logged in | load `~/.douyin_state.json` into the context and check login before opening the modal (`ALREADY_LOGGED_IN`) |
| Two QR runs at once, both broken | kill the earlier background run first; one Chromium per login |

## Credential disclosure (do this every time)

State plainly that the cookie jar equals account credentials, lives in plaintext
at `~/.douyin_cookies.json`, and offer to delete it once the crawl is done. Users
appreciate the choice and it prevents surprise later.

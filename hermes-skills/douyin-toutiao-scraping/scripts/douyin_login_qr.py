#!/usr/bin/env python3
"""Douyin login-QR harvester (real Chromium on a virtual screen).

Opens Douyin, triggers the login modal, screenshots the QR element to a PNG the
user can scan, then polls until login succeeds and dumps cookies.

Usage:
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers /opt/mc-venv/bin/python douyin_login_qr.py [timeout_seconds]

Prints one status line per event (read them from the background process output):
    ALREADY_LOGGED_IN            saved state is still valid -- no scan needed, cookies refreshed
    QR_READY <path> <HH:MM:SS>   new QR saved -> SEND THAT EXACT PATH NOW (no vision_analyze);
                                 it works for 60 seconds only
    QR_EXPIRED <path>            that QR is dead and its file is deleted -- don't send it again
    QR_REFRESHED <path> <time>   Douyin drew a new QR -> send the new path
    VERIFY <path> <words>        Douyin wants an extra check (身份验证) -> the script picks
                                 接收短信验证码 itself when offered (刷脸 fails on this server)
    SMS_CLICK_FAILED <path> ..   picked 接收短信验证码 but the page never said 短信已发送; it retries
                                 (6 tries). After the 6th: XTEST-click it (references/xvfb-browser-control.md)
    SMS_SENT <path>              the page says 短信已发送 -> the code is on the user's phone: ask for it, then
                                 `echo <code> > ~/.douyin_sms_code` (the script types it + 验证)
    SMS_SUBMITTED <code> -> ok   typed and pressed 验证; SMS_RESULT <path> = screenshot after it
    SMS_BAD_CODE                 the file had no 4-8 digits -> ask again
    LOGGED_IN                    login confirmed, cookies saved
    QR_NOT_LOADED <path>         the QR image never arrived (box shows only the logo) -- send
                                 nothing to scan; tell the user and offer to retry
    TIMEOUT                      nobody scanned in time (cookies NOT overwritten)

Outputs:
    /home/user/douyin_qr_<HHMMSS>.png  the current QR. Only ONE such file exists at a time:
                                       older ones are deleted the moment a QR expires or a
                                       new one is drawn, so a stale QR can't be sent.
    ~/.douyin_cookies.json             cookie list (ctx.cookies())
    ~/.douyin_state.json               storage_state for later ctx reuse

Hard-won details (do not "fix" these back):
  * Headless Chromium gets a QR that Douyin kills right away ("二维码已过期" the
    moment the user scans). Douyin spots headless + automation flags. So: real
    (headful) Chromium on an Xvfb virtual screen (the script re-runs itself under
    `xvfb-run` when there is no $DISPLAY), `--disable-blink-features=AutomationControlled`,
    and MediaCrawler's stealth.min.js when present. Same recipe as the Space's own
    working login (streamer/dy_login.py).
  * Each QR works for 60 SECONDS from when it is drawn (get_qrcode/check_qrconnect
    return expire_time = issue + 60 s). Douyin then silently draws a new one --
    no "已过期" text on the page -- so a picture sent 55 s after it was taken is
    dead on arrival. That was the "二维码一扫就过期" bug. The script watches the
    QR <img> src and prints QR_EXPIRED + QR_REFRESHED on every swap. Send each
    QR the second it prints; never run vision_analyze first.
  * Screenshot the element `#animate_qrcode_container` (after its <img> loaded).
    Canvas/`<img src>` extraction gives a BLANK 1.5KB PNG; don't use it.
  * Login test = localStorage HasUserLogin == "1", or cookie LOGIN_STATUS == "1",
    or a non-empty sessionid / sessionid_ss / sid_tt / sid_guard (same as
    streamer/dy_login.py). NEVER guess from the DOM (avatar present, no login
    button): that is also true logged out and reported LOGGED_IN / ALREADY_LOGGED_IN
    with nobody scanning. A real login always has sessionid.
  * "Execution context was destroyed, most likely because of a navigation":
    Douyin reloads / redirects the page right after the scan is confirmed, and on
    a second run (state already saved) right after load. Never call DOM methods
    bare: go through dom() below, which waits for the new page and retries.
  * Second run: load ~/.douyin_state.json first and check whether it is still
    logged in. Only show a new QR if it is not. An earlier run of this script is
    killed first (pid file) -- two browsers fighting over one login break both.
"""
import glob
import json
import os
import shutil
import signal
import sys
import time

COOKIE_PATH = os.path.expanduser("~/.douyin_cookies.json")
STATE_PATH = os.path.expanduser("~/.douyin_state.json")
PID_PATH = os.path.expanduser("~/.douyin_login.pid")
SMS_PATH = os.path.expanduser("~/.douyin_sms_code")  # Hermes writes the SMS code here
SMS_WAIT = 300  # after the SMS is sent, wait at least this long for the user's code
OUT_DIR = "/home/user"
QR_GLOB = os.path.join(OUT_DIR, "douyin_qr_*.png")
STEALTH = ["/opt/MediaCrawler/libs/stealth.min.js", "libs/stealth.min.js"]
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}
QR_BOX = "#animate_qrcode_container"
QR_IMG = "#animate_qrcode_container img"
LOGIN_PANEL = "#login-panel-new"
LOGIN_BUTTONS = ['#douyin-header-menuCt [data-e2e="login-button"]',
                 '[data-e2e="login-button"]',
                 "xpath=//p[text() = '登录']",
                 'button:has-text("登录")']
EXPIRED_WORDS = ("二维码已失效", "二维码已过期", "点击刷新")
VERIFY_WORDS = ("身份验证", "安全验证", "验证身份", "验证方式", "刷脸验证", "人脸验证", "扫脸验证")
# what Playwright raises when the page navigated under a DOM call
NAV_ERRORS = ("Execution context was destroyed", "Cannot find context with specified id",
              "navigat", "frame was detached", "from a different document",
              "Element is not attached", "Node is detached")
# fallback crop (fractions of the viewport) if the QR element can't be found
CROP = (0.26, 0.34, 0.46, 0.66)


def say(*parts):
    print(*parts, flush=True)


def under_display():
    """Re-run this script inside xvfb-run when there is no screen, so Chromium can be headful."""
    if os.environ.get("DISPLAY") or os.environ.get("DOUYIN_QR_XVFB"):
        return True
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        say("WARNING: no $DISPLAY and no xvfb-run -- falling back to headless; Douyin may kill the QR")
        return False
    os.environ["DOUYIN_QR_XVFB"] = "1"
    os.execv(xvfb, [xvfb, "-a", "-s", "-screen 0 1280x900x24", sys.executable, *sys.argv])


def kill_previous():
    try:
        old = int(open(PID_PATH).read().strip())
        if old != os.getpid():
            os.kill(old, signal.SIGTERM)
            say("stopped earlier login run", old)
            time.sleep(2)
    except (OSError, ValueError):
        pass
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))


def drop_qr_files():
    for path in glob.glob(QR_GLOB) + [os.path.join(OUT_DIR, "douyin_qr_crop.png")]:
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    headful = under_display()
    kill_previous()
    drop_qr_files()  # nothing from an earlier run may be mistaken for the new QR

    from playwright.sync_api import Error as PwError
    from playwright.sync_api import sync_playwright

    def dom(pg, fn, default=None, tries=5):
        """Run a DOM call, surviving the navigations Douyin does after load and after login."""
        for _ in range(tries):
            try:
                return fn()
            except PwError as e:
                if not any(m.lower() in str(e).lower() for m in NAV_ERRORS):
                    raise
                try:
                    pg.wait_for_load_state("domcontentloaded", timeout=15000)
                except PwError:
                    pass
                pg.wait_for_timeout(1000)
        return default

    def click(pg, loc):
        try:
            dom(pg, lambda: loc.click(timeout=3000))
            return True
        except PwError:  # not there / covered: try the next one
            return False

    def sms_on_its_way(pg):
        """The SMS page says 短信已发送至 ... / 重新发送 once Douyin really sent it"""
        text = page_text(pg)
        return any(w in text for w in ("已发送", "重新发送", "后重新获取", "后重发"))

    def ask_sms(pg):
        """Pick 接收短信验证码 and make sure the SMS really went out. A plain loc.click() once
        printed SMS_SENT while the page still showed the list of 验证方式 (2026-10-29), so: try
        the text, the whole option row, and a real mouse click at its centre, and check each time."""
        label = pg.get_by_text("接收短信验证码").first
        row = label.locator("xpath=ancestor::*[contains(@class,'item') or @role='button' or "
                            "contains(@style,'cursor')][1]")
        for how in ("label", "row", "mouse"):
            try:
                if how == "label":
                    dom(pg, lambda: label.click(timeout=3000))
                elif how == "row":
                    dom(pg, lambda: row.first.click(timeout=3000))
                else:
                    box = dom(pg, lambda: label.bounding_box())
                    if not box:
                        continue
                    pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            except PwError:
                continue
            pg.wait_for_timeout(2500)
            if click(pg, pg.get_by_text("获取验证码", exact=True).first):  # some versions want this too
                pg.wait_for_timeout(2500)
            if sms_on_its_way(pg):
                return True
        return False

    def visible(pg, sel):
        return bool(dom(pg, lambda: pg.locator(sel).first.is_visible(), default=False))

    def page_text(pg):
        return dom(pg, lambda: pg.evaluate("document.body ? document.body.innerText : ''"), default="") or ""

    def logged_in(pg, ctx):
        """Same test as the Space's own working login (streamer/dy_login.py). No DOM guessing:
        an avatar on the page and a missing login button also happen logged OUT (live-stream
        avatars in the feed, the header's 登录 is a <p>), which reported LOGGED_IN with nobody scanning."""
        ls = dom(pg, lambda: pg.evaluate('() => window.localStorage.getItem("HasUserLogin")'))
        if ls == "1":
            return True
        cookies = ctx.cookies("https://www.douyin.com/")
        return any(c["name"] == "LOGIN_STATUS" and c["value"] == "1" for c in cookies) or \
            any(c["name"] in LOGIN_COOKIES and c["value"] for c in cookies)

    def save(ctx):
        cookies = ctx.cookies()
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        try:
            ctx.storage_state(path=STATE_PATH)
        except PwError:
            pass
        say("cookies saved:", COOKIE_PATH, len(cookies), "items")
        say("cookie names:", sorted({c["name"] for c in cookies}))
        say("login cookies:", sorted(LOGIN_COOKIES & {c["name"] for c in cookies if c["value"]}))

    def submit_code(pg, code):
        """Type the SMS code into the 接收短信验证码 dialog and press 验证."""
        for sel in ("input[placeholder*='验证码']", "input[type='tel']", "input[type='number']",
                    "input[inputmode='numeric']"):
            box = pg.locator(sel).filter(visible=True)
            if dom(pg, box.count, default=0):
                try:
                    dom(pg, lambda: box.first.click(timeout=3000))
                    dom(pg, lambda: box.first.fill(""))
                    dom(pg, lambda: box.first.type(code, delay=120))  # typed, so the page sees key events
                except PwError:
                    continue
                pg.wait_for_timeout(800)
                for btn in (pg.get_by_role("button", name="验证", exact=True),
                            pg.get_by_text("验证", exact=True)):
                    if click(pg, btn.filter(visible=True).last):
                        return True
                dom(pg, lambda: pg.keyboard.press("Enter"))
                return True
        # No visible <input> (2026-10-29: COULD NOT TYPE IT): the code field can be a hidden input
        # behind drawn digit boxes. Click where the page says 请输入验证码 / the boxes, then type
        # with the keyboard, which goes to whatever got the focus.
        for target in (pg.get_by_placeholder("验证码"), pg.get_by_text("请输入验证码"),
                       pg.locator("input").filter(has_not=pg.locator("[type=hidden]"))):
            box = dom(pg, lambda: target.first.bounding_box(), default=None)
            if not box:
                continue
            pg.mouse.click(box["x"] + min(box["width"] / 2, 40), box["y"] + box["height"] / 2)
            pg.wait_for_timeout(300)
            pg.keyboard.type(code, delay=120)
            pg.wait_for_timeout(800)
            if code[:2] not in page_text(pg) and not dom(pg, lambda: pg.evaluate(
                    "c => [...document.querySelectorAll('input')].some(i => i.value.includes(c))", code)):
                continue  # the keys went nowhere
            for btn in (pg.get_by_role("button", name="验证", exact=True), pg.get_by_text("验证", exact=True)):
                if click(pg, btn.filter(visible=True).last):
                    return True
            dom(pg, lambda: pg.keyboard.press("Enter"))
            return True
        return False

    def open_login(pg, seconds=20):
        """The panel usually pops up by itself a few seconds after load; if not, click 登录."""
        end = time.time() + seconds
        while time.time() < end:
            if visible(pg, LOGIN_PANEL) or visible(pg, QR_BOX):
                return True
            for sel in LOGIN_BUTTONS:
                if visible(pg, sel) and click(pg, pg.locator(sel).first):
                    say(f"clicked login via {sel}")
                    break
            pg.wait_for_timeout(2000)
        return False

    def qr_src(pg):
        js = f"() => {{ const i = [...document.querySelectorAll('{QR_IMG}')].find(i => i.naturalWidth >= 100); return i ? i.src : ''; }}"
        return dom(pg, lambda: pg.evaluate(js), default="") or ""

    def snap_qr(pg):
        """Screenshot the QR right after it is drawn; returns (path, HH:MM:SS) or (None, None)."""
        # the box shows only a TikTok logo until the QR image arrives: never send that
        ready = f"() => [...document.querySelectorAll('{QR_IMG}')].some(i => i.complete && i.naturalWidth >= 100)"
        try:
            pg.wait_for_function(ready, timeout=30000)
            pg.wait_for_timeout(1000)  # let the image actually paint
        except PwError:
            drop_qr_files()
            shot = os.path.join(OUT_DIR, f"douyin_noqr_{time.strftime('%H%M%S')}.png")
            dom(pg, lambda: pg.screenshot(path=shot))
            say("QR_NOT_LOADED", shot)
            return None, None
        drop_qr_files()
        stamp = time.strftime("%H:%M:%S")
        path = os.path.join(OUT_DIR, f"douyin_qr_{stamp.replace(':', '')}.png")
        try:
            pg.locator(QR_BOX).first.screenshot(path=path, timeout=10000)
        except PwError:  # QR is there but the box moved: clip the usual spot
            w, h = pg.viewport_size["width"], pg.viewport_size["height"]
            box = {"x": int(w * CROP[0]), "y": int(h * CROP[1]),
                   "width": int(w * (CROP[2] - CROP[0])), "height": int(h * (CROP[3] - CROP[1]))}
            try:
                pg.screenshot(path=path, clip=box)
            except PwError:
                return None, None
        try:
            from PIL import Image
            im = Image.open(path)
            im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(path)
        except ImportError:
            pass
        return path, stamp

    wait_seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    sec_uid = os.environ.get("DOUYIN_SEC_UID", "")
    url = f"https://www.douyin.com/user/{sec_uid}" if sec_uid else "https://www.douyin.com/"

    with sync_playwright() as p:
        chrome = os.environ.get("DOUYIN_CHROME") or None  # only for testing with another Chromium
        browser = p.chromium.launch(headless=not headful, executable_path=chrome, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        kw = {"viewport": {"width": 1280, "height": 900}, "locale": "zh-CN"}
        if not headful:  # headless Chromium says "HeadlessChrome" in its UA
            probe = browser.new_page()
            kw["user_agent"] = probe.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            probe.close()
        if os.path.exists(STATE_PATH):
            kw["storage_state"] = STATE_PATH
        ctx = browser.new_context(**kw)
        stealth = next((s for s in STEALTH if os.path.exists(s)), None)
        if stealth:
            ctx.add_init_script(path=stealth)
        else:
            ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        pg = ctx.new_page()
        for attempt in range(3):
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                break
            except PwError as e:
                # with a saved login Douyin redirects while the first page is still loading
                if "interrupted by another navigation" in str(e):
                    break
                if attempt == 2:
                    raise
                say("page load failed, retrying:", str(e).splitlines()[0])
                pg.wait_for_timeout(3000)
        pg.wait_for_timeout(5000)

        if logged_in(pg, ctx):
            say("ALREADY_LOGGED_IN")
            save(ctx)
            browser.close()
            return

        say("login dialog opened:", open_login(pg))
        path, stamp = snap_qr(pg)
        if not path:
            say("ERROR no QR -- send the QR_NOT_LOADED screenshot, say so, offer to retry")
            browser.close()
            return
        say("QR_READY", path, stamp)
        say("SEND THIS PATH NOW. Douyin replaces it 60 s after", stamp, "-- do not run vision_analyze first.")
        last_src, warned = qr_src(pg), ""
        verifying, sms_asked, sms_tries = False, False, 0
        try:
            os.remove(SMS_PATH)  # a code left from an earlier login is useless
        except OSError:
            pass

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            pg.wait_for_timeout(1000)
            if logged_in(pg, ctx):
                pg.wait_for_timeout(3000)  # let the post-login redirect finish writing cookies
                say("LOGGED_IN")
                save(ctx)
                drop_qr_files()
                browser.close()
                return
            text = page_text(pg)
            words = [w for w in VERIFY_WORDS if w in text]
            if words or sms_asked:
                # scanned + confirmed, now Douyin wants 身份验证 (new device). 刷脸 ends in
                # "流程错误" on this server; 接收短信验证码 works -> pick it ourselves
                verifying = True
                drop_qr_files()
                if not sms_asked and sms_tries >= 6 and sms_on_its_way(pg):
                    # someone clicked 接收短信验证码 by hand (XTEST): pick the code up from the file too
                    sms_asked = True
                    deadline = max(deadline, time.time() + SMS_WAIT)
                    shot = os.path.join(OUT_DIR, f"douyin_verify_{time.strftime('%H%M%S')}.png")
                    dom(pg, lambda: pg.screenshot(path=shot))
                    say("SMS_SENT", shot, "(clicked by hand)")
                    say(f"Ask the user for the 6-digit SMS code, then: echo <code> > {SMS_PATH}")
                    continue
                if not sms_asked and "接收短信验证码" in text and sms_tries < 6:
                    sms_tries += 1
                    if ask_sms(pg):
                        sms_asked = True
                        deadline = max(deadline, time.time() + SMS_WAIT)
                        shot = os.path.join(OUT_DIR, f"douyin_verify_{time.strftime('%H%M%S')}.png")
                        dom(pg, lambda: pg.screenshot(path=shot))
                        say("SMS_SENT", shot)
                        say(f"Ask the user for the 6-digit SMS code, then: echo <code> > {SMS_PATH}")
                        continue
                    shot = os.path.join(OUT_DIR, f"douyin_verify_{time.strftime('%H%M%S')}.png")
                    dom(pg, lambda: pg.screenshot(path=shot))
                    say("SMS_CLICK_FAILED", shot, f"try {sms_tries}/6 -- page did not say 短信已发送; trying again")
                    continue
                if sms_asked and os.path.exists(SMS_PATH):
                    code = "".join(ch for ch in open(SMS_PATH).read() if ch.isdigit())
                    os.remove(SMS_PATH)
                    if 4 <= len(code) <= 8:
                        say("SMS_SUBMITTED", code, "->", "ok" if submit_code(pg, code) else "COULD NOT TYPE IT")
                        pg.wait_for_timeout(5000)
                        shot = os.path.join(OUT_DIR, f"douyin_verify_{time.strftime('%H%M%S')}.png")
                        dom(pg, lambda: pg.screenshot(path=shot))
                        say("SMS_RESULT", shot, "(LOGGED_IN follows if it worked)")
                    else:
                        say("SMS_BAD_CODE", repr(code), "-- need the 4-8 digits from the SMS")
                    continue
                if words and ",".join(words) != warned:
                    warned = ",".join(words)
                    shot = os.path.join(OUT_DIR, f"douyin_verify_{time.strftime('%H%M%S')}.png")
                    dom(pg, lambda: pg.screenshot(path=shot))
                    say("VERIFY", shot, warned)
                continue
            if verifying:
                continue  # the QR is gone for good once 身份验证 started
            if any(w in text for w in EXPIRED_WORDS) and visible(pg, QR_BOX):
                # older page versions grey the QR out and show a refresh button.
                # Clicking 刷新 often does NOTHING (modal stays 已过期, <img> src unchanged)
                # -> reload the page and reopen the login panel to get a fresh code
                say("QR_EXPIRED", path)
                drop_qr_files()
                path = None
                for w in ("点击刷新", "刷新"):
                    if click(pg, pg.get_by_text(w).first):
                        break
                pg.wait_for_timeout(1500)
                src_after = qr_src(pg)
                if not src_after or src_after == last_src:
                    dom(pg, lambda: pg.reload(wait_until="domcontentloaded"))
                    pg.wait_for_timeout(4000)
                    open_login(pg, seconds=10)
                path, stamp = snap_qr(pg)
                last_src = qr_src(pg)
                if path:
                    say("QR_REFRESHED", path, stamp)
                continue
            src = qr_src(pg)
            if src and src != last_src:
                # Douyin silently swaps the QR every 60 s (check_qrconnect hands out a new one,
                # no "expired" text): the image sent a minute ago is dead now
                if path and os.path.exists(path):
                    say("QR_EXPIRED", path)
                path, stamp = snap_qr(pg)
                last_src = qr_src(pg)
                if path:
                    say("QR_REFRESHED", path, stamp)
        else:
            say("TIMEOUT")
        drop_qr_files()
        browser.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            if open(PID_PATH).read().strip() == str(os.getpid()):
                os.remove(PID_PATH)
        except OSError:
            pass

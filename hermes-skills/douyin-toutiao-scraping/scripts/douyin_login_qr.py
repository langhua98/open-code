#!/usr/bin/env python3
"""Douyin login-QR harvester (Playwright headless).

Opens a Douyin profile, triggers the login modal, screenshot-crops the QR code
to a PNG the user can scan, then polls until login succeeds and dumps cookies.

Usage:
    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 douyin_login_qr.py [timeout_seconds]

Prints one status line per event (read them from the background process output):
    ALREADY_LOGGED_IN   saved state is still valid -- no scan needed, cookies refreshed
    QR_READY <path>     QR crop saved -> verify with vision_analyze, then SEND it
    QR_REFRESHED <path> QR expired and Douyin drew a new one -> send the new image
    LOGGED_IN           login confirmed, cookies saved
    TIMEOUT             nobody scanned in time (cookies NOT overwritten)

Outputs:
    /home/user/douyin_login_full.png   full viewport screenshot (debug)
    /home/user/douyin_qr_crop.png      2x-upscaled QR crop -> SEND THIS to the user
    ~/.douyin_cookies.json             cookie list (ctx.cookies())
    ~/.douyin_state.json               storage_state for later ctx reuse

Hard-won details (do not "fix" these back):
  * Canvas/`<img>` QR extraction returns a BLANK 1.5KB PNG on douyin.com. Don't
    trust it. Screenshot the viewport, then crop the modal region.
  * Login modal is centered; QR sits at roughly x 26%-46%, y 34%-66% of a
    1280x900 viewport. Crop that, resize 2x LANCZOS, and verify with
    vision_analyze before sending -- a blank crop is silent otherwise.
  * Scan-only login yields NO `sessionid` / `sessionid_ss` cookie (the user must
    tap confirm in the app). Verify login by DOM (avatar / logout button)
    as well as by cookie name.
  * "Execution context was destroyed, most likely because of a navigation":
    Douyin reloads / redirects the page right after the scan is confirmed, and on
    a second run (state already saved) right after load. Any DOM call made in
    that window raises. Never call pg.query_selector()/evaluate() bare: go
    through dom() below, which waits for the new page to settle and retries.
    Cookie checks (ctx.cookies()) never break on navigation -- check them first.
  * Second run: load ~/.douyin_state.json first and check whether it is still
    logged in. Only show a new QR if it is not. Kill leftover Chromium from an
    earlier run before starting (two browsers on one profile fight each other).
"""
import json
import os
import subprocess
import sys
import time

from playwright.sync_api import Error as PwError
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
COOKIE_PATH = os.path.expanduser("~/.douyin_cookies.json")
STATE_PATH = os.path.expanduser("~/.douyin_state.json")
QR_PATH = "/home/user/douyin_qr_crop.png"
FULL_PATH = "/home/user/douyin_login_full.png"
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "uid_tt"}
LOGIN_BUTTONS = ['#douyin-header-menuCt [data-e2e="login-button"]',
                 '[data-e2e="login-button"]',
                 'button:has-text("登录")']
AVATAR = '[data-e2e="live-avatar"], [data-e2e="user-info"]'
# what Playwright raises when the page navigated under a DOM call
NAV_ERRORS = ("Execution context was destroyed", "Cannot find context with specified id",
              "navigat", "frame was detached", "from a different document",
              "Element is not attached", "Node is detached")

# crop box as fractions of the viewport (see module docstring)
CROP = (0.26, 0.34, 0.46, 0.66)


def say(*parts):
    print(*parts, flush=True)


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


def has_login_cookie(ctx):
    return bool(LOGIN_COOKIES & {c["name"] for c in ctx.cookies()})


def logged_in(pg, ctx):
    if has_login_cookie(ctx):
        return True
    avatar = dom(pg, lambda: pg.query_selector(AVATAR))
    button = dom(pg, lambda: pg.query_selector('[data-e2e="login-button"]'))
    return bool(avatar) and not button


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


def snap_qr(pg):
    pg.screenshot(path=FULL_PATH)
    w, h = pg.viewport_size["width"], pg.viewport_size["height"]
    box = {"x": int(w * CROP[0]), "y": int(h * CROP[1]),
           "width": int(w * (CROP[2] - CROP[0])), "height": int(h * (CROP[3] - CROP[1]))}
    pg.screenshot(path=QR_PATH, clip=box)
    try:
        from PIL import Image
        im = Image.open(QR_PATH)
        im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(QR_PATH)
    except ImportError:
        pass
    return open(QR_PATH, "rb").read()


def open_login(pg):
    for sel in LOGIN_BUTTONS:
        el = dom(pg, lambda: pg.query_selector(sel))
        if el and dom(pg, el.is_visible, default=False):
            dom(pg, el.click)
            say(f"clicked login via {sel}")
            pg.wait_for_timeout(4000)
            return True
    return False


def main():
    wait_seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    sec_uid = os.environ.get("DOUYIN_SEC_UID", "")
    url = f"https://www.douyin.com/user/{sec_uid}" if sec_uid else "https://www.douyin.com/"

    # a Chromium left over from an earlier run keeps the old page alive and fights this one
    # (only browsers from our own PLAYWRIGHT_BROWSERS_PATH: the Space's video crawler runs its own Chromium)
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", os.path.expanduser("~/.cache/ms-playwright"))
    subprocess.run(["pkill", "-f", browsers], check=False)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        kw = {"user_agent": UA, "viewport": {"width": 1280, "height": 900}, "locale": "zh-CN"}
        if os.path.exists(STATE_PATH):
            kw["storage_state"] = STATE_PATH
        ctx = browser.new_context(**kw)
        pg = ctx.new_page()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PwError as e:
            # with a saved login Douyin redirects while the first page is still loading
            if "interrupted by another navigation" not in str(e):
                raise
        pg.wait_for_timeout(5000)
        dom(pg, lambda: pg.wait_for_load_state("domcontentloaded"))

        if os.path.exists(STATE_PATH) and logged_in(pg, ctx):
            say("ALREADY_LOGGED_IN")
            save(ctx)
            browser.close()
            return

        say("login dialog opened:", open_login(pg))
        last = snap_qr(pg)
        say("QR_READY", QR_PATH)
        say("VERIFY the crop with vision_analyze before sending -- blank crops are silent.")

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            pg.wait_for_timeout(3000)
            if logged_in(pg, ctx):
                pg.wait_for_timeout(3000)  # let the post-login redirect finish writing cookies
                say("LOGGED_IN")
                save(ctx)
                browser.close()
                return
            # the QR expires after ~2 minutes; Douyin shows a refresh button on the modal
            refresh = dom(pg, lambda: pg.query_selector('text=/点击刷新|二维码已失效|二维码已过期/'))
            if refresh:
                dom(pg, refresh.click)
                pg.wait_for_timeout(3000)
                if not dom(pg, lambda: pg.query_selector('[class*="login"], [id*="login"]')):
                    open_login(pg)
                img = snap_qr(pg)
                if img != last:
                    last = img
                    say("QR_REFRESHED", QR_PATH)

        say("TIMEOUT")
        browser.close()


if __name__ == "__main__":
    main()

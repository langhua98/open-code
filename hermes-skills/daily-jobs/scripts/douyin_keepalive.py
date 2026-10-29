#!/usr/bin/env python3
"""抖音登录保活：每天开一次抖音（带着 ~/.douyin_state.json），确认还是登录状态，顺手把刷新过的登录存回去。

给 Hermes 的定时任务用（cronjob no_agent=True：输出原样发给用户，不经过大模型，不花 token）：
    cp douyin_keepalive.py douyin_keepalive.sh ~/.hermes/scripts/
    cronjob create schedule="0 10 * * *" script="douyin_keepalive.sh" no_agent=true name="抖音登录保活"

还登录着、离过期还远：什么也不打印（定时任务不发消息）。掉线了、或者 7 天内要过期：打印一句话提醒用户
回「登录抖音」重新扫码。只认真正的登录（localStorage HasUserLogin=1、LOGIN_STATUS=1 或非空 sessionid），
和 douyin_login_qr.py 同一套判断；页面上有没有头像不算。

手动跑：python3 douyin_keepalive.py [-v]     -v：还登录着也打印一行
"""
import json
import os
import shutil
import sys
import time

STATE = os.path.expanduser("~/.douyin_state.json")
COOKIES = os.path.expanduser("~/.douyin_cookies.json")
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}
STEALTH = ["/opt/MediaCrawler/libs/stealth.min.js"]
WARN_DAYS = 7
RELOGIN = "回我「登录抖音」，我发二维码给你重新扫一次。"


def expires_in_days(cookies):
    """sid_guard 的值是 <sid>|<签发时间>|<有效秒数>|<日期>；拿不到就看 sessionid 的 expires。"""
    for c in cookies:
        if c.get("name") == "sid_guard" and c.get("value"):
            parts = c["value"].replace("%7C", "|").split("|")
            try:
                return (int(parts[1]) + int(parts[2]) - time.time()) / 86400
            except (IndexError, ValueError):
                pass
    for c in cookies:
        if c.get("name") == "sessionid" and (c.get("expires") or 0) > 0:
            return (c["expires"] - time.time()) / 86400
    return None


def under_display():
    if os.environ.get("DISPLAY") or os.environ.get("DOUYIN_QR_XVFB"):
        return True
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        return False
    os.environ["DOUYIN_QR_XVFB"] = "1"
    os.execv(xvfb, [xvfb, "-a", "-s", "-screen 0 1280x900x24", sys.executable, *sys.argv])


def main():
    verbose = "-v" in sys.argv[1:]
    if not os.path.exists(STATE):
        print("抖音还没登录过（没有保存的登录）。" + RELOGIN)
        return 0
    headful = under_display()
    from playwright.sync_api import Error as PwError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful, executable_path=os.environ.get("DOUYIN_CHROME") or None,
                                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(storage_state=STATE, viewport={"width": 1280, "height": 900}, locale="zh-CN")
        stealth = next((s for s in STEALTH if os.path.exists(s)), None)
        if stealth:
            ctx.add_init_script(path=stealth)
        pg = ctx.new_page()
        for attempt in range(3):
            try:
                pg.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
                break
            except PwError as e:
                if "interrupted by another navigation" in str(e):
                    break
                if attempt == 2:
                    print(f"抖音打不开（{str(e).splitlines()[0][:80]}），明天再查。", file=sys.stderr)
                    return 1  # network trouble is not "logged out": stay quiet
                pg.wait_for_timeout(5000)
        pg.wait_for_timeout(8000)
        ls = None
        for _ in range(3):
            try:
                ls = pg.evaluate('() => window.localStorage.getItem("HasUserLogin")')
                break
            except PwError:  # the page navigated under us
                pg.wait_for_timeout(2000)
        cookies = ctx.cookies("https://www.douyin.com/")
        ok = ls == "1" or any(c["name"] == "LOGIN_STATUS" and c["value"] == "1" for c in cookies) or \
            any(c["name"] in LOGIN_COOKIES and c["value"] for c in cookies)
        if ok:
            # keep the refreshed cookies so the login lives on
            ctx.storage_state(path=STATE)
            with open(COOKIES, "w", encoding="utf-8") as f:
                json.dump(ctx.cookies(), f, ensure_ascii=False, indent=2)
        browser.close()

    days = expires_in_days(cookies) if ok else None
    if not ok:
        print("⚠️ 抖音登录掉了（今天检查时已经不是登录状态）。" + RELOGIN)
    elif days is not None and days < WARN_DAYS:
        print(f"⏰ 抖音登录还有 {max(days, 0):.0f} 天过期。" + RELOGIN)
    elif verbose:
        print("抖音登录正常" + (f"，还有约 {days:.0f} 天过期" if days is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""每日热榜：抖音热榜 + 今日头条热榜前 N 条，打印成一条能直接发微信的消息。

给 Hermes 的定时任务用（cronjob no_agent=True，脚本的输出原样发给用户，不经过大模型，不花 token）：
    cp daily_hot.py ~/.hermes/scripts/
    cronjob create schedule="0 8 * * *" script="daily_hot.py" no_agent=true name="每日热榜"

手动跑：python3 daily_hot.py [N]      N 默认 20（每个榜）
只用标准库，哪个 Python 都能跑。两个榜都拿不到时什么也不打印（定时任务就不发空消息），错误写到标准错误。
"""
import json
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DOUYIN = ("https://www.douyin.com/aweme/v1/web/hot/search/list/"
          "?device_platform=webapp&aid=6383&channel=channel_pc_web")
TOUTIAO = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"


def get_json(url, referer=None, tries=3):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except OSError:  # connection reset now and then: try again
            if i == tries - 1:
                raise
            time.sleep(3)


def heat(v):
    return f"{v / 10000:.0f}万" if isinstance(v, (int, float)) and v >= 10000 else str(v or "")


def douyin(n):
    d = get_json(DOUYIN, "https://www.douyin.com/")
    inner = d.get("data") or {}
    words = inner.get("word_list") or (inner.get("data") or {}).get("word_list") or []
    return [f"{i}. {w.get('word', '')}  🔥{heat(w.get('hot_value'))}" for i, w in enumerate(words[:n], 1)]


def toutiao(n):
    d = get_json(TOUTIAO)
    return [f"{i}. {x.get('Title', '')}" for i, x in enumerate((d.get("data") or [])[:n], 1)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    parts = []
    for name, fn in (("抖音热榜", douyin), ("头条热榜", toutiao)):
        try:
            lines = fn(n)
        except Exception as e:  # noqa: BLE001 -- one board down shouldn't kill the other
            print(f"{name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if lines:
            parts.append(f"【{name}】\n" + "\n".join(lines))
    if parts:
        print(f"📰 今日热榜 {time.strftime('%m-%d')}\n\n" + "\n\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())

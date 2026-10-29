---
name: daily-jobs
description: Set up the owner's daily automatic jobs - the morning 抖音/头条 hot list push and the daily Douyin login keep-alive check - as zero-token cron jobs (no_agent scripts). Use when the user asks for 每日热榜 / 定时推送 / 登录保活 / 每天检查登录, or to list/stop those jobs.
---

# 每天自动跑的活（不花 token）

Both jobs are **`no_agent` cron jobs**: the script runs on schedule and its output is sent to the user
as is. No model call, no tokens. Empty output = nothing is sent.

## Install (once, and again after these files are updated)
```bash
mkdir -p ~/.hermes/scripts
cp ~/.hermes/skills/daily-jobs/scripts/daily_hot.py \
   ~/.hermes/skills/daily-jobs/scripts/douyin_keepalive.py \
   ~/.hermes/skills/daily-jobs/scripts/douyin_keepalive.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/douyin_keepalive.sh
python3 ~/.hermes/scripts/daily_hot.py 3          # quick check: prints a short hot list
bash ~/.hermes/scripts/douyin_keepalive.sh -v     # quick check: 抖音登录正常 / 掉了
```
(Cron scripts must live in `~/.hermes/scripts/` and are named relative to it.)

## Create the jobs — from the user's WeChat chat, so the output goes back to them
Use the `cronjob` tool, `action="create"`, leave `deliver` out (= this chat):

| name | schedule | script | no_agent |
|---|---|---|---|
| 每日热榜 | `0 8 * * *` | `daily_hot.py` | `true` |
| 抖音登录保活 | `0 10 * * *` | `douyin_keepalive.sh` | `true` |

`cronjob action="list"` first — don't create a second copy of a job that exists. Change the time if
the user asks (cron syntax, server time; Beijing = UTC+8 if the server is on UTC: 8:00 北京 = `0 0 * * *` UTC).
Check the server's timezone with `date` before picking the hour, and tell the user the time in 北京时间.

## What they do
- **每日热榜**: Douyin hot list + Toutiao hot board, top 20 each, one message. `daily_hot.py N` for another size.
- **抖音登录保活**: opens douyin.com with `~/.douyin_state.json`, checks the REAL login (HasUserLogin /
  LOGIN_STATUS / sessionid — not the page's avatar), saves the refreshed cookies back. Silent when fine.
  Says "抖音登录掉了 / 还有 N 天过期，回我「登录抖音」" when it isn't. When the user then says 登录抖音, run
  the normal QR login (`douyin-toutiao-scraping` skill). A cron job can't do the QR itself: nobody's
  there to scan within 60 s.

## Stop / change
`cronjob action="list"` → find the id → `action="pause" | "resume" | "remove"` / `"update"` with that id.
Never guess ids.

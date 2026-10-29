---
name: daily-jobs
description: Set up the owner's daily automatic jobs - the morning 抖音热点 top-10 videos (sent as video files), the 抖音/头条 hot list text push, and the daily Douyin login keep-alive check - as zero-token cron jobs (no_agent scripts). Use when the user asks for 每日热榜 / 热点视频 / 定时推送 / 登录保活 / 每天检查登录, or to list/stop those jobs.
---

# 每天自动跑的活（不花 token）

Both jobs are **`no_agent` cron jobs**: the script runs on schedule and its output is sent to the user
as is. No model call, no tokens. Empty output = nothing is sent.

## Install (once, and again after these files are updated)
```bash
mkdir -p ~/.hermes/scripts
cd ~/.hermes/skills/daily-jobs/scripts
cp daily_hot.py daily_hot_videos.py daily_hot_videos.sh douyin_keepalive.py douyin_keepalive.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/*.sh
python3 ~/.hermes/scripts/daily_hot.py 3          # quick check: prints a short hot list
bash ~/.hermes/scripts/daily_hot_videos.sh 2      # quick check: 2 hot videos (needs the Douyin login)
bash ~/.hermes/scripts/douyin_keepalive.sh -v     # quick check: 抖音登录正常 / 掉了
```
(Cron scripts must live in `~/.hermes/scripts/` and are named relative to it.)

## Create the jobs — from the user's WeChat chat, so the output goes back to them
Use the `cronjob` tool, `action="create"`, leave `deliver` out (= this chat):

| name | schedule | script | no_agent |
|---|---|---|---|
| 每日热榜 | `0 8 * * *` | `daily_hot_videos.sh` | `true` |
| 抖音登录保活 | `0 10 * * *` | `douyin_keepalive.sh` | `true` |

`cronjob action="list"` first — don't create a second copy of a job that exists. Change the time if
the user asks (cron syntax, server time; Beijing = UTC+8 if the server is on UTC: 8:00 北京 = `0 0 * * *` UTC).
Check the server's timezone with `date` before picking the hour, and tell the user the time in 北京时间.

## What they do
- **每日热榜** (the user wants this one): `daily_hot_videos.sh` — Douyin hot list top 10, and **each item's video sent as a
  file** (the user said: no links, they want to watch right away). It opens each hot item's video page
  with the saved login, downloads the video (H.264, ≤15 MB, else ffmpeg shrinks it to 540p) to
  `/home/user/hot_videos/`, prints the list plus one `MEDIA:` line per video. Items it couldn't get are
  named at the end of the text. Needs the real Douyin login; without it, it says so and sends no videos.
  Takes a few minutes. `daily_hot_videos.sh N` for another count.
  The old text-only `daily_hot.py` (Douyin + Toutiao top 20) is still there if the user asks for text.
- **抖音登录保活**: opens douyin.com with `~/.douyin_state.json`, checks the REAL login (HasUserLogin /
  LOGIN_STATUS / sessionid — not the page's avatar), saves the refreshed cookies back. Silent when fine.
  Says "抖音登录掉了 / 还有 N 天过期，回我「登录抖音」" when it isn't. When the user then says 登录抖音, run
  the normal QR login (`douyin-toutiao-scraping` skill). A cron job can't do the QR itself: nobody's
  there to scan within 60 s.

## Stop / change
`cronjob action="list"` → find the id → `action="pause" | "resume" | "remove"` / `"update"` with that id.
Never guess ids.

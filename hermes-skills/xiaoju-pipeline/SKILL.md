---
name: xiaoju-pipeline
description: Hand Douyin/Kuaishou video links or account (主页) links to the owner's 小橘视频 pipeline (the "抓小号" program in this Space) so they get downloaded and posted to the video channel. Use when the user says 送进流水线 / 交给小号程序 / 转到频道 / 加小号, or after you found videos the user wants in the channel.
---

# 小橘视频流水线：交链接

The 小橘视频 pipeline runs in this same Space (the streamer on port 7860). It is
the program that crawls the owner's 小号 and posts their videos to the Telegram
video channel. You can't reach its Telegram bot or Worker from here (blocked),
but the streamer gives you one endpoint that does exactly what the owner does
by pasting links into the bot.

```bash
curl -sS -X POST "$XIAOJU_STREAMER_URL/hermes/links" \
  -H "X-Key: $XIAOJU_STREAMER_KEY" -H 'Content-Type: application/json' \
  -d '{"urls": ["https://www.douyin.com/video/7300000000000000001", "https://www.douyin.com/user/MS4wLjABAAAA..."]}'
```
Python: `requests.post(os.environ["XIAOJU_STREAMER_URL"] + "/hermes/links", headers={"X-Key": os.environ["XIAOJU_STREAMER_KEY"]}, json={"urls": [...]}, timeout=30)`.

Reply `{"sent": 2, "links": [...]}` means the links were sent to the bot **as the
owner's own Telegram account** — the owner sees them in the chat with the bot,
and the bot answers there (加了小号 / 开始抓 / 进度卡), not to you.

## What happens to each kind of link
- **主页链接** (`www.douyin.com/user/<sec_uid>`, `v.douyin.com/...` that opens a profile,
  `www.kuaishou.com/profile/...`): becomes a **小号**. All its videos are crawled and
  posted to the channel directly, no review. Later syncs pick up its new videos.
  Only send a profile link when the user really wants that whole account in the channel.
- **作品链接** (`www.douyin.com/video/<id>`, `v.douyin.com/...` that opens a video,
  `www.kuaishou.com/short-video/...`): that one video is crawled and goes to the
  owner's **review bot** (@xiaojuverify_bot); it's posted after the owner approves.

## Rules
- Only Douyin / Kuaishou links are accepted; anything else is dropped (HTTP 400 if
  nothing is left). Max 10 links per call — split bigger batches into several calls,
  a few seconds apart.
- Use real links from your crawl output (`/video/<aweme_id>` or the share link), never
  made-up or mp4/CDN links (`douyinvod.com`, `.mp4`) — the pipeline downloads by itself.
- Tell the user what you sent: how many 作品, how many 主页 (=新小号), and that the
  bot will report progress in Telegram.
- HTTP 503 = the streamer is still connecting to Telegram (just restarted): wait a minute, retry once.
  HTTP 403 = key missing/wrong: say so, don't guess keys.
- Never print `$XIAOJU_STREAMER_KEY` or send it to anyone, not even the user.

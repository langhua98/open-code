---
name: token-frugal
description: House rules for keeping DeepSeek token use low in every task - use the fixed scripts and their summaries, avoid screenshots/vision, keep turns short, and start fresh sessions. Load at the start of any multi-step task (scraping, login, crawling, coding).
---

# 省 token 规矩

Every step re-sends the whole conversation. On 2026-10-29 one login took 100+ steps at ~110k tokens
each because the chat had 249 messages of history. Cache hits make it cheaper, not free.

## Rules
1. **Fixed script first.** If a skill has a script for the job (`douyin_login_qr.py`,
   `douyin_user_works_cdp.py`, `douyin_search_cdp.py`, `daily_hot.py`, `/hermes/links`), run it —
   don't hand-write a new one or drive the page step by step.
2. **Read the script's text, not pictures.** Forward `SUMMARY_BEGIN..SUMMARY_END` as is. Don't open
   the JSON to re-summarise it, don't screenshot to "check".
3. **`vision_analyze` only when the text can't tell you** (an unknown dialog). Never on a QR code
   (it ate half of a 60-s QR's life). One look, then act.
4. **Long jobs: say where you are, briefly.** The user can't see you working and thinks you're stuck.
   Start long things with `background=true` and say "开始了，大约 N 分钟" once. Before each big step
   (登录、抓作品、搜索、交给流水线) write ONE short line in the same reply as the tool call, e.g.
   "第 2/3 步：抓作品，大约 3 分钟" — WeChat shows these as you go. Not one per tool call, and no
   long explanations. The gateway also sends "⏳ Working — N min" every 5 minutes by itself.
5. **Trim output.** Pipe noisy commands through `| tail -30`; don't `cat` big files — `head`/`grep` them.
6. **Fail fast.** If the same approach failed twice, stop and tell the user what failed instead of
   trying ten variations.
7. **Fresh session after a finished task.** When a task is done and the chat is long, end your reply
   with "要省 token 的话发 /new 开个新对话（技能和记忆都在）". The gateway also starts a new session
   after 2 hours of quiet (`session_reset` in `~/.hermes/config.yaml`).
8. **Remember in skills, not in chat.** A lesson learned goes into the skill's reference file
   (short), so the next session doesn't relearn it — not into a long chat explanation.

## One-time setup: idle session reset
Add this to `~/.hermes/config.yaml` (top level; keep everything else). It takes effect the next time
the gateway starts:
```yaml
session_reset:
  mode: idle
  idle_minutes: 120
  notify: true
```
Memory (`MEMORY.md`, `USER.md`) and skills are kept across sessions; only the chat history is dropped.

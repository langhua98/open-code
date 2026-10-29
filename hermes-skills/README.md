# Hermes 技能补丁

douyin-proxy Space 里的 Hermes（微信助手）自己写的技能，这里放修好的文件，让它下载后覆盖 `~/.hermes/skills/` 里同名的文件。
只放改过的文件，其余文件（含账号信息的参考笔记）留在 Hermes 那边，不进这个公开仓库。

- `douyin-toutiao-scraping/`：抖音扫码登录第二次报 `Execution context was destroyed` 的修复。
  `scripts/douyin_login_qr.py` 的 DOM 调用都经过 `dom()`：页面跳转时等新页面加载完再重试；先用已保存的登录
  （`ALREADY_LOGGED_IN`）；二维码过期自动刷新（`QR_REFRESHED`）。`SKILL.md`、`references/qr-login.md` 写了这些坑。
- 二维码一扫就"已过期"的修复：抖音每张二维码只管 60 秒，到点页面悄悄换一张、不提示；以前截完图要将近一分钟才发出去，到手就作废了。
  现在脚本盯着二维码图片，一换就截新图报 `QR_REFRESHED`；改成虚拟屏幕上的真浏览器（`xvfb-run`，和 Space 里视频爬虫登录抖音同一套办法），
  二维码真加载出来才截图；文件名带生成时间（`/home/user/douyin_qr_<时分秒>.png`），过期、换新、结束时旧图都删掉，
  发不出旧图；`SKILL.md` 让 Hermes 一看到 `QR_READY` 就发，不再先用 vision_analyze 看一遍。
- `xiaoju-pipeline/`：新技能。把抓到的抖音、快手作品链接或小号主页链接交给 Space 里的小橘视频流水线
  （`POST $XIAOJU_STREAMER_URL/hermes/links`，流式服务用频道主账号转发给机器人，和频道主自己粘贴链接一样）。
- 一次教五个技能（2026-10-29）：
  - `douyin-toutiao-scraping/`：登录脚本自己选「接收短信验证码」，用户把验证码发来后写进 `~/.douyin_sms_code`，脚本自动填好、点验证；
    二维码点刷新没反应时重新加载页面。`douyin_user_works_cdp.py`（一句话抓全部作品：表格 + 现成的摘要）、
    `douyin_search_cdp.py`（关键词搜索，按最新发布或最多点赞排，可限定 N 天内）。
    `references/login-verification.md` 重写：以前要求"同步后重打补丁"，现在不用打了。
  - `daily-jobs/`：每日热榜、抖音登录保活，都是 no_agent 定时任务，脚本的输出直接发给用户，不经过大模型。
  - `token-frugal/`：省 token 的规矩，外加闲置 2 小时自动开新会话（`session_reset`）。
- `free-media-gen/`：免费生图和图生视频（2026-10-29）。`gen_image.py`：Pollinations 免费出图（不要 key，同一 IP 45 秒一张，
  脚本自己等），失败了用 HF 的 Z-Image-Turbo（中文提示词、能在图里写中文字）。`img2video.py`：HF ZeroGPU 上的
  Wan 2.2 快速版，失败了换 LTX-Video。视频和 Z-Image 要用户自己的 HF 免费 token（存 `~/.hermes/hf_token`），
  免费账号每天有几分钟 GPU 时间。

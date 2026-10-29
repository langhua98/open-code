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

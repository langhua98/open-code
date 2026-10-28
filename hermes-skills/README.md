# Hermes 技能补丁

douyin-proxy Space 里的 Hermes（微信助手）自己写的技能，这里放修好的文件，让它下载后覆盖 `~/.hermes/skills/` 里同名的文件。
只放改过的文件，其余文件（含账号信息的参考笔记）留在 Hermes 那边，不进这个公开仓库。

- `douyin-toutiao-scraping/`：抖音扫码登录第二次报 `Execution context was destroyed` 的修复。
  `scripts/douyin_login_qr.py` 的 DOM 调用都经过 `dom()`：页面跳转时等新页面加载完再重试；先用已保存的登录
  （`ALREADY_LOGGED_IN`）；二维码过期自动刷新（`QR_REFRESHED`）。`SKILL.md`、`references/qr-login.md` 写了这些坑。

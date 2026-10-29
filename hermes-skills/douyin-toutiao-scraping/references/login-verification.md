# 登录真假、身份验证（短信）、登录后抓作品（2026-10 实战，已并进脚本）

这份替换掉之前自己写的同名笔记。以前笔记 §8 说"每次从 GitHub 同步完都要重新打三个补丁"，
**现在不用打了，也不要打**：三个补丁都已经并进仓库里的脚本。尤其不要再把 `AVATAR` 头像判断加回
`logged_in()`：新脚本里已经没有 `AVATAR` 这个常量，加回去会直接 `NameError` 崩掉。

## 1. 什么算真登录

只认这三样之一（`douyin_login_qr.py`、`douyin_keepalive.py`、流水线的 `dy_login.py` 用的是同一套）：
- localStorage `HasUserLogin` == "1"
- cookie `LOGIN_STATUS` == "1"
- 非空的 `sessionid` / `sessionid_ss` / `sid_tt` / `sid_guard`

页面上有头像、找不到登录按钮，这些**都不算**：个人主页上 `[data-e2e="user-info"]` 是博主本人的资料块，
没登录也会显示；顶部的登录入口是 `<p>登录</p>`，不是 `[data-e2e="login-button"]`。旧判断就是这样，
没人扫码也报了 `LOGGED_IN`。

脚本在 `LOGGED_IN` 后会打印 `login cookies: [...]`，**是空的 `[]` 就不是真登录**，不能跟用户说成功。
如果之前存过假登录：删掉 `~/.douyin_state.json` 和 `~/.douyin_cookies.json` 再重新登录。

## 2. 扫码之后的「身份验证」：脚本自己选短信

新设备扫码、在手机上确认后，网页会弹出「身份验证」，有三个选项：手机刷脸验证、接收短信验证码、
验证登录密码。**在这台服务器上选刷脸会报「流程错误」，选短信能过。**

现在脚本会自己处理（页面是它自己的，直接用 Playwright 点，不需要 XTEST，也不需要截图找坐标）：
1. 看到「接收短信验证码」就点它，打印 `SMS_SENT <截图>`。这时短信已经发到用户手机上。
2. 你问用户要 6 位验证码，然后执行 `echo 258902 > ~/.douyin_sms_code`（数字换成用户发来的）。
3. 脚本读到这个文件，把验证码填进去、点「验证」，打印 `SMS_SUBMITTED <码> -> ok` 和 `SMS_RESULT <截图>`。
   验证通过的话，接着就会打印 `LOGGED_IN`。
4. 码填错或者过期了，就再问用户要一次，再写一次文件就行，脚本还在等（发短信后至少等 5 分钟）。

不要为这一步杀掉登录脚本：扫码结果只存在它那个浏览器里，杀掉就得让用户从头再扫一遍。
`scripts/xinput.py` 和 `references/xvfb-browser-control.md`（XTEST 点虚拟屏）留着备用，
只有脚本自己点不动的时候才用。

弹窗里显示的账号可能是用户的另一个号（比如「坏脾气小橘🍊」），不一定是要抓的那个号。
用哪个号登录都能抓公开作品，但要跟用户说一声。

## 3. 登录后取作品 JSON：只有 CDP 这一条路走得通

| 方法 | 结果 |
| --- | --- |
| `pg.on("response")` 里 `resp.text()` | 正文长度是 0 |
| 拿页面的签名 URL 用 `requests` / `ctx.request` 重新请求 | `403 Sign Invalid`（`a_bogus` 只能用一次） |
| 在页面里 `fetch(url)` | 拿回来的是 HTML，不是 JSON |
| **CDP `Network.getResponseBody`** | ✅ 能用（`base64Encoded` 为真时先解码） |

`scripts/douyin_user_works_cdp.py`（作品）和 `scripts/douyin_search_cdp.py`（搜索）都用这个办法。

## 4. 翻页

真登录后每页 20 条，`has_more=1`。只用 `mouse.wheel` 翻两页就会停。现在的做法：同时用 wheel、
对所有能滚的 div 执行 `scrollTo`、`window.scrollTo`，每轮等 2.5 秒，连续 20 轮都没有新的一页才放弃。
实测 193/193 条、11 页（已经写进 `douyin_user_works_cdp.py`）。

没登录（或者假登录）的时候翻不动：只有 1 次请求、8 条，而且是"猜你喜欢"之类混进来的数据，不是这个号的作品。

## 5. 环境
- 这台机器**没有 `pkill` / `pgrep` / `xdotool`**。脚本用 pid 文件 `~/.douyin_login.pid` 停掉上一次的登录。
- 二维码 60 秒换一张。看到 `QR_READY` / `QR_REFRESHED` 就马上发，不要先用 vision_analyze 看图。

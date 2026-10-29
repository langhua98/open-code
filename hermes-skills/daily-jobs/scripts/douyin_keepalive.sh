#!/bin/bash
# Hermes 定时任务的入口（脚本必须放在 ~/.hermes/scripts/）。用镜像自带的 /opt/mc-venv：
# 它装好了 Playwright 和 Chromium（/opt/pw-browsers），重启也在；pip 装进 python3 的重启就没了
if [ -x /opt/mc-venv/bin/python ]; then
  export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
  exec /opt/mc-venv/bin/python "$HOME/.hermes/scripts/douyin_keepalive.py" "$@"
fi
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
exec python3 "$HOME/.hermes/scripts/douyin_keepalive.py" "$@"

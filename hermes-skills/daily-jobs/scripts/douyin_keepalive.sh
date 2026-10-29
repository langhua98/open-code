#!/bin/bash
# Hermes 定时任务的入口（脚本必须放在 ~/.hermes/scripts/）：用装了 Playwright 的 python3 跑保活检查
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
exec python3 "$HOME/.hermes/scripts/douyin_keepalive.py" "$@"

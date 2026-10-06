#!/usr/bin/env bash
# Runs every time the codespace starts: serves the OpenCode web UI on port 4096,
# which Codespaces forwards to a private https URL you can open on a phone.
cd "$(dirname "$0")/.." || exit 0
export PATH="$PWD/tools:$PATH"

if ! command -v opencode >/dev/null 2>&1; then
  echo "OpenCode is not installed yet; see .devcontainer/setup.sh"
  exit 0
fi

if (echo >/dev/tcp/127.0.0.1/4096) 2>/dev/null; then
  echo "OpenCode web UI is already running on port 4096"
  exit 0
fi

setsid nohup opencode serve --port 4096 --hostname 127.0.0.1 >/tmp/opencode-web.log 2>&1 </dev/null &
echo "OpenCode web UI starting on port 4096 (log: /tmp/opencode-web.log)"

#!/usr/bin/env bash
# Runs once when the codespace is created.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing OpenCode"
npm install -g opencode-ai@latest

echo "==> Installing the Kaggle CLI"
python3 -m pip install --disable-pip-version-check --no-cache-dir --upgrade "kaggle>=2.2.4,<3"

chmod +x tools/kgpu

echo "==> Installed"
opencode --version
python3 -m kaggle --version

if [ -n "${KAGGLE_API_TOKEN:-}" ]; then
  tools/kgpu quota || echo "KAGGLE_API_TOKEN is set but Kaggle login failed; check the secret's value."
else
  echo "KAGGLE_API_TOKEN is not set: add it under GitHub Settings > Codespaces > Secrets, then restart the codespace."
fi

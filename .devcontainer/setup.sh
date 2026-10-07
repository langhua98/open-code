#!/usr/bin/env bash
# Runs once when the codespace is created. Safe to run again in an existing codespace to pick up
# tools added later: git pull && bash .devcontainer/setup.sh && web restart
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing OpenCode"
# npm 11+ skips install scripts unless allowed; opencode-ai's postinstall picks the binary for this CPU.
npm install -g --allow-scripts=opencode-ai opencode-ai@latest

echo "==> Installing the Kaggle CLI"
python3 -m pip install --disable-pip-version-check --no-cache-dir --upgrade "kaggle>=2.2.4,<3"

# Same fix as in the Dockerfile, for codespaces created before it: Yarn's apt repository fails
# signature checks and breaks `apt-get update`.
sudo rm -f /etc/apt/sources.list.d/yarn.list

echo "==> Installing the browser for OpenCode (Playwright MCP + Chromium)"
npm install -g @playwright/mcp@latest
# Installs the Chromium build that matches this Playwright MCP version, plus its system libraries and fonts.
playwright-mcp install-browser --with-deps chromium

echo "==> Installing the GitHub CLI (gh)"
if ! command -v gh >/dev/null; then
  # Official apt repository: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
  sudo mkdir -p -m 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
  sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq gh
fi

echo "==> Installing Python libraries for documents and charts"
python3 -m pip install --disable-pip-version-check --no-cache-dir --upgrade \
  pypdf python-docx openpyxl python-pptx pandas matplotlib

echo "==> Installed"
opencode --version
python3 -m kaggle --version
playwright-mcp --version
gh --version
if command -v docker >/dev/null; then docker --version; else echo "Docker: available after Rebuild Container"; fi

if [ -n "${KAGGLE_API_TOKEN:-}" ]; then
  tools/kgpu quota || echo "KAGGLE_API_TOKEN is set but Kaggle login failed; check the secret's value."
else
  echo "KAGGLE_API_TOKEN is not set: add it under GitHub Settings > Codespaces > Secrets, then restart the codespace."
fi

#!/usr/bin/env bash
# Starts ComfyUI on port 7860. Everything the user makes (models, custom nodes,
# workflows, outputs) goes to /data when the Space has persistent storage,
# so it survives restarts and rebuilds. Without it, files are lost on restart.
set -euo pipefail

if [ -d /data ] && [ -w /data ]; then
  BASE=/data/comfyui
else
  BASE=$HOME/comfy-data
  echo "[start] no persistent storage at /data: files are lost when the Space restarts"
fi
mkdir -p "$BASE"/{models,custom_nodes,input,output,user,temp}

# Models listed in models.txt; already downloaded files are skipped.
python fetch_models.py models.txt "$BASE/models" || echo "[start] some models failed to download, starting anyway"

exec python app/main.py \
  --listen 0.0.0.0 --port 7860 \
  --base-directory "$BASE" \
  --enable-manager \
  ${COMFYUI_ARGS:-}

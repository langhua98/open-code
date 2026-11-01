"""Download the models listed in models.txt from Hugging Face.

Each non-empty line is: <models subfolder> <repo id> <file path in repo>
for example:  checkpoints  Comfy-Org/stable-diffusion-v1-5-archive  v1-5-pruned-emaonly-fp16.safetensors
The file is saved as <models dir>/<subfolder>/<file name>. Files that already exist are skipped.
Gated or private repos need the HF_TOKEN secret on the Space.
"""

import os
import shutil
import sys
import tempfile

from huggingface_hub import hf_hub_download


def parse(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 3:
                raise SystemExit(f"{path}:{n}: expected '<subfolder> <repo id> <file>', got: {line}")
            entries.append(tuple(parts))
    return entries


def main(list_file, models_dir):
    failed = 0
    for subfolder, repo, filename in parse(list_file):
        dest = os.path.join(models_dir, subfolder, os.path.basename(filename))
        if os.path.exists(dest):
            print(f"[models] have {subfolder}/{os.path.basename(filename)}")
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        print(f"[models] downloading {repo}/{filename} -> {subfolder}/")
        try:
            # Download next to the destination so the final move is a rename on the same disk.
            with tempfile.TemporaryDirectory(dir=models_dir, prefix=".dl-") as tmp:
                got = hf_hub_download(repo_id=repo, filename=filename, local_dir=tmp)
                shutil.move(got, dest)
        except Exception as e:  # keep going: one bad line should not stop the Space
            failed += 1
            print(f"[models] FAILED {repo}/{filename}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: fetch_models.py <models.txt> <models dir>")
    sys.exit(main(sys.argv[1], sys.argv[2]))

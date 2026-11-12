#!/usr/bin/env python3
"""Free text-to-image.

  python3 gen_image.py "<prompt>" [--ratio 1:1|3:4|4:3|9:16|16:9] [--engine auto|pollinations|hf] [--seed N]

auto = Pollinations first (free, no key, 1 picture / 45 s per IP), then the Z-Image-Turbo
Hugging Face Space (needs HF token, uses the daily free ZeroGPU quota).
Last line on success:  MEDIA_READY <path>   (send it with MEDIA:<path>)
On failure:            NO_TOKEN | QUOTA_EXCEEDED <msg> | BLOCKED <msg> | FAILED <msg>
"""
import argparse
import os
import random
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import POLLI_KEY_FILE, classify, gradio_client, hf_client, hf_token, out_path, read_secret  # noqa: E402

SIZES = {  # ratio -> (w, h) for Pollinations, Z-Image dropdown label
    "1:1": ((1024, 1024), "1024x1024 ( 1:1 )"),
    "3:4": ((864, 1152), "864x1152 ( 3:4 )"),
    "4:3": ((1152, 864), "1152x864 ( 4:3 )"),
    "9:16": ((720, 1280), "720x1280 ( 9:16 )"),
    "16:9": ((1280, 720), "1280x720 ( 16:9 )"),
}


def pollinations(prompt, ratio, seed):
    (w, h), _ = SIZES[ratio]
    q = {"width": w, "height": h, "seed": seed, "nologo": "true", "model": "flux"}
    key = read_secret("POLLINATIONS_KEY", POLLI_KEY_FILE)
    if key:
        url = "https://gen.pollinations.ai/image/%s?%s" % (urllib.parse.quote(prompt), urllib.parse.urlencode(q))
        headers = {"Authorization": "Bearer " + key}
    else:
        url = "https://image.pollinations.ai/prompt/%s?%s" % (urllib.parse.quote(prompt), urllib.parse.urlencode(q))
        headers = {}
    for attempt in range(3):
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-free-media-gen", **headers})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            if not ctype.startswith("image/") or len(data) < 2000:
                raise RuntimeError("not an image: %s %d bytes" % (ctype, len(data)))
            path = out_path("image", "jpg")
            with open(path, "wb") as f:
                f.write(data)
            return path
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            if e.code in (402, 429) and attempt < 2:  # free limit: 1 image / 45 s per IP
                print("POLLINATIONS_WAIT 46s (%s)" % e.code, flush=True)
                time.sleep(46)
                continue
            raise RuntimeError("pollinations HTTP %s: %s" % (e.code, body))
    raise RuntimeError("pollinations: still rate limited")


def zimage(prompt, ratio, seed):
    _, label = SIZES[ratio]
    c = hf_client("Tongyi-MAI/Z-Image-Turbo")
    res = c.predict(prompt=prompt, resolution=label, seed=seed, steps=8, shift=3.0,
                    random_seed=False, gallery_images=[], api_name="/generate")
    gallery = res[0]
    item = gallery[0]
    src = item["image"] if isinstance(item, dict) and "image" in item else item
    if isinstance(src, dict):
        src = src.get("path")
    path = out_path("image", os.path.splitext(src)[1].lstrip(".") or "png")
    shutil.copy(src, path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--ratio", default="1:1", choices=list(SIZES))
    ap.add_argument("--engine", default="auto", choices=["auto", "pollinations", "hf"])
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else random.randint(1, 2**31 - 1)

    errors = []
    if a.engine in ("auto", "pollinations"):
        try:
            print("ENGINE pollinations", flush=True)
            print("MEDIA_READY " + pollinations(a.prompt, a.ratio, seed))
            return
        except Exception as e:  # noqa: BLE001
            errors.append("pollinations: %s" % e)
            print("POLLINATIONS_FAILED %s" % e, flush=True)
    if a.engine in ("auto", "hf"):
        if not hf_token():
            print("NO_TOKEN (no HF token in $HF_TOKEN or ~/.hermes/hf_token)")
            sys.exit(2)
        try:
            print("ENGINE hf Z-Image-Turbo", flush=True)
            print("MEDIA_READY " + zimage(a.prompt, a.ratio, seed))
            return
        except Exception as e:  # noqa: BLE001
            word, msg = classify(e)
            print("%s %s" % (word, msg))
            sys.exit(1)
    print("FAILED " + " | ".join(errors))
    sys.exit(1)


if __name__ == "__main__":
    main()

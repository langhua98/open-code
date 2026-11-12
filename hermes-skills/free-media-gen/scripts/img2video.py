#!/usr/bin/env python3
"""Free image-to-video on Hugging Face ZeroGPU Spaces (needs an HF token).

  python3 img2video.py <image path or URL> "<motion prompt>" [--seconds 3.5] [--engine auto|wan|ltx]

wan = Wan 2.2 14B fast (zerogpu-aoti/wan2-2-fp8da-aoti-faster), best quality, ~1 min.
ltx = LTX-Video distilled (Lightricks/ltx-video-distilled), lighter, used if wan fails.
Last line on success:  MEDIA_READY <path.mp4>
On failure:            NO_TOKEN | NO_IMAGE | QUOTA_EXCEEDED <msg> | BLOCKED <msg> | FAILED <msg>
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import classify, gradio_client, hf_client, hf_token, out_path  # noqa: E402


def video_path(v):
    if isinstance(v, dict):
        v = v.get("video") or v.get("path")
        if isinstance(v, dict):
            v = v.get("path")
    return v


def wan(img, prompt, seconds):
    _, handle_file = gradio_client()
    c = hf_client("zerogpu-aoti/wan2-2-fp8da-aoti-faster")
    res = c.predict(input_image=handle_file(img), prompt=prompt, steps=6,
                    duration_seconds=seconds, randomize_seed=True, api_name="/generate_video")
    return video_path(res[0])


def ltx(img, prompt, seconds):
    _, handle_file = gradio_client()
    c = hf_client("Lightricks/ltx-video-distilled")
    res = c.predict(prompt=prompt, input_image_filepath=handle_file(img), mode="image-to-video",
                    duration_ui=min(seconds, 5), randomize_seed=True, api_name="/image_to_video")
    return video_path(res[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("prompt", nargs="?", default="make this image come alive, cinematic motion, smooth animation")
    ap.add_argument("--seconds", type=float, default=3.5)
    ap.add_argument("--engine", default="auto", choices=["auto", "wan", "ltx"])
    a = ap.parse_args()
    seconds = max(1.0, min(a.seconds, 5.0))  # longer = more GPU quota; 5 s is plenty for WeChat

    if not a.image.startswith(("http://", "https://")) and not os.path.isfile(a.image):
        print("NO_IMAGE %s" % a.image)
        sys.exit(2)
    if not hf_token():
        print("NO_TOKEN (no HF token in $HF_TOKEN or ~/.hermes/hf_token)")
        sys.exit(2)

    engines = {"wan": [wan], "ltx": [ltx], "auto": [wan, ltx]}[a.engine]
    last = None
    for fn in engines:
        try:
            print("ENGINE %s (about 1-3 min)" % fn.__name__, flush=True)
            src = fn(a.image, a.prompt, seconds)
            path = out_path("video", "mp4")
            shutil.copy(src, path)
            print("MEDIA_READY " + path)
            return
        except Exception as e:  # noqa: BLE001
            last = classify(e)
            print("%s_FAILED %s" % (fn.__name__.upper(), last[1][:300]), flush=True)
            if last[0] in ("QUOTA_EXCEEDED", "BLOCKED"):
                break  # same quota / same content on the next Space, don't waste time
    print("%s %s" % last)
    sys.exit(1)


if __name__ == "__main__":
    main()

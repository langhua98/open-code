---
name: free-media-gen
description: Make pictures from text (文生图/画一张/生成图片) and short videos from a picture (图生视频/让图片动起来) for free - Pollinations for images, Hugging Face ZeroGPU Spaces (Wan 2.2, LTX-Video, Z-Image) with the owner's free HF token. Use whenever the user asks to draw, generate an image, or animate a photo.
---

# 免费生图 / 图生视频

Two fixed scripts. Run them, send the file, done. Don't write your own API calls (token-frugal rule 1).

## Install (once, and again after these files are updated)
```bash
pip install -q gradio_client        # the scripts also do this themselves if it's missing
ls ~/.hermes/hf_token 2>/dev/null || echo "no HF token yet"
```

## HF token (needed for video, and for the image fallback)
Free Hugging Face accounts get a few minutes of ZeroGPU time per day; without a token it's ~0.
When the user sends a token (`hf_...`), save it — don't echo it back, don't put it in memory/chat summaries:
```bash
mkdir -p ~/.hermes && printf '%s' 'hf_XXXX' > ~/.hermes/hf_token && chmod 600 ~/.hermes/hf_token
```
(`$HF_TOKEN` in the environment also works and wins over the file.) A **Read** token is enough:
huggingface.co → Settings → Access Tokens → Create new token → type Read.

## 文生图
```bash
python3 ~/.hermes/skills/free-media-gen/scripts/gen_image.py "<prompt>" --ratio 3:4
```
- `--ratio` 1:1 (default) | 3:4 | 4:3 | 9:16 (抖音竖屏) | 16:9.
- First engine is **Pollinations** (free, no key, small watermark, **1 picture per 45 s** — the script
  waits and retries by itself, `POLLINATIONS_WAIT` is normal). **Write the prompt in English** for it:
  translate the user's Chinese and add a few style words (photo / anime / watercolor, lighting).
- If Pollinations fails it falls back to **Z-Image-Turbo** on HF (needs the token). Z-Image understands
  Chinese and can draw Chinese text in the picture — when the user wants words written ON the image
  (海报、标题、"早安"), go straight to it with `--engine hf` and keep the prompt in Chinese.
- Several pictures: run it several times (Pollinations is one per 45 s; tell the user it takes a bit).

## 图生视频
```bash
python3 ~/.hermes/skills/free-media-gen/scripts/img2video.py <image path or https URL> "<motion prompt>" --seconds 3.5
```
- The image is the picture the user just sent (use the local path the gateway gave you) or one you just
  generated (`/home/user/gen_image_*.jpg`). No picture → ask for one, or make one with gen_image.py first.
- Motion prompt in English, describe the MOVEMENT, not the picture: "the cat slowly turns its head and
  blinks, gentle camera push-in". Default if the user gives none is fine.
- `--seconds` 1–5 (default 3.5). Longer eats more of the daily GPU quota.
- Engines: Wan 2.2 fast (best, ~1–2 min) → LTX-Video distilled if Wan errors. Run with `background=true`
  and say "开始做视频了，大约 2 分钟" once.
- Output is a silent MP4, about 624×832 for a 3:4 picture.

## Reading the result (last line)
| line | do |
|---|---|
| `MEDIA_READY <path>` | send `MEDIA:<path>` with one short line. Don't vision_analyze it first. |
| `NO_TOKEN` | "视频要用你的 Hugging Face 免费 token：huggingface.co → Settings → Access Tokens → 新建一个 Read 类型，发给我" |
| `QUOTA_EXCEEDED <msg>` | today's free GPU time is used up. Tell the user, include the "Try again in H:MM:SS" from msg. Images still work via Pollinations. Don't retry in a loop. |
| `BLOCKED <msg>` | the Space's safety filter refused it. Say so; don't try to word around it. |
| `NO_IMAGE` / `FAILED <msg>` | say what failed in one line. Try `--engine ltx` (video) once; then stop (token-frugal rule 6). |

Files: `/home/user/gen_image_<HHMMSS>.jpg|png`, `/home/user/gen_video_<HHMMSS>.mp4`. Delete old ones now and
then (`rm /home/user/gen_*`), they're not needed after sending.

## Notes
- Spaces used: `zerogpu-aoti/wan2-2-fp8da-aoti-faster`, `Lightricks/ltx-video-distilled`,
  `Tongyi-MAI/Z-Image-Turbo`. Public Spaces sometimes go to sleep or change; if one keeps failing with
  an API error (not quota), tell the owner instead of guessing new parameters.
- Pollinations' new API (`gen.pollinations.ai`) needs a key with paid "pollen"; if the owner ever gets one,
  put it in `~/.hermes/pollinations_key` and the script uses it (no 45-s limit, no watermark).

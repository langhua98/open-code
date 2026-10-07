"""导出频道视频清单给 worker.js / 前端用.
用法: python src/export_index.py   (读 TELEGRAM_API_ID / HASH 环境变量,复用 /tmp/tg_login 登录态)
产出: outputs/index.json  [{id,caption,date,duration,size,mime}]
前端 INDEX_URL 指到这个文件的公网地址 (R2 / GitHub Pages) 即可.
"""
import asyncio
import json
import os
import sys

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004292843233"))
OUT = "outputs/index.json"

async def main():
    from telethon import TelegramClient
    from telethon.tl.types import InputMessagesFilterVideo

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    c = TelegramClient("/tmp/tg_login", api_id, api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        print("未登录,先走验证码流程", file=sys.stderr)
        sys.exit(1)

    items = []
    # iter_messages 自动分页,4177 条几分钟跑完
    async for m in c.iter_messages(CHANNEL_ID, filter=InputMessagesFilterVideo(), limit=None):
        try:
            v = m.video
            dur = 0
            if v:
                dur = int(getattr(v, "duration", 0) or 0)
                # attributes 里有时更准
                for a in getattr(v, "attributes", []) or []:
                    if hasattr(a, "duration") and a.duration:
                        dur = int(a.duration)
                        break
            items.append({
                "id": m.id,
                "caption": (m.text or "")[:200],
                "date": m.date.isoformat() if m.date else "",
                "duration": dur,
                "size": v.size if v else 0,
                "mime": v.mime_type if v else "",
            })
        except Exception as e:
            print(f"skip {m.id}: {e}", file=sys.stderr)
        if len(items) % 500 == 0:
            print(f"...{len(items)}", flush=True)

    # 按 id 倒序 (新的在前,前端默认就这样翻)
    items.sort(key=lambda x: -x["id"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"OK total={len(items)} -> {OUT}")
    await c.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

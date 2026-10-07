"""找出并删除频道里被转发进来的重复视频.
worker.js 在 LOG_CHAT_ID 设成频道本身时,每次播放都会把视频转发回频道,产生重复.
这些重复消息都带"转发自本频道"标记,原视频不带,所以只删带标记的,原视频不动.

用法: python src/dedupe_channel.py            # 只列出,不删
     python src/dedupe_channel.py --delete   # 真的删除
(读 TELEGRAM_API_ID / HASH 环境变量,复用 /tmp/tg_login 登录态,和 export_index.py 一样)
"""
import asyncio
import os
import sys

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004292843233"))


async def main(delete: bool):
    from telethon import TelegramClient
    from telethon.utils import get_peer_id

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    c = TelegramClient("/tmp/tg_login", api_id, api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        print("未登录,先走验证码流程", file=sys.stderr)
        sys.exit(1)

    dupes = []  # (消息 id, 原视频 id)
    total = 0
    async for m in c.iter_messages(CHANNEL_ID, limit=None):
        total += 1
        f = m.fwd_from
        if f and f.from_id and get_peer_id(f.from_id) == CHANNEL_ID:
            dupes.append((m.id, f.channel_post))
        if total % 1000 == 0:
            print(f"...已检查 {total} 条", flush=True)

    print(f"共 {total} 条消息,其中 {len(dupes)} 条是转发回本频道的重复视频")
    for mid, orig in dupes[:20]:
        print(f"  消息 {mid}  <- 原视频 {orig}")
    if len(dupes) > 20:
        print(f"  ...还有 {len(dupes) - 20} 条")

    if delete and dupes:
        ids = [mid for mid, _ in dupes]
        for i in range(0, len(ids), 100):
            await c.delete_messages(CHANNEL_ID, ids[i : i + 100])
        print(f"已删除 {len(ids)} 条重复消息,原视频都保留着")
    elif dupes:
        print("这次只是列出来。确认无误后加 --delete 再运行一次就会删除。")
    await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main("--delete" in sys.argv))

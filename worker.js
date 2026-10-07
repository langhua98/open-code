// Cloudflare Worker: 前端播放你的 TG 频道视频
// 需要的环境变量 (wrangler secret / dashboard):
//   BOT_TOKEN   - @xiaoju_videos_bot 的 token
//   CHANNEL_ID  - -1004292843233
//   INDEX_URL   - export_index.py 生成的 index.json 的公网地址 (R2 / GitHub Pages)
//   LOG_CHAT_ID - 可选,用来按需 forward 换 file_id (先填频道 ID 本身也行,建议建个私有仓)
// 保留了你原来的 POST /tg-webhook,不破坏现有机器人

const JSON_HDR = { "content-type": "application/json; charset=utf-8" };
const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "*, Range",
  "access-control-expose-headers": "Content-Range, Accept-Ranges, Content-Length",
};

let INDEX_CACHE = null;
let INDEX_TS = 0;

async function tg(env, method, params = {}) {
  const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  return r.json();
}

async function loadIndex(env) {
  // 10 分钟缓存,前端翻页不用来回拉 4177 条
  if (INDEX_CACHE && Date.now() - INDEX_TS < 10 * 60 * 1000) return INDEX_CACHE;
  if (!env.INDEX_URL) return [];
  const r = await fetch(env.INDEX_URL, { cf: { cacheTtl: 600 } });
  if (!r.ok) return [];
  INDEX_CACHE = await r.json();
  INDEX_TS = Date.now();
  return INDEX_CACHE;
}

// 按需换 file_id:把频道某条消息 forward 到 LOG_CHAT_ID,拿回 file_id
// 需要 bot 在 LOG_CHAT_ID 里也是管理员 (建个只有你和 bot 的私有频道最省事)
async function resolveFileId(env, msgId, index) {
  const hit = (index || []).find((x) => String(x.id) === String(msgId));
  if (hit && hit.file_id) return hit;
  if (!env.LOG_CHAT_ID) return hit || null;
  const fwd = await tg(env, "forwardMessage", {
    chat_id: env.LOG_CHAT_ID,
    from_chat_id: env.CHANNEL_ID,
    message_id: Number(msgId),
  });
  const m = fwd && fwd.result ? fwd.result : null;
  const fileId =
    m?.video?.file_id || m?.document?.file_id || m?.animation?.file_id || null;
  const thumbId = m?.video?.thumbnail?.file_id || m?.thumb?.file_id || null;
  if (!fileId) return hit || null;
  return { ...(hit || { id: Number(msgId) }), file_id: fileId, thumb_id: thumbId };
}

function proxyResp(upstream, extra = {}) {
  const h = new Headers();
  for (const k of ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"])
    if (upstream.headers.get(k)) h.set(k, upstream.headers.get(k));
  Object.entries({ ...cors, ...extra }).forEach(([k, v]) => h.set(k, v));
  return new Response(upstream.body, { status: upstream.status, headers: h });
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });

    // 1) 原来的机器人 webhook,原样保留
    if (u.pathname === "/tg-webhook" && req.method === "POST") {
      // 这里以后可以顺手把新视频的 file_id 存 KV,现在先直接回 ok 不破坏现有逻辑
      try { await req.json(); } catch {}
      return new Response(JSON.stringify({ ok: true }), { headers: { ...JSON_HDR, ...cors } });
    }

    // 2) 健康检查
    if (u.pathname === "/api/health") {
      return new Response(JSON.stringify({ ok: true, channel: env.CHANNEL_ID || null }), { headers: { ...JSON_HDR, ...cors } });
    }

    // 3) 清单: /api/list?offset=0&limit=20&q=关键词&shuffle=1&seed=123
    //    shuffle=1 时用 seed 做确定性洗牌:同一 seed 翻页不重复,换 seed 换一批随机
    if (u.pathname === "/api/list") {
      const index = await loadIndex(env);
      const q = (u.searchParams.get("q") || "").trim().toLowerCase();
      const offset = Math.max(0, Number(u.searchParams.get("offset") || 0));
      const limit = Math.min(100, Math.max(1, Number(u.searchParams.get("limit") || 20)));
      let arr = index.slice();
      if (q) arr = arr.filter((x) => (x.caption || "").toLowerCase().includes(q));
      if (u.searchParams.get("shuffle") === "1") {
        let s = Number(u.searchParams.get("seed") || Date.now()) >>> 0;
        const rnd = () => {
          s |= 0; s = (s + 0x6d2b79f5) | 0;
          let t = Math.imul(s ^ (s >>> 15), 1 | s);
          t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
          return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
        for (let i = arr.length - 1; i > 0; i--) {
          const j = Math.floor(rnd() * (i + 1));
          [arr[i], arr[j]] = [arr[j], arr[i]];
        }
      }
      const total = arr.length;
      const items = arr.slice(offset, offset + limit).map((x) => ({
        id: x.id,
        caption: (x.caption || "").slice(0, 120),
        duration: x.duration || 0,
        size: x.size || 0,
        date: x.date || "",
        thumb: `/thumb/${x.id}.jpg`,
        stream: `/stream/${x.id}.mp4`,
      }));
      return new Response(JSON.stringify({ total, offset, limit, items }), { headers: { ...JSON_HDR, ...cors } });
    }

    // 4) 播放: /stream/6515.mp4  或 /stream?id=6515 (支持 Range 拖进度)
    let m = u.pathname.match(/^\/stream\/(\d+)/) || (u.pathname === "/stream" ? [null, u.searchParams.get("id")] : null);
    if (m && m[1]) {
      const index = await loadIndex(env);
      const meta = await resolveFileId(env, m[1], index);
      if (!meta || !meta.file_id) return new Response("no file_id,先跑 export 更新 index.json", { status: 404, headers: cors });
      const g = await tg(env, "getFile", { file_id: meta.file_id });
      const path = g?.result?.file_path;
      if (!path) return new Response("getFile 失败", { status: 502, headers: cors });
      const fileUrl = `https://api.telegram.org/file/bot${env.BOT_TOKEN}/${path}`;
      const headers = {};
      const range = req.headers.get("range");
      if (range) headers["range"] = range;
      const up = await fetch(fileUrl, { headers });
      return proxyResp(up);
    }

    // 5) 封面: /thumb/6515.jpg
    m = u.pathname.match(/^\/thumb\/(\d+)/);
    if (m && m[1]) {
      const index = await loadIndex(env);
      const meta = await resolveFileId(env, m[1], index);
      const fid = meta?.thumb_id || meta?.file_id;
      if (!fid) return new Response("no thumb", { status: 404, headers: cors });
      const g = await tg(env, "getFile", { file_id: fid });
      const path = g?.result?.file_path;
      if (!path) return new Response("getFile 失败", { status: 502, headers: cors });
      const up = await fetch(`https://api.telegram.org/file/bot${env.BOT_TOKEN}/${path}`);
      return proxyResp(up, { "cache-control": "public, max-age=86400" });
    }

    return new Response("ok", { headers: cors });
  },
};

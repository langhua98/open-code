// Cloudflare Worker: 前端播放你的 TG 频道视频
// 需要的环境变量 (wrangler secret / dashboard):
//   BOT_TOKEN   - @xiaoju_videos_bot 的 token
//   CHANNEL_ID  - -1004292843233
//   INDEX_URL   - export_index.py 生成的 index.json 的公网地址 (R2 / GitHub Pages)
//   LOG_CHAT_ID - 可选,用来按需 forward 换 file_id (先填频道 ID 本身也行,建议建个私有仓)
//   FILE_IDS    - 可选 KV 绑定 (见 wrangler.toml):换到的 file_id 永久存下来,每个视频只 forward 一次
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

// Bot API 只能下载 20 MB 以内的文件,更大的视频放不了
const MAX_BOT_FILE = 20 * 1024 * 1024;
// file_id 永久有效;file_path 官方保证至少 1 小时有效
const PATH_TTL = 50 * 60 * 1000;
const META = new Map(); // 消息 id -> {file_id, thumb_id}
const PATHS = new Map(); // file_id -> {path, ts}
const PENDING = new Map(); // 同一视频的并发请求 (播放时浏览器会分段要数据) 只问一次 TG

function once(key, fn) {
  if (!PENDING.has(key)) PENDING.set(key, fn().finally(() => PENDING.delete(key)));
  return PENDING.get(key);
}

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
// 换到的 file_id 先存内存,有 FILE_IDS 绑定时再存 KV,之后不再 forward
async function resolveFileId(env, msgId, index) {
  const id = String(msgId);
  const hit = (index || []).find((x) => String(x.id) === id);
  if (hit && hit.file_id) return hit;
  const base = hit || { id: Number(id) };
  if (META.has(id)) return { ...base, ...META.get(id) };
  if (env.FILE_IDS) {
    const saved = await env.FILE_IDS.get(id, "json");
    if (saved) {
      META.set(id, saved);
      return { ...base, ...saved };
    }
  }
  if (!env.LOG_CHAT_ID) return hit || null;
  const ids = await once(`fwd:${id}`, async () => {
    const fwd = await tg(env, "forwardMessage", {
      chat_id: env.LOG_CHAT_ID,
      from_chat_id: env.CHANNEL_ID,
      message_id: Number(id),
    });
    const m = fwd && fwd.result ? fwd.result : null;
    const fileId =
      m?.video?.file_id || m?.document?.file_id || m?.animation?.file_id || null;
    if (!fileId) return null;
    const thumbId = m?.video?.thumbnail?.file_id || m?.thumb?.file_id || null;
    const found = { file_id: fileId, thumb_id: thumbId };
    META.set(id, found);
    if (env.FILE_IDS) await env.FILE_IDS.put(id, JSON.stringify(found));
    return found;
  });
  return ids ? { ...base, ...ids } : hit || null;
}

// file_id -> 下载路径,缓存 50 分钟,不用每段数据都问一次 getFile
async function filePath(env, fileId) {
  const c = PATHS.get(fileId);
  if (c && Date.now() - c.ts < PATH_TTL) return { path: c.path };
  return once(`path:${fileId}`, async () => {
    const g = await tg(env, "getFile", { file_id: fileId });
    const path = g?.result?.file_path;
    if (!path) return { error: g?.description || "getFile 失败" };
    PATHS.set(fileId, { path, ts: Date.now() });
    return { path };
  });
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
      // 超过 20 MB 的视频机器人下载不了,不放进列表
      let arr = index.filter((x) => !(x.size > MAX_BOT_FILE));
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
      const hit = index.find((x) => String(x.id) === String(m[1]));
      if (hit && hit.size > MAX_BOT_FILE) return new Response("视频超过 20 MB,机器人接口下载不了", { status: 413, headers: cors });
      const meta = await resolveFileId(env, m[1], index);
      if (!meta || !meta.file_id) return new Response("no file_id,先跑 export 更新 index.json", { status: 404, headers: cors });
      const { path, error } = await filePath(env, meta.file_id);
      if (!path) return new Response(error, { status: 502, headers: cors });
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
      const { path, error } = await filePath(env, fid);
      if (!path) return new Response(error, { status: 502, headers: cors });
      const up = await fetch(`https://api.telegram.org/file/bot${env.BOT_TOKEN}/${path}`);
      return proxyResp(up, { "cache-control": "public, max-age=86400" });
    }

    return new Response("ok", { headers: cors });
  },
};

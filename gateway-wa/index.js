import path from "node:path";
import crypto from "node:crypto";
import http from "node:http";
import dotenv from "dotenv";
import pino from "pino";
import qrcode from "qrcode-terminal";
import QRCode from "qrcode";
import {
  default as makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  downloadMediaMessage,
} from "@whiskeysockets/baileys";

// Muat konfigurasi dari root .env atau fallback
const rootEnvPath = path.resolve(process.cwd(), "..", ".env");
dotenv.config({ path: rootEnvPath });
dotenv.config(); // fallback ke local .env jika ada

const BACKEND_BASE_URL =
  process.env.VITE_API_URL || process.env.BACKEND_URL || "http://127.0.0.1:5687";
const INTERNAL_TOKEN = process.env.INTERNAL_TOKEN || "change-me";
const SESSION_PATH =
  process.env.WA_SESSION_PATH || path.resolve(process.cwd(), "session");

const QR_PORT = parseInt(process.env.QR_PORT || "3001", 10);
const QR_PASSWORD = process.env.QR_PASSWORD || "cepu-qr";
// Secret untuk sign cookie — pakai INTERNAL_TOKEN supaya tidak perlu var baru
const COOKIE_SECRET = INTERNAL_TOKEN + "-qr-session";
const COOKIE_NAME = "cepu_qr_session";
const COOKIE_MAX_AGE = 60 * 60 * 24; // 24 jam

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
});

// --- QR HTTP Server ---
let currentQR = null;
let isConnected = false;
const sseClients = new Set();

function broadcastSSE(data) {
  const msg = `data: ${JSON.stringify(data)}\n\n`;
  for (const res of sseClients) {
    try { res.write(msg); } catch (_) { sseClients.delete(res); }
  }
}

/** Buat signed token dari password hash + timestamp */
function makeSessionToken() {
  const payload = Date.now().toString();
  const sig = crypto.createHmac("sha256", COOKIE_SECRET).update(payload).digest("hex");
  return `${payload}.${sig}`;
}

/** Verifikasi token dari cookie */
function isValidToken(token) {
  if (!token || typeof token !== "string") return false;
  const dot = token.indexOf(".");
  if (dot <= 0) return false;
  const payload = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  if (!payload || !sig || !/^[0-9a-fA-F]+$/.test(sig)) return false;
  let sigBuf, expBuf;
  try {
    sigBuf = Buffer.from(sig, "hex");
    const expected = crypto.createHmac("sha256", COOKIE_SECRET).update(payload).digest();
    expBuf = expected;
  } catch (_) {
    return false;
  }
  if (sigBuf.length !== expBuf.length) return false;
  if (!crypto.timingSafeEqual(sigBuf, expBuf)) return false;
  const ts = parseInt(payload, 10);
  if (!Number.isFinite(ts)) return false;
  // Cek umur token (max 24 jam)
  return Date.now() - ts < COOKIE_MAX_AGE * 1000;
}

/** Parse cookie header → object (tahan terhadap nilai yang mengandung "=") */
function parseCookies(req) {
  const raw = req.headers.cookie || "";
  const out = {};
  if (!raw) return out;
  for (const part of raw.split(";")) {
    const eq = part.indexOf("=");
    if (eq <= 0) continue;
    try {
      const k = decodeURIComponent(part.slice(0, eq).trim());
      const v = decodeURIComponent(part.slice(eq + 1).trim());
      if (k) out[k] = v;
    } catch (_) {
      // abaikan cookie yang tidak bisa di-decode
    }
  }
  return out;
}

/** Cek apakah request sudah auth */
function isAuthenticated(req) {
  if (!QR_PASSWORD) return true; // password tidak diset → bebas akses
  const cookies = parseCookies(req);
  return isValidToken(cookies[COOKIE_NAME]);
}

const qrServer = http.createServer(async (req, res) => {
  // --- POST /login: validasi password, set cookie ---
  if (req.method === "POST" && req.url === "/login") {
    let body = "";
    req.on("data", chunk => { body += chunk; });
    req.on("end", () => {
      const params = new URLSearchParams(body);
      const pwd = params.get("password") || "";
      if (pwd === QR_PASSWORD) {
        const token = makeSessionToken();
        res.writeHead(302, {
          "Set-Cookie": `${COOKIE_NAME}=${encodeURIComponent(token)}; HttpOnly; SameSite=Lax; Max-Age=${COOKIE_MAX_AGE}; Path=/`,
          "Location": "/qr",
        });
        res.end();
      } else {
        res.writeHead(302, { "Location": "/qr?err=1" });
        res.end();
      }
    });
    return;
  }

  // --- GET /events: SSE (butuh auth) ---
  if (req.url === "/events") {
    if (!isAuthenticated(req)) {
      res.writeHead(401).end("Unauthorized");
      return;
    }
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    });
    sseClients.add(res);
    if (isConnected) {
      res.write(`data: ${JSON.stringify({ type: "connected" })}\n\n`);
    } else if (currentQR) {
      const svg = await QRCode.toString(currentQR, { type: "svg" }).catch(() => null);
      if (svg) res.write(`data: ${JSON.stringify({ type: "qr", svg })}\n\n`);
    }
    req.on("close", () => sseClients.delete(res));
    return;
  }

  // --- GET /qr atau / ---
  if (req.url === "/" || req.url?.startsWith("/qr")) {
    const showError = req.url.includes("err=1");
    const authed = isAuthenticated(req);

    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });

    if (!authed) {
      // Halaman login
      res.end(`<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CePu WA Gateway – Login</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { min-height: 100vh; display: flex; align-items: center; justify-content: center;
           background: #0f1117; font-family: 'Inter', system-ui, sans-serif; padding: 24px; }
    .card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 20px;
            padding: 40px 36px; width: 100%; max-width: 380px;
            box-shadow: 0 20px 60px rgba(0,0,0,.5); }
    .logo { font-size: 2.5rem; text-align: center; margin-bottom: 8px; }
    h1 { font-size: 1.25rem; font-weight: 700; color: #e2e8f0; text-align: center; margin-bottom: 4px; }
    .sub { font-size: .85rem; color: #64748b; text-align: center; margin-bottom: 28px; }
    label { display: block; font-size: .8rem; color: #94a3b8; margin-bottom: 6px; font-weight: 600; letter-spacing: .5px; text-transform: uppercase; }
    input[type=password] { width: 100%; padding: 12px 14px; background: #0f1117;
      border: 1px solid #2d3748; border-radius: 10px; color: #e2e8f0;
      font-size: .95rem; outline: none; transition: border-color .2s; }
    input[type=password]:focus { border-color: #25d366; }
    .err { background: #2d1515; border: 1px solid #7f1d1d; color: #fca5a5;
           border-radius: 8px; padding: 10px 14px; font-size: .85rem; margin-bottom: 16px; }
    button { width: 100%; margin-top: 16px; padding: 13px; background: #25d366;
             color: #0f1117; font-weight: 700; font-size: 1rem; border: none;
             border-radius: 10px; cursor: pointer; transition: background .2s, transform .1s; }
    button:hover { background: #1ebe5d; }
    button:active { transform: scale(.98); }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">📱</div>
    <h1>CePu WA Gateway</h1>
    <p class="sub">Masukkan password untuk akses halaman QR</p>
    ${showError ? '<div class="err">❌ Password salah. Coba lagi.</div>' : ''}
    <form method="POST" action="/login">
      <label for="pwd">Password</label>
      <input type="password" id="pwd" name="password" autofocus placeholder="••••••••" required>
      <button type="submit">Masuk →</button>
    </form>
  </div>
</body>
</html>`);
      return;
    }

    // Halaman QR (sudah auth)
    res.end(`<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CePu WA Gateway – Scan QR</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center;
           background: #0f1117; color: #e2e8f0; font-family: 'Inter', system-ui, sans-serif; gap: 24px; padding: 24px; }
    h1 { font-size: 1.4rem; font-weight: 700; color: #25d366; letter-spacing: .5px; }
    p  { font-size: .9rem; color: #94a3b8; text-align: center; max-width: 340px; line-height: 1.7; }
    #qr-box { background: #fff; border-radius: 20px; padding: 24px;
              box-shadow: 0 0 60px #25d36650;
              display: flex; align-items: center; justify-content: center;
              min-width: 270px; min-height: 270px; transition: box-shadow .3s; }
    #qr-box:has(svg) { box-shadow: 0 0 60px #25d36680; }
    #qr-box svg { width: 224px; height: 224px; }
    #status { font-size: .85rem; color: #64748b; }
    .live { color: #f59e0b !important; font-weight: 600; }
    .connected { color: #25d366 !important; font-weight: 600; font-size: 1rem; }
    .spinner { width: 52px; height: 52px; border: 4px solid #1e293b; border-top-color: #25d366;
               border-radius: 50%; animation: spin .8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .badge { font-size: .72rem; background: #1e293b; color: #475569; padding: 4px 10px;
             border-radius: 99px; margin-top: -8px; }
  </style>
</head>
<body>
  <h1>📱 CePu WA Gateway</h1>
  <p>Buka WhatsApp → <b>Pengaturan → Perangkat Tertaut → Tautkan Perangkat</b>, lalu scan QR di bawah.</p>
  <div id="qr-box"><div class="spinner"></div></div>
  <span id="status">Menunggu QR code...</span>
  <span class="badge">QR auto-refresh • sesi 24 jam</span>
  <script>
    const box = document.getElementById('qr-box');
    const status = document.getElementById('status');
    const es = new EventSource('/events');
    es.onmessage = e => {
      const d = JSON.parse(e.data);
      if (d.type === 'qr') {
        box.innerHTML = d.svg;
        status.textContent = '🟡 QR aktif – segera scan!';
        status.className = 'live';
      } else if (d.type === 'connected') {
        box.innerHTML = '<span style="font-size:4rem">✅</span>';
        status.textContent = 'WhatsApp berhasil terhubung!';
        status.className = 'connected';
      } else if (d.type === 'disconnected') {
        box.innerHTML = '<div class="spinner"></div>';
        status.textContent = 'Koneksi terputus, menunggu QR baru...';
        status.className = '';
      }
    };
    es.onerror = () => { status.textContent = 'Koneksi SSE terputus, coba refresh halaman.'; };
  </script>
</body>
</html>`);
    return;
  }

  res.writeHead(404).end();
});

qrServer.listen(QR_PORT, () => {
  console.log(`🌐 QR Server berjalan di http://localhost:${QR_PORT}/qr`);
});

function hashPhoneNumber(senderJid) {
  // Tangani berbagai bentuk JID: 628xx@s.whatsapp.net, xxx@lid,
  // grup (xxx@g.us + participant), channel (@newsletter), dsb.
  // Untuk grup: pakai participant (pengirim asli), bukan ID grup.
  const raw = String(senderJid || "");
  const cleanNumber = raw.split("@")[0].replace(/\D/g, "");
  const basis = cleanNumber || raw;
  // Hash SHA-256 untuk menjaga privasi nomor pengguna di backend CePu
  return crypto.createHash("sha256").update(basis).digest("hex");
}

// ---------------------------------------------------------------------------
// Kebijakan gateway: DETEKSI HANYA LEWAT GAMBAR.
// - Teks (menu/bantuan/lapor/job) tetap diteruskan ke backend agar state
//   machine (edukasi/lapor/menu/job) tetap jalan.
// - Teks bebas TIDAK pernah memicu deteksi di backend (backend juga menolak
//   pipeline teks dan membalas imbauan kirim screenshot).
// - Hanya pesan gambar yang diteruskan sebagai job deteksi (type: "image").
// - Tipe lain (stiker/audio/video/kontak/lokasi/poll/dokumen non-gambar/...)
//   dibalas lokal dengan panduan kirim screenshot, TANPA memanggil backend
//   (hemat inferensi BERT + anti-ban). Update protokol/reaksi/poll-vote
//   diabaikan diam-diam agar bot tidak ngobrol sendiri.
// ---------------------------------------------------------------------------
const MAX_IMAGE_BYTES = parseInt(process.env.WA_MAX_IMAGE_BYTES || `${5 * 1024 * 1024}`, 10);
const ALLOWED_IMAGE_MIMES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
]);
// Dokumen yang masih masuk akal sebagai screenshot lowongan.
const ALLOWED_DOC_MIMES = new Set([
  ...ALLOWED_IMAGE_MIMES,
  "application/pdf",
]);

const IMAGE_ONLY_GUIDE_TEXT = (
  "🔎 *Deteksi CePu hanya lewat gambar/screenshot* 📸\n\n" +
  "Mohon kirim *screenshot/foto lowongan kerja* (JPG/PNG/WebP, maks 5MB) " +
  "beserta caption bila perlu — nanti saya baca teksnya otomatis (OCR) dan analisis.\n\n" +
  "Teks ketikan tidak bisa dideteksi langsung supaya hasilnya akurat.\n" +
  "Ketik *bantuan* untuk panduan menu."
);

const UNSUPPORTED_KIND_TEXT = (
  "📎 *Maaf, tipe pesan itu belum bisa diproses.*\n\n" +
  IMAGE_ONLY_GUIDE_TEXT
);

const TOO_LARGE_IMAGE_TEXT = (
  "📎 *Gambarnya kebesaran (maks 5MB).* 🙏\n" +
  "Coba kompres/screenshot ulang dengan resolusi lebih kecil, lalu kirim lagi ya."
);

const BUSY_TEXT = (
  "⏳ *Masih menganalisis gambar sebelumnya...* tunggu sebentar ya, " +
  "saya balas begitu selesai. Kirim ulang gambarnya jika belum ada balasan 1 menit lagi."
);

// Deduplikasi redelivery Baileys: id pesan -> timestamp. TTL 5 menit.
const seenMessageIds = new Map();
const SEEN_TTL_MS = 5 * 60 * 1000;
function isDuplicateMessage(keyId) {
  if (!keyId) return false;
  const now = Date.now();
  if (seenMessageIds.has(keyId)) return true;
  seenMessageIds.set(keyId, now);
  if (seenMessageIds.size > 2000) {
    for (const [k, ts] of seenMessageIds) {
      if (now - ts > SEEN_TTL_MS) seenMessageIds.delete(k);
      if (seenMessageIds.size <= 1500) break;
    }
  }
  return false;
}

// Cegah dobel inferensi paralel dari pengirim yang sama (spam/ban + hemat GPU).
const inflightSenders = new Set();

// Cooldown balasan "kirim gambar dong" supaya stiker-spam tidak bikin bot
// kena flag spam. Default 45 detik per pengirim.
const lastNudgeAt = new Map();
const NUDGE_COOLDOWN_MS = parseInt(process.env.WA_NUDGE_COOLDOWN_MS || "45000", 10);
function shouldSendNudge(senderJid) {
  const now = Date.now();
  const last = lastNudgeAt.get(senderJid) || 0;
  if (now - last < NUDGE_COOLDOWN_MS) return false;
  lastNudgeAt.set(senderJid, now);
  return true;
}

/** True jika JID ini BUKAN DM personal (grup/channel/broadcast/status). */
function isNonDirectChat(remoteJid) {
  if (!remoteJid) return true;
  if (remoteJid === "status@broadcast") return true;
  if (remoteJid.endsWith("@g.us")) return true; // grup
  if (remoteJid.endsWith("@broadcast")) return true; // broadcast/status
  if (remoteJid.endsWith("@newsletter")) return true; // channel/follow
  return false;
}

/**
 * Lepas pembungkus Baileys: ephemeral / view-once / lanjutan view-once.
 * Mengembalikan objek message yang sudah "telanjang".
 */
function unwrapMessageContent(content) {
  let cur = content;
  for (let i = 0; i < 5 && cur; i++) {
    if (cur.ephemeralMessage?.message) {
      cur = cur.ephemeralMessage.message;
    } else if (cur.viewOnceMessage?.message) {
      cur = cur.viewOnceMessage.message;
    } else if (cur.viewOnceMessageV2?.message) {
      cur = cur.viewOnceMessageV2.message;
    } else if (cur.viewOnceMessageV2Extension?.message) {
      cur = cur.viewOnceMessageV2Extension.message;
    } else {
      break;
    }
  }
  return cur || {};
}

/** Ambil teks dari berbagai kemungkinan payload (caption ikut). */
function extractTextBody(content) {
  return (
    content?.conversation ||
    content?.extendedTextMessage?.text ||
    content?.imageMessage?.caption ||
    content?.documentMessage?.caption ||
    content?.videoMessage?.caption ||
    ""
  );
}

async function forwardMessageToBackend(phoneHash, msgType, textContent, onProgress, imageB64 = null, mimeType = null) {
  const url = `${BACKEND_BASE_URL}/internal/wa/inbound`;
  try {
    const body = {
      phone_hash: phoneHash,
      msg: {
        type: msgType,
        body: textContent,
        image_b64: imageB64,
        mime_type: mimeType,
      },
      stream: true,
    };
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": INTERNAL_TOKEN,
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errText = await response.text();
      logger.error({ status: response.status, errText }, "Backend returned error");
      return "⚠️ Maaf, layanan CePu sedang mengalami kendala teknis. Silakan coba sesaat lagi.";
    }

    // Handle SSE stream from backend
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let finalReply = "";
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const block of lines) {
        for (const line of block.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (payload.type === "progress" && onProgress) {
                await onProgress(payload.stage, payload.message, payload.percent);
              } else if (payload.type === "result") {
                finalReply = payload.reply;
              } else if (payload.type === "error") {
                return `⚠️ Terjadi kendala saat analisis: ${payload.message}`;
              }
            } catch (e) {
              // ignore json parse error on partial chunks
            }
          }
        }
      }
    }

    return finalReply || "⚠️ Tidak ada respon dari sistem deteksi.";
  } catch (error) {
    logger.error({ error }, "Gagal menghubungi backend CePu");
    return "⚠️ Terjadi gangguan koneksi ke server CePu. Silakan coba kembali nanti.";
  }
}

async function startWhatsAppBot() {
  console.log("-------------------------------------------------------");
  console.log("🤖 Memulai CePu WhatsApp Gateway (Personal Number)");
  console.log(`📡 Backend Target : ${BACKEND_BASE_URL}`);
  console.log(`📁 Lokasi Session : ${SESSION_PATH}`);
  console.log("-------------------------------------------------------");

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
  const { version, isLatest } = await fetchLatestBaileysVersion();
  logger.info({ version, isLatest }, "Menggunakan versi Baileys WhatsApp Web");

  const sock = makeWASocket({
    version,
    logger: pino({ level: "silent" }), // Heningkan log internal baileys agar terminal bersih
    printQRInTerminal: false,
    auth: state,
    generateHighQualityLinkPreview: true,
  });

  // Simpan perubahan kredensial sesi
  sock.ev.on("creds.update", saveCreds);

  // Pantau update status koneksi
  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQR = qr;
      isConnected = false;
      console.log("\n=======================================================");
      console.log("📱 SCAN KODE QR DI BAWAH DENGAN WHATSAPP PRIBADI ANDA:");
      console.log(`   Atau buka browser: http://localhost:${QR_PORT}/qr`);
      console.log("=======================================================\n");
      qrcode.generate(qr, { small: true });
      // Broadcast QR baru ke semua browser yang terbuka
      QRCode.toString(qr, { type: "svg" })
        .then(svg => broadcastSSE({ type: "qr", svg }))
        .catch(() => {});
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      // loggedOut / badSession = sesi mati, reconnect sia-sia (butuh scan ulang).
      // Selain itu (closed/lost/timedOut/replaced/restartRequired/...) = reconnect.
      const fatalCodes = new Set([
        DisconnectReason.loggedOut,
        DisconnectReason.badSession,
      ]);
      const shouldReconnect = !fatalCodes.has(statusCode);

      logger.warn(
        { statusCode, shouldReconnect, reason: lastDisconnect?.error },
        "Koneksi WhatsApp terputus"
      );

      if (shouldReconnect) {
        console.log("🔄 Menghubungkan ulang ke WhatsApp dalam 3 detik...");
        setTimeout(() => startWhatsAppBot(), 3000);
      } else if (statusCode === DisconnectReason.badSession) {
        console.log("❌ Sesi korup (bad session). Hapus direktori session dan restart untuk scan QR baru.");
      } else {
        console.log("❌ Sesi telah keluar (logged out). Hapus direktori session dan restart untuk scan QR baru.");
      }
    } else if (connection === "open") {
      isConnected = true;
      currentQR = null;
      broadcastSSE({ type: "connected" });
      console.log("\n✅ Berhasil terhubung ke WhatsApp!");
      console.log("🎉 Bot CePu siap menerima pesan dari pengguna.\n");
    }
  });

  // Kirim teks dengan aman: jangan pernah lempar exception ke loop utama.
  async function safeReplyText(toJid, text, quotedMsg) {
    try {
      await sock.sendMessage(toJid, { text }, quotedMsg ? { quoted: quotedMsg } : undefined);
      return true;
    } catch (err) {
      logger.warn({ err, toJid }, "Gagal mengirim balasan teks");
      return false;
    }
  }

  // WAJIB mengimbangi setiap "composing": tanpa "paused", aplikasi WA
  // pengirim macet menampilkan "mengetik..." padahal hasil sudah terkirim.
  async function markIdle(toJid) {
    try {
      await sock.sendPresenceUpdate("paused", toJid);
    } catch (e) {
      // abaikan
    }
  }

  // Centang biru best-effort: tanda pesan sudah dibaca bot.
  async function markRead(incomingMsg) {
    try {
      await sock.readMessages([incomingMsg.key]);
    } catch (e) {
      // abaikan
    }
  }

  // Balasan lokal (tanpa backend) + tutup indikator mengetik.
  async function replyAndIdle(toJid, text, quotedMsg) {
    const ok = await safeReplyText(toJid, text, quotedMsg);
    await markIdle(toJid);
    return ok;
  }

  // Satu pesan diproses di sini. Semua edge-case "aneh" WhatsApp ditangani
  // di satu tempat supaya loop utama tidak pernah crash.
  async function handleOneIncomingMessage(msg) {
    // 1) Abaikan pesan milik sendiri.
    if (msg.key?.fromMe) return;

    // Baileys baru kadang menaruh DM di remoteJidAlt (pemetaan LID<->PN).
    const remoteJid = msg.key?.remoteJid || msg.key?.remoteJidAlt;
    if (!remoteJid) return;

    // 2) Abaikan grup / channel / broadcast / status.
    //    Bot ini reply-only di DM personal; membalas di grup = spam + risiko banned.
    if (isNonDirectChat(remoteJid)) return;

    // 3) Deduplikasi redelivery (Baileys bisa mengirim pesan yang sama 2x).
    if (isDuplicateMessage(msg.key?.id)) return;

    // 4) Abaikan update non-chat: read receipt/history-sync/dsb tanpa payload.
    if (!msg.message) return;

    const content = unwrapMessageContent(msg.message);

    // 5) Abaikan diam-diam: pesan protokol (revoke/delete), reaksi, vote poll,
    //    dan event panggilan. Membalas ini hanya bikin bot ngobrol sendiri.
    if (
      content.protocolMessage ||
      content.reactionMessage ||
      content.pollUpdateMessage ||
      content.keepInChatMessage
    ) {
      return;
    }

    const senderJid = remoteJid;
    const messageBody = extractTextBody(content) || "";

    const hasImage = Boolean(content.imageMessage);
    const hasDocument = Boolean(content.documentMessage);
    const hasVideo = Boolean(content.videoMessage);
    const hasAudio = Boolean(content.audioMessage || content.pttMessage);
    const hasSticker = Boolean(content.stickerMessage);
    const hasContact = Boolean(content.contactMessage || content.contactsArrayMessage);
    const hasLocation = Boolean(content.locationMessage || content.liveLocationMessage);
    const hasPollCreate = Boolean(content.pollCreationMessage);
    const hasCall = Boolean(content.callLogMessage || content.callLogRecordMessage);

    // 6) Tipe yang tidak didukung untuk deteksi -> balas panduan LOKAL
    //    (tanpa memanggil backend) + cooldown anti-spam.
    //    Catatan: teks & gambar diteruskan ke backend; sisanya ditolak di sini.
    const unsupportedKind =
      hasSticker || hasAudio || hasVideo || hasContact || hasLocation || hasPollCreate || hasCall ||
      (hasDocument && !ALLOWED_DOC_MIMES.has((content.documentMessage?.mimetype || "").split(";")[0].trim().toLowerCase()));

    if (unsupportedKind) {
      let kind = "lainnya";
      if (hasSticker) kind = "stiker";
      else if (hasAudio) kind = "audio/vn";
      else if (hasVideo) kind = "video";
      else if (hasContact) kind = "kontak";
      else if (hasLocation) kind = "lokasi";
      else if (hasPollCreate) kind = "polling";
      else if (hasCall) kind = "panggilan";
      else if (hasDocument) kind = `dokumen (${content.documentMessage?.mimetype || "?"})`;
      console.log(`⏭️ Pesan ${kind} dari ${senderJid} ditolak lokal (bukan gambar).`);
      if (shouldSendNudge(senderJid)) {
        await replyAndIdle(senderJid, UNSUPPORTED_KIND_TEXT, msg);
      }
      return;
    }

    const isDocImage = hasDocument && ALLOWED_DOC_MIMES.has(
      (content.documentMessage?.mimetype || "").split(";")[0].trim().toLowerCase()
    );
    const isImage = hasImage || isDocImage;

    // 7) Pesan kosong tanpa teks & tanpa gambar (mis. poll-update lolos,
    //    messageContextInfo saja, dsb.) -> abaikan diam-diam.
    if (!messageBody && !isImage) {
      return;
    }

    // Centang biru: pesan diterima dan sedang diproses.
    await markRead(msg);

    // 8) Cegah inferensi ganda paralel dari pengirim yang sama.
    if (inflightSenders.has(senderJid)) {
      await replyAndIdle(senderJid, BUSY_TEXT, msg);
      return;
    }
    inflightSenders.add(senderJid);
    try {
      const msgType = isImage ? "image" : "text";
      // Untuk grup (sudah diabaikan di atas) participant dipakai; di DM pakai remoteJid.
      const phoneHash = hashPhoneNumber(msg.key?.participant || senderJid);

      // 9) Download gambar jika ada + validasi ukuran & mime.
      //    DETEKSI HANYA LEWAT GAMBAR: caption boleh kosong (OCR yang bicara).
      let imageB64 = null;
      let mimeType = null;
      if (isImage) {
        const mediaNode = content.imageMessage || content.documentMessage;
        const declaredMime = (mediaNode?.mimetype || "image/jpeg").split(";")[0].trim().toLowerCase();
        if (!ALLOWED_DOC_MIMES.has(declaredMime)) {
          if (shouldSendNudge(senderJid)) {
            await replyAndIdle(senderJid, UNSUPPORTED_KIND_TEXT, msg);
          }
          return;
        }
        // Pra-cek fileLength dari metadata WA (kalau ada) supaya file 50MB
        // tidak di-download dulu baru ditolak.
        const declaredLen = parseInt(mediaNode?.fileLength || "0", 10);
        if (Number.isFinite(declaredLen) && declaredLen > MAX_IMAGE_BYTES) {
          await replyAndIdle(senderJid, TOO_LARGE_IMAGE_TEXT, msg);
          return;
        }
        let buffer;
        try {
          buffer = await downloadMediaMessage(msg, "buffer", {}, { logger });
        } catch (e) {
          logger.warn({ err: e }, "Gagal download media WhatsApp");
          await replyAndIdle(
            senderJid,
            "⚠️ *Gagal mengunduh gambarnya.* Coba kirim ulang screenshot-nya ya 📸 (pastikan bukan sekali-lihat yang sudah dibuka).",
            msg
          );
          return;
        }
        if (!buffer || buffer.length === 0) {
          await replyAndIdle(
            senderJid,
            "⚠️ *Gambarnya kosong/tidak terbaca.* Coba kirim ulang screenshot-nya ya 📸.",
            msg
          );
          return;
        }
        if (buffer.length > MAX_IMAGE_BYTES) {
          await replyAndIdle(senderJid, TOO_LARGE_IMAGE_TEXT, msg);
          return;
        }
        imageB64 = buffer.toString("base64");
        mimeType = declaredMime;
      }

      console.log(`📥 Pesan diterima dari ${senderJid} (type: ${msgType}): "${messageBody.slice(0, 120)}"`);

      // Tampilkan indikator mengetik (composing) di WhatsApp pengirim
      try {
        await sock.sendPresenceUpdate("composing", senderJid);
      } catch (e) {
        // abaikan jika presence gagal (mis. JID aneh / grup)
      }

      let progressMsgKey = null;
      let lastProgressUpdate = 0;

      const onProgress = async (stage, text, percent) => {
        const now = Date.now();
        // Update presence dan kirim notifikasi progres jika analisis membutuhkan waktu
        try {
          await sock.sendPresenceUpdate("composing", senderJid);
        } catch (e) {}

        // Batasi frekuensi edit/pesan progres agar tidak spamming (min 1.2 detik jeda)
        if (now - lastProgressUpdate > 1200 || stage === "complete") {
          lastProgressUpdate = now;
          const statusText = `⏳ *CePu sedang menganalisis (${percent}%)*...\n_${text}_`;
          try {
            if (!progressMsgKey) {
              const sent = await sock.sendMessage(senderJid, { text: statusText }, { quoted: msg });
              progressMsgKey = sent?.key;
            } else if (sock.sendMessage) {
              // Edit pesan progres sebelumnya jika didukung Baileys
              await sock.sendMessage(senderJid, { text: statusText, edit: progressMsgKey });
            }
          } catch (e) {
            // fallback jika edit pesan tidak didukung versi wa user
          }
        }
      };

      // Teruskan pesan ke API CePu Backend dengan callback progres.
      // - type "image" -> backend menjalankan OCR + pipeline deteksi.
      // - type "text"  -> backend HANYA melayani menu/edukasi/lapor/job;
      //   teks bebas TIDAK memicu deteksi (backend membalas panduan gambar).
      const botReply = await forwardMessageToBackend(phoneHash, msgType, messageBody, onProgress, imageB64, mimeType);

      // Kirim balasan akhir ke pengguna (atau edit status message terakhir menjadi hasil akhir)
      try {
        if (progressMsgKey) {
          try {
            await sock.sendMessage(senderJid, { text: botReply, edit: progressMsgKey });
          } catch (e) {
            await sock.sendMessage(senderJid, { text: botReply }, { quoted: msg });
          }
        } else {
          await sock.sendMessage(senderJid, { text: botReply }, { quoted: msg });
        }
        console.log(`📤 Balasan terkirim ke ${senderJid}`);
      } catch (err) {
        logger.error({ err, senderJid }, "Gagal mengirim balasan WhatsApp");
      }
    } finally {
      inflightSenders.delete(senderJid);
      // Tutup indikator "mengetik..." di HP pengirim — wajib di semua
      // jalur (sukses maupun gagal), kalau tidak chat macet menampilkan
      // status menulis padahal tidak ada pesan susulan.
      await markIdle(senderJid);
    }
  }

  // Tangani pesan masuk
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      try {
        await handleOneIncomingMessage(msg);
      } catch (err) {
        // Satu pesan busuk tidak boleh membunuh loop / memutuskan koneksi.
        logger.error({ err, msgId: msg?.key?.id }, "Gagal memproses pesan masuk, dilewati");
        // Best-effort: jangan biarkan indikator mengetik nyangkut.
        try {
          const jid = msg?.key?.remoteJid || msg?.key?.remoteJidAlt;
          if (jid && !isNonDirectChat(jid)) await markIdle(jid);
        } catch (_) {}
      }
    }
  });
}

startWhatsAppBot().catch((err) => {
  console.error("Fatal error saat inisialisasi bot:", err);
  process.exit(1);
});

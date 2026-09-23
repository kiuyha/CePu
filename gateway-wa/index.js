import path from "node:path";
import crypto from "node:crypto";
import dotenv from "dotenv";
import pino from "pino";
import qrcode from "qrcode-terminal";
import {
  default as makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
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

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
});

function hashPhoneNumber(senderJid) {
  // Membersihkan ID WhatsApp (misal 6281234567890@s.whatsapp.net -> 6281234567890)
  const cleanNumber = senderJid.split("@")[0].replace(/\D/g, "");
  // Hash SHA-256 untuk menjaga privasi nomor pengguna di backend CePu
  return crypto.createHash("sha256").update(cleanNumber).digest("hex");
}

async function forwardMessageToBackend(phoneHash, msgType, textContent, onProgress) {
  const url = `${BACKEND_BASE_URL}/internal/wa/inbound`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": INTERNAL_TOKEN,
      },
      body: JSON.stringify({
        phone_hash: phoneHash,
        msg: {
          type: msgType,
          body: textContent,
        },
        stream: true,
      }),
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
      console.log("\n=======================================================");
      console.log("📱 SCAN KODE QR DI BAWAH DENGAN WHATSAPP PRIBADI ANDA:");
      console.log("   (Buka WhatsApp -> Pengaturan / Titik 3 -> Perangkat Tertaut -> Tautkan Perangkat)");
      console.log("=======================================================\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn(
        { statusCode, shouldReconnect, reason: lastDisconnect?.error },
        "Koneksi WhatsApp terputus"
      );

      if (shouldReconnect) {
        console.log("🔄 Menghubungkan ulang ke WhatsApp dalam 3 detik...");
        setTimeout(() => startWhatsAppBot(), 3000);
      } else {
        console.log("❌ Sesi telah keluar (logged out). Hapus direktori session dan restart untuk scan QR baru.");
      }
    } else if (connection === "open") {
      console.log("\n✅ Berhasil terhubung ke WhatsApp!");
      console.log("🎉 Bot CePu siap menerima pesan dari pengguna.\n");
    }
  });

  // Tangani pesan masuk
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      // Abaikan pesan yang dikirim oleh bot itu sendiri atau pesan status/broadcast
      if (msg.key.fromMe) continue;
      if (msg.key.remoteJid.endsWith("@broadcast") || msg.key.remoteJid.includes("status")) {
        continue;
      }

      const senderJid = msg.key.remoteJid;
      // Ambil teks dari berbagai kemungkinan payload baileys
      const messageBody =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.imageMessage?.caption ||
        "";

      const isImage = Boolean(msg.message?.imageMessage);

      // Jika tidak ada teks maupun gambar (misal stiker, kontak, reaksi), abaikan
      if (!messageBody && !isImage) {
        continue;
      }

      const msgType = isImage ? "image" : "text";
      const phoneHash = hashPhoneNumber(senderJid);

      console.log(`📥 Pesan diterima dari ${senderJid} (type: ${msgType}): "${messageBody}"`);

      // Tampilkan indikator mengetik (composing) di WhatsApp pengirim
      try {
        await sock.sendPresenceUpdate("composing", senderJid);
      } catch (e) {
        // abaikan jika presence gagal
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

      // Teruskan pesan ke API CePu Backend dengan callback progres
      const botReply = await forwardMessageToBackend(phoneHash, msgType, messageBody, onProgress);

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
    }
  });
}

startWhatsAppBot().catch((err) => {
  console.error("Fatal error saat inisialisasi bot:", err);
  process.exit(1);
});

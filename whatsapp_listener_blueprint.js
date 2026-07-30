const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, downloadContentFromMessage, getContentType,
    makeCacheableSignalKeyStore } = require('@whiskeysockets/baileys');

const pino = require('pino');
const axios = require('axios');
const qrcode = require('qrcode-terminal');

// 🔁 Resilient decrypt-with-retry wrapper.
// WhatsApp often delivers the sender-key a few hundred ms to a couple seconds
// AFTER the encrypted message itself (that's what "sent retry receipt" in the
// logs is doing on WA's side). A single immediate attempt can miss that window
// even with a healthy session store, so we retry with backoff before giving up.
async function downloadImageWithRetry(imageMessageNode, retries = 3) {
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const stream = await downloadContentFromMessage(imageMessageNode, 'image');
            let buffer = Buffer.from([]);

            for await (const chunk of stream) {
                buffer = Buffer.concat([buffer, chunk]);
            }

            if (buffer && buffer.length > 0) {
                return buffer; // raw bytes - caller encodes/saves
            }
        } catch (err) {
            console.warn(`⚠️ Decrypt attempt ${attempt + 1}/${retries + 1} failed: ${err.message}`);
            if (attempt < retries) {
                const delay = 1200 * (attempt + 1);
                await new Promise(r => setTimeout(r, delay));
            }
        }
    }
    return null;
}

// 🚦 SERIAL PROCESSING QUEUE
// With hundreds of active supplier groups, Baileys can fire 'messages.upsert'
// faster than a single message finishes processing. If two messages try to
// decrypt/write to the auth-state key store concurrently, one transaction wins
// and the other gets "transaction failed, rolling back" - silently breaking
// that message's session/decrypt. Forcing strictly sequential processing
// removes this race entirely. Throughput cost is small relative to the
// reliability gain, since each message is just one HTTP POST + optional decrypt.
let queueTail = Promise.resolve();
function enqueue(task) {
    queueTail = queueTail.then(task).catch(err => {
        console.error("⚡ Queue task error:", err.message);
    });
    return queueTail;
}

// 🪦 DEAD SESSION TRACKING
// Some sender/group pairs will NEVER decrypt within this run, no matter how
// many times we retry (confirmed: same participant fails identically over a
// 20+ minute window even with serialized key-store access). Retrying these
// wastes time and floods logs. Track repeat offenders and skip immediate
// decrypt attempts for them - the .enc fallback URL still gets saved via
// webhook_server.py, just without burning 4 retry attempts per message.
const failCounts = new Map(); // "remoteJid|participant" -> consecutive fail count
const DEAD_THRESHOLD = 2;

function sessionKey(msg) {
    return `${msg.key.remoteJid}|${msg.key.participant || ''}`;
}

function isKnownDead(msg) {
    return (failCounts.get(sessionKey(msg)) || 0) >= DEAD_THRESHOLD;
}

function recordFailure(msg) {
    const k = sessionKey(msg);
    failCounts.set(k, (failCounts.get(k) || 0) + 1);
}

function recordSuccess(msg) {
    failCounts.delete(sessionKey(msg)); // session healed - clear it
}

async function processMessage(msg) {
    try {
        let messageContent = msg.message;
        let messageType = getContentType(messageContent);

        // Robust multi-pass loop to peel back nested containers
        while (messageContent && ['ephemeralMessage', 'viewOnceMessage', 'viewOnceMessageV2', 'documentWithCaptionMessage'].includes(messageType)) {
            messageContent = messageContent[messageType].message;
            messageType = getContentType(messageContent);
        }

        let base64Image = null;

        if (messageType === 'imageMessage') {
            if (isKnownDead(msg)) {
                console.warn(`💀 Skipping decrypt retries for known-dead session: ${sessionKey(msg)}`);
            } else {
                console.log(`📸 Image message discovered from ${msg.pushName || 'Supplier'}. Decrypting media stream...`);
                const buffer = await downloadImageWithRetry(messageContent.imageMessage);

                if (buffer) {
                    base64Image = `data:image/jpeg;base64,${buffer.toString('base64')}`;
                    console.log("✅ Media stream decrypted successfully.");
                    recordSuccess(msg);
                } else {
                    console.error("❌ Media decryption failed after retries.");
                    recordFailure(msg);
                }
            }
        }

        // Forward payload data directly to your FastAPI backend
        await axios.post('http://127.0.0.1:8000/webhook/whatsapp', {
            instance: "Rikeys_Local_Engine",
            media: base64Image,
            data: msg
        });

    } catch (err) {
        console.log("⚡ Ingestion link down or FastAPI offline:", err.message);
    }
}

// 🔒 MUTEX-WRAPPED KEY STORE
// "transaction failed, rolling back" happens INSIDE Baileys' own internal
// stanza-decryption pipeline - before 'messages.upsert' ever fires. With
// hundreds of concurrent groups, Baileys can be decrypting multiple incoming
// messages in parallel internally, and those internal calls race on the raw
// key store (state.keys.get/set) regardless of anything we serialize in our
// own event handler. The only reliable fix is to force every single read/write
// to the underlying key store to happen one at a time, at the source.
function makeMutexKeyStore(rawKeys) {
    let chain = Promise.resolve();

    function lock(task) {
        const result = chain.then(task);
        // Keep the chain alive even if a task throws, so later ops still run.
        chain = result.catch(() => {});
        return result;
    }

    return {
        get: (type, ids) => lock(() => rawKeys.get(type, ids)),
        set: (data) => lock(() => rawKeys.set(data)),
        ...(rawKeys.clear ? { clear: () => lock(() => rawKeys.clear()) } : {})
    };
}

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_session_data');
    const logger = pino({ level: 'silent' });

    // Mutex first (true serialization at the source), THEN cache on top
    // (so repeated reads of the same key within a burst are cheap).
    const serializedKeys = makeMutexKeyStore(state.keys);
    const cachedKeys = makeCacheableSignalKeyStore(serializedKeys, logger);

    const sock = makeWASocket({
        auth: {
            creds: state.creds,
            keys: cachedKeys,
        },
        printQRInTerminal: false,
        logger
    });

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            console.log('🤖 SCAN THIS QR CODE WITH YOUR WHATSAPP APP:');
            qrcode.generate(qr, { small: true });
        }
        if (connection === 'close') {
            const shouldReconnect = lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('⚠️ Connection closed, reconnecting: ', shouldReconnect);
            if (shouldReconnect) connectToWhatsApp();
        } else if (connection === 'open') {
            console.log('🚀 Rikeys Stream Pipeline Connected Natively to WhatsApp Core!');
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // Intercept inbound payload streams - push each message onto the serial
    // queue rather than processing inline, so decrypt/key-store ops never overlap.
    sock.ev.on('messages.upsert', (m) => {
        if (m.type !== 'notify') return;

        for (const msg of m.messages) {
            if (!msg.message || msg.key.fromMe) continue;
            if (msg.key.remoteJid === 'status@broadcast') continue; // not a real group JID
            enqueue(() => processMessage(msg));
        }
    });
}

connectToWhatsApp();

"""Bot rekap keuangan - WhatsApp Cloud API (Meta).
Env: WA_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN, APP_SECRET, ADMIN_PASSWORD, BASE_URL, DB_PATH
Jalankan: python app_cloud.py   (webhook: BASE_URL/webhook)
"""
import os, re, json, hmac, hashlib, sqlite3, secrets, requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, abort

E = os.getenv
DB = E("DB_PATH", "keuangan.db")
WA_TOKEN, PHONE_ID = E("WA_TOKEN", ""), E("PHONE_NUMBER_ID", "")
VERIFY, APP_SECRET, ADMIN_PW = E("VERIFY_TOKEN", "ganti-ini"), E("APP_SECRET", ""), E("ADMIN_PASSWORD", "")
BASE_URL = E("BASE_URL", "http://localhost:5000")
GRAPH = "https://graph.facebook.com/v21.0"  # cek versi terbaru di dokumentasi Meta
KAT = {
    "keluar": ["Makanan", "Transport", "Belanja", "Tagihan", "Kesehatan", "Hiburan", "Pendidikan", "Lainnya"],
    "masuk": ["Gaji", "Bonus", "Usaha", "Hadiah", "Lainnya"],
}
AMT = re.compile(r"(\d[\d.,]*)\s*(rb|ribu|k|jt|juta)?\b", re.I)
HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


def now():
    return datetime.utcnow() + timedelta(hours=7)  # WIB


def q(sql, a=(), one=False, w=False):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        cur = c.execute(sql, a)
        return None if w else (cur.fetchone() if one else cur.fetchall())


def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(wa TEXT PRIMARY KEY, nama TEXT, token TEXT, tgl TEXT);
        CREATE TABLE IF NOT EXISTS state(wa TEXT PRIMARY KEY, step TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS trx(id INTEGER PRIMARY KEY AUTOINCREMENT, wa TEXT, tipe TEXT,
            jumlah REAL, kategori TEXT, catatan TEXT, tgl TEXT);
        CREATE TABLE IF NOT EXISTS tries(wa TEXT PRIMARY KEY, n INTEGER, until TEXT);
        CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY);""")


def rp(n):
    return "Rp" + f"{n:,.0f}".replace(",", ".")


def parse_amount(text):
    m = AMT.search(text)
    if not m:
        return None, text
    num, suf = m.group(1), (m.group(2) or "").lower()
    if suf:
        val = float(num.replace(",", ".")) * (1_000_000 if suf in ("jt", "juta") else 1_000)
    else:
        val = float(re.sub(r"[.,]", "", num))
    return val, (text[:m.start()] + text[m.end():]).strip()


# ---------- kirim pesan ----------
def send(to, payload):
    payload.update(messaging_product="whatsapp", to=to)
    if not WA_TOKEN:
        print("[KIRIM]", to, json.dumps(payload, ensure_ascii=False))
        return
    r = requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers={"Authorization": "Bearer " + WA_TOKEN},
                      json=payload, timeout=15)
    if r.status_code >= 400:
        print("[ERROR WA]", r.text)


def text(to, t):
    send(to, {"type": "text", "text": {"body": t}})


def buttons(to, t, opts):  # maksimal 3 tombol, judul maks 20 karakter
    send(to, {"type": "interactive", "interactive": {"type": "button", "body": {"text": t},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": ti}} for i, ti in opts]}}})


def pick(to, t, opts):  # daftar pilihan, maksimal 10 baris
    send(to, {"type": "interactive", "interactive": {"type": "list", "body": {"text": t},
        "action": {"button": "Pilih", "sections": [{"title": "Pilihan",
        "rows": [{"id": i, "title": ti[:24]} for i, ti in opts]}]}}})


def menu(to, pre=""):
    buttons(to, (pre + "\n\nMau apa?").strip(),
            [("masuk", "Uang masuk"), ("keluar", "Uang keluar"), ("rekap", "Rekap")])


def set_state(wa, step, data=None):
    q("INSERT OR REPLACE INTO state VALUES(?,?,?)", (wa, step, json.dumps(data or {})), w=True)


def clear(wa):
    q("DELETE FROM state WHERE wa=?", (wa,), w=True)


# ---------- pendaftaran (gerbang sandi) ----------
def register(wa, t, step):
    if step is None:
        set_state(wa, "sandi")
        return text(wa, "Halo! Nomor ini belum terdaftar. Masukkan sandi akses untuk mendaftar.")
    tr = q("SELECT * FROM tries WHERE wa=?", (wa,), one=True)
    if tr and tr["until"] and tr["until"] > now().isoformat():
        return text(wa, "Terlalu banyak percobaan. Coba lagi nanti.")
    if step == "sandi":
        if ADMIN_PW and hmac.compare_digest(t.encode(), ADMIN_PW.encode()):
            q("DELETE FROM tries WHERE wa=?", (wa,), w=True)
            set_state(wa, "nama")
            return text(wa, "Sandi benar. Siapa nama Anda?")
        n = (tr["n"] if tr else 0) + 1
        until = (now() + timedelta(minutes=30)).isoformat() if n >= 3 else ""
        q("INSERT OR REPLACE INTO tries VALUES(?,?,?)", (wa, 0 if until else n, until), w=True)
        return text(wa, "Sandi salah." + (" Diblokir 30 menit." if until else ""))
    if step == "nama":
        nama = t[:40]
        q("INSERT INTO users VALUES(?,?,?,?)", (wa, nama, secrets.token_urlsafe(16), now().isoformat()[:19]), w=True)
        clear(wa)
        return menu(wa, f"Pendaftaran berhasil, {nama}!")


# ---------- menu untuk nomor terdaftar ----------
def handle(wa, val):
    t, low = val.strip(), val.strip().lower()
    user = q("SELECT * FROM users WHERE wa=?", (wa,), one=True)
    st = q("SELECT * FROM state WHERE wa=?", (wa,), one=True)
    step = st["step"] if st else None
    if not user:
        return register(wa, t, step)
    if low in ("menu", "batal"):
        clear(wa)
        return menu(wa)
    if low in ("masuk", "keluar"):
        set_state(wa, "kat", {"tipe": low})
        return pick(wa, f"Pilih kategori uang {low}:", [("k|" + k, k) for k in KAT[low]])
    if low == "rekap":
        clear(wa)
        return menu(wa, f"Rekap dan grafik interaktif (pilih bulan langsung di web):\n{BASE_URL}/d/{user['token']}")
    if step == "kat" and t.startswith("k|") and t[2:] in KAT[json.loads(st["data"])["tipe"]]:
        d = json.loads(st["data"])
        d["kat"] = t[2:]
        set_state(wa, "nominal", d)
        return text(wa, f"Kategori {d['kat']}.\n\nCatatan sebelum kirim nominal:\n- Ketik angka saja, tanpa titik, koma, atau huruf\n- Contoh benar: 25000\n- Contoh salah: 25rb, 25.000, Rp25000\n\nSilakan ketik nominalnya. (ketik batal untuk kembali)")
    if step == "nominal":
        if not re.fullmatch(r"\d{1,12}", t) or int(t) == 0:
            return text(wa, "Format salah. Ketik angka saja tanpa titik, koma, atau huruf. Contoh: 25000 (bukan 25rb atau 25.000)")
        d = json.loads(st["data"])
        q("INSERT INTO trx(wa,tipe,jumlah,kategori,catatan,tgl) VALUES(?,?,?,?,?,?)",
          (wa, d["tipe"], float(t), d["kat"], "", now().strftime("%Y-%m-%d %H:%M:%S")), w=True)
        clear(wa)
        return menu(wa, f"Tercatat {'+' if d['tipe'] == 'masuk' else '-'}{rp(float(t))} ({d['kat']}).")
    return menu(wa)


# ---------- webhook Meta ----------
@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY:
        return request.args.get("hub.challenge", ""), 200
    abort(403)


@app.post("/webhook")
def hook():
    if APP_SECRET:
        exp = "sha256=" + hmac.new(APP_SECRET.encode(), request.get_data(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), exp):
            abort(403)
    for e in (request.get_json(silent=True) or {}).get("entry", []):
        for ch in e.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                if q("SELECT 1 FROM seen WHERE id=?", (m["id"],), one=True):
                    continue  # cegah pesan diproses dua kali saat Meta mengirim ulang
                q("INSERT INTO seen VALUES(?)", (m["id"],), w=True)
                if m["type"] == "text":
                    v = m["text"]["body"]
                elif m["type"] == "interactive":
                    i = m["interactive"]
                    v = (i.get("button_reply") or i.get("list_reply"))["id"]
                else:
                    v = "menu"
                try:
                    handle(m["from"], v)
                except Exception as ex:
                    print("[ERROR]", ex)
    return "ok"


# ---------- dashboard per pengguna ----------
def owner(tok):
    u = q("SELECT wa FROM users WHERE token=?", (tok,), one=True)
    return u["wa"] if u else abort(404)


@app.get("/api/<tok>")
def api(tok):
    u = q("SELECT wa, nama FROM users WHERE token=?", (tok,), one=True) or abort(404)
    rows = q("SELECT tgl, tipe, jumlah, kategori FROM trx WHERE wa=? ORDER BY tgl DESC LIMIT 5000", (u["wa"],))
    return jsonify(nama=u["nama"], trx=[dict(r) for r in rows])


@app.get("/d/<tok>")
def dashboard(tok):
    owner(tok)
    return send_from_directory(os.path.join(HERE, "static"), "dashboard.html")


init_db()
if __name__ == "__main__":
    if not ADMIN_PW:
        print("PERINGATAN: ADMIN_PASSWORD belum diset, tidak ada yang bisa mendaftar.")
    app.run(host="0.0.0.0", port=int(E("PORT", 5000)))

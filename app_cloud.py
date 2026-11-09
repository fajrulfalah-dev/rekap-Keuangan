"""Bot rekap keuangan - Telegram Bot API.
Env (file .env atau pengaturan server): TELEGRAM_TOKEN, WEBHOOK_SECRET, ADMIN_PASSWORD, BASE_URL, DB_PATH, ENV_FILE
Mode webhook : python app_telegram.py          (Telegram -> BASE_URL/webhook, butuh URL HTTPS publik)
Mode polling : python app_telegram.py poll     (tanpa webhook, cocok untuk tes lokal)
"""
import os, re, sys, json, hmac, sqlite3, secrets, threading, time, requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, abort

try:
    from dotenv import load_dotenv
    load_dotenv(os.getenv("ENV_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")))
except ImportError:
    pass

E = os.getenv
DB = E("DB_PATH", "keuangan.db")
TOKEN = E("TELEGRAM_TOKEN", "")
SECRET, ADMIN_PW = E("WEBHOOK_SECRET", ""), E("ADMIN_PASSWORD", "")
BASE_URL = E("BASE_URL", "http://localhost:5000")
API = f"https://api.telegram.org/bot{TOKEN}"
KAT = {
    "keluar": ["Makanan", "Transport", "Belanja", "Tagihan", "Kesehatan", "Hiburan", "Pendidikan", "Lainnya"],
    "masuk": ["Gaji", "Bonus", "Usaha", "Hadiah", "Lainnya"],
}
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
    # kolom "wa" menyimpan chat_id Telegram (nama kolom dipertahankan agar cocok dengan dashboard)
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


# ---------- kirim pesan ----------
def tg(method, **payload):
    if not TOKEN:
        print("[KIRIM]", method, json.dumps(payload, ensure_ascii=False))
        return {}
    try:
        r = requests.post(f"{API}/{method}", json=payload, timeout=40)
        if r.status_code >= 400:
            print("[ERROR TG]", r.text)
        return r.json()
    except Exception as ex:
        print("[ERROR TG]", ex)
        return {}


def text(to, t, keyboard=None):
    p = {"chat_id": to, "text": t, "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = {"inline_keyboard": keyboard}
    tg("sendMessage", **p)


def buttons(to, t, opts):  # satu baris tombol
    text(to, t, [[{"text": ti, "callback_data": i} for i, ti in opts]])


def pick(to, t, opts, per_row=2):  # daftar pilihan, 2 tombol per baris
    rows = [[{"text": ti, "callback_data": i} for i, ti in opts[n:n + per_row]] for n in range(0, len(opts), per_row)]
    text(to, t, rows)


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
        return text(wa, "Halo! Akun Telegram ini belum terdaftar. Masukkan sandi akses untuk mendaftar.")
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


# ---------- menu untuk akun terdaftar ----------
def handle(wa, val):
    t, low = val.strip(), val.strip().lower()
    user = q("SELECT * FROM users WHERE wa=?", (wa,), one=True)
    st = q("SELECT * FROM state WHERE wa=?", (wa,), one=True)
    step = st["step"] if st else None
    if not user:
        return register(wa, t, step)
    if low in ("menu", "batal", "start"):
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


# ---------- terima update Telegram ----------
def process(u):
    uid = "tg%s" % u.get("update_id")
    if q("SELECT 1 FROM seen WHERE id=?", (uid,), one=True):
        return  # cegah update diproses dua kali
    q("INSERT INTO seen VALUES(?)", (uid,), w=True)
    if "callback_query" in u:
        cb = u["callback_query"]
        tg("answerCallbackQuery", callback_query_id=cb["id"])  # hilangkan ikon loading di tombol
        msg = cb.get("message") or {}
        chat = msg.get("chat", {})
        v = cb.get("data", "menu")
    elif "message" in u:
        msg = u["message"]
        chat = msg.get("chat", {})
        v = msg.get("text")
        if v is None:
            v = "menu"  # stiker, foto, dll
        elif v.startswith("/"):
            v = v[1:].split("@")[0].split()[0] if v[1:].strip() else "menu"
    else:
        return
    if chat.get("type") != "private":
        return  # hanya chat pribadi, abaikan grup
    try:
        handle(str(chat["id"]), v)
    except Exception as ex:
        print("[ERROR]", ex)


@app.post("/webhook")
def hook():
    if SECRET and not hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), SECRET):
        abort(403)
    u = request.get_json(silent=True)
    if u:
        process(u)
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
    return send_from_directory(os.path.join(HERE, "static"), "index.html")


@app.get("/")
def home():
    return "Bot rekap keuangan aktif."


def poll():
    tg("deleteWebhook")
    off = None
    print("Mode polling aktif. Kirim /start ke bot Anda di Telegram.")
    while True:
        r = tg("getUpdates", timeout=30, offset=off, allowed_updates=["message", "callback_query"])
        for u in r.get("result", []):
            off = u["update_id"] + 1
            process(u)
        if not r:
            time.sleep(3)


init_db()
if __name__ == "__main__":
    if not ADMIN_PW:
        print("PERINGATAN: ADMIN_PASSWORD belum diset, tidak ada yang bisa mendaftar.")
    port = int(E("PORT", 5000))
    if len(sys.argv) > 1 and sys.argv[1] == "poll":
        threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
        poll()
    else:
        app.run(host="0.0.0.0", port=port)
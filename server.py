# Local KABAMAN server. Serves the site and stores accounts, orders, and
# admin settings in SQLite. Identity files stay in data/ and are not public.
# Set KABAMAN_ADMIN_PASSWORD, or let the first start write data/admin.config.json.
# The password is never printed.

import base64
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("KABAMAN_DATA_DIR", str(ROOT / "data"))).resolve()
IDS = DATA / "ids"
DB_PATH = DATA / "kabaman.sqlite"
CONFIG_PATH = DATA / "admin.config.json"
SITE_PATH = ROOT / "site.json"
HOST = os.environ.get("KABAMAN_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "4173"))
PBKDF2_ROUNDS = 200_000
SESSION_DAYS = 14
MAX_BODY = 3_000_000
MAX_ID_BYTES = 1_800_000
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "").strip()
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_GRAPH_VERSION = os.environ.get("WHATSAPP_GRAPH_VERSION", "").strip()

db_lock = threading.Lock()
listeners = []
listener_lock = threading.Lock()

STATUSES = {"Verified", "Not verified"}
FORMS = {"sourcing", "importation", "inspection", "auction"}


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_password(password, salt=None, rounds=PBKDF2_ROUNDS):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return "pbkdf2_sha256$%d$%s$%s" % (rounds, salt, digest.hex())


def verify_password(password, stored):
    try:
        algo, rounds, salt, digest = str(stored).split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds))
        return hmac.compare_digest(check.hex(), digest)
    except (TypeError, ValueError):
        return False


def load_admin_password():
    env = os.environ.get("KABAMAN_ADMIN_PASSWORD", "").strip()
    if env:
        return env
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            saved = str(data.get("password") or "").strip()
            if saved:
                return saved
        except (OSError, json.JSONDecodeError):
            pass
    generated = secrets.token_urlsafe(18)
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"password": generated}), encoding="utf-8")
    return generated


ADMIN_PASSWORD = None


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=8)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn, table):
    return {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}


def migrate(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY,
          email TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          phone TEXT NOT NULL DEFAULT '',
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY,
          role TEXT NOT NULL,
          customer_id INTEGER,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY,
          ref TEXT UNIQUE NOT NULL,
          customer_id INTEGER NOT NULL,
          form TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'Not verified',
          reply TEXT NOT NULL DEFAULT '',
          payload TEXT NOT NULL,
          has_id INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS id_documents (
          id INTEGER PRIMARY KEY,
          order_id INTEGER NOT NULL,
          filename TEXT NOT NULL,
          content_type TEXT NOT NULL,
          storage_name TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS site_settings (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          data TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS whatsapp_conversations (
          wa_id TEXT PRIMARY KEY,
          contact_name TEXT NOT NULL DEFAULT '',
          last_message_at TEXT NOT NULL,
          last_message_preview TEXT NOT NULL DEFAULT '',
          unread_count INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
          id INTEGER PRIMARY KEY,
          wa_message_id TEXT UNIQUE,
          wa_id TEXT NOT NULL,
          direction TEXT NOT NULL,
          message_type TEXT NOT NULL DEFAULT 'text',
          body TEXT NOT NULL DEFAULT '',
          media_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_thread
          ON whatsapp_messages (wa_id, id);
        """
    )
    if "orders" in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        columns = table_columns(conn, "orders")
        if columns and "has_id" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN has_id INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def read_site_file():
    try:
        data = json.loads(SITE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return drop_products(data if isinstance(data, dict) else {})


def drop_products(site):
    services = site.get("services") if isinstance(site, dict) else None
    if not isinstance(services, list):
        return site
    kept = []
    for item in services:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        form = str(item.get("form") or "").strip().lower()
        if name in ("product", "products") or form in ("product", "products"):
            continue
        kept.append(item)
    site = dict(site)
    site["services"] = kept
    return site


def ensure_site_row(conn):
    row = conn.execute("SELECT id FROM site_settings WHERE id = 1").fetchone()
    if row:
        return
    conn.execute(
        "INSERT INTO site_settings (id, data, updated_at) VALUES (1, ?, ?)",
        (json.dumps(read_site_file()), now()),
    )
    conn.commit()


def site_data(conn):
    row = conn.execute("SELECT data FROM site_settings WHERE id = 1").fetchone()
    if not row:
        return read_site_file()
    try:
        data = json.loads(row["data"])
    except json.JSONDecodeError:
        data = read_site_file()
    return drop_products(data if isinstance(data, dict) else read_site_file())


def save_site(conn, data):
    clean = drop_products(data if isinstance(data, dict) else {})
    conn.execute(
        "INSERT INTO site_settings (id, data, updated_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (json.dumps(clean), now()),
    )
    conn.commit()
    return clean


def new_ref(conn):
    for _ in range(40):
        ref = "KBM-" + str(secrets.randbelow(9000) + 1000)
        if not conn.execute("SELECT 1 FROM orders WHERE ref = ?", (ref,)).fetchone():
            return ref
    return "KBM-" + str(int(datetime.now().timestamp()))[-6:]


def session_user(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT token, role, customer_id, expires_at FROM sessions WHERE token = ?",
        (token,),
    ).fetchone()
    if not row or row["expires_at"] < now():
        if row:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        return None
    return row


def public_customer(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"], "phone": row["phone"] or ""}


def order_view(row, include_customer=False):
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    contact = dict(contact)
    contact.pop("idImage", None)
    payload["contact"] = contact
    payload["ref"] = row["ref"]
    payload["status"] = row["status"]
    payload["reply"] = row["reply"] or ""
    payload["placedAt"] = row["created_at"]
    payload["hasId"] = bool(row["has_id"])
    if include_customer:
        payload["customer"] = {
            "email": row["email"] if "email" in row.keys() else "",
            "name": row["customer_name"] if "customer_name" in row.keys() else "",
        }
    return payload


def publish(customer_id, event):
    with listener_lock:
        stale = []
        for item in listeners:
            if item["role"] != "admin" and item["customer_id"] != customer_id:
                continue
            try:
                item["queue"].put_nowait(event)
            except queue.Full:
                stale.append(item)
        for item in stale:
            if item in listeners:
                listeners.remove(item)


def decode_data_url(value):
    text = str(value or "")
    if not text.startswith("data:") or "," not in text:
        return None
    header, encoded = text.split(",", 1)
    mime = header[5:].split(";")[0].strip().lower() or "application/octet-stream"
    if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"):
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > MAX_ID_BYTES:
        return None
    return mime, raw


def store_id(conn, order_id, filename, data_url):
    decoded = decode_data_url(data_url)
    if not decoded:
        return False
    mime, raw = decoded
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "application/pdf": ".pdf"}[mime]
    storage_name = "%s-%s%s" % (order_id, secrets.token_hex(8), ext)
    IDS.mkdir(parents=True, exist_ok=True)
    (IDS / storage_name).write_bytes(raw)
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "", str(filename or "id"))[:80] or "id"
    conn.execute(
        "INSERT INTO id_documents (order_id, filename, content_type, storage_name, created_at) VALUES (?, ?, ?, ?, ?)",
        (order_id, safe_name, mime, storage_name, now()),
    )
    return True


def clean_order(body):
    order = body.get("order") if isinstance(body, dict) else None
    if not isinstance(order, dict):
        return None, "Order is missing."
    services = order.get("services") if isinstance(order.get("services"), list) else []
    service = services[0] if services and isinstance(services[0], dict) else {}
    form = str(service.get("id") or order.get("form") or "").strip().lower()
    if form == "import":
        form = "importation"
    if form == "auctions":
        form = "auction"
    if form not in FORMS:
        return None, "That service is not available."
    goods = order.get("goods") if isinstance(order.get("goods"), dict) else {}
    contact = order.get("contact") if isinstance(order.get("contact"), dict) else {}
    contact = dict(contact)
    image = body.get("idImage") or contact.get("idImage") or ""
    contact.pop("idImage", None)
    name = str(contact.get("name") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    if form == "sourcing":
        link = ""
        links = goods.get("links") if isinstance(goods.get("links"), list) else []
        if links and isinstance(links[0], dict):
            link = str(links[0].get("url") or "")
        if not link.startswith("http://") and not link.startswith("https://"):
            return None, "Paste the product link."
        if not name or not phone:
            return None, "Add your name and phone number."
    elif form == "importation":
        link = ""
        links = goods.get("links") if isinstance(goods.get("links"), list) else []
        if links and isinstance(links[0], dict):
            link = str(links[0].get("url") or "")
        quantity = goods.get("quantity")
        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)
        if not link.startswith("http://") and not link.startswith("https://"):
            return None, "Paste the product link."
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 250:
            return None, "Enter a whole number of at least 250 pieces."
        if not str(goods.get("specification") or "").strip():
            return None, "Add the product specification."
        if not name or not phone or not str(goods.get("wilaya") or contact.get("wilaya") or "").strip():
            return None, "Add your name, phone number, and wilaya."
        if not str(goods.get("address") or contact.get("address") or "").strip():
            return None, "Add the address."
    elif form == "inspection":
        if not str(goods.get("supplierCountry") or "").strip():
            return None, "Add the country of the customer's supplier."
        if not str(goods.get("supplierAddress") or "").strip():
            return None, "Add the address of the customer's supplier."
        if not str(goods.get("supplierPhone") or "").strip():
            return None, "Add the phone number of the supplier."
        if not str(goods.get("checklist") or "").strip():
            return None, "Add the checklist to inspect."
    elif form == "auction":
        bid = goods.get("bid")
        if not str(goods.get("description") or "").strip():
            return None, "Describe the goods."
        if not isinstance(bid, (int, float)) or bid <= 0:
            return None, "Enter a bid greater than 0."
        if not name or not phone:
            return None, "Add your name and phone number."
    if not decode_data_url(image):
        return None, "Add an ID document or scan it with your camera."
    payload = {
        "services": [{
            "id": form,
            "name": str(service.get("name") or form),
            "action": str(service.get("action") or service.get("name") or form),
            "qty": 1,
        }],
        "goods": goods,
        "contact": contact,
        "reviewWindow": order.get("reviewWindow") or "",
        "paymentMethod": "",
    }
    return {"form": form, "payload": payload, "image": image, "filename": contact.get("idFileName") or "id"}, ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def cookie_token(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "kabaman_session":
                return value.strip()
        return ""

    def send_json(self, code, payload, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length < 0 or length > MAX_BODY:
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def set_session(self, token):
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        cookie = "kabaman_session=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d" % (
            token,
            SESSION_DAYS * 24 * 3600,
        )
        return [("Set-Cookie", cookie)]

    def clear_session(self):
        return [("Set-Cookie", "kabaman_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")]

    def current(self):
        with db_lock:
            conn = connect()
            try:
                row = session_user(conn, self.cookie_token())
                if not row:
                    return None, None
                if row["role"] == "admin":
                    return {"role": "admin"}, None
                customer = conn.execute(
                    "SELECT id, email, name, phone FROM customers WHERE id = ?",
                    (row["customer_id"],),
                ).fetchone()
                if not customer:
                    return None, None
                return {"role": "customer", "customer": public_customer(customer)}, customer["id"]
            finally:
                conn.close()

    def require_customer(self):
        me, customer_id = self.current()
        if not me or me["role"] != "customer":
            self.send_json(401, {"error": "Log in required."})
            return None
        return customer_id

    def require_admin(self):
        me, _customer_id = self.current()
        if not me or me["role"] != "admin":
            self.send_json(401, {"error": "Admin login required."})
            return False
        return True

    def whatsapp_webhook_get(self):
        query = parse_qs(urlparse(self.path).query)
        mode = (query.get("hub.mode") or [""])[0]
        token = (query.get("hub.verify_token") or [""])[0]
        challenge = (query.get("hub.challenge") or [""])[0]
        if mode != "subscribe" or not WHATSAPP_VERIFY_TOKEN or not hmac.compare_digest(token, WHATSAPP_VERIFY_TOKEN):
            self.send_error(403)
            return
        body = challenge.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def store_whatsapp_payload(self, payload):
        def message_text(message, kind):
            item = message.get(kind)
            if not isinstance(item, dict):
                return ""
            if kind == "text":
                return str(item.get("body") or "")
            if kind in ("image", "video", "document", "audio", "sticker"):
                caption = str(item.get("caption") or "")
                filename = str(item.get("filename") or "")
                label = {"image": "Photo", "video": "Vidéo", "document": "Document", "audio": "Audio", "sticker": "Sticker"}.get(kind, kind)
                details = filename or caption
                return (label + " — " + details) if details else label + " reçu"
            if kind == "location":
                return "Localisation partagée"
            if kind == "contacts":
                return "Contact partagé"
            if kind == "button":
                return str(item.get("text") or item.get("payload") or "Réponse rapide")
            if kind == "interactive":
                button = item.get("button_reply") or {}
                list_reply = item.get("list_reply") or {}
                return str(button.get("title") or list_reply.get("title") or "Réponse interactive")
            if kind == "reaction":
                return str(item.get("emoji") or "Réaction")
            return str(item.get("text") or item.get("title") or "")

        def message_media_id(message, kind):
            item = message.get(kind)
            if kind not in ("image", "video", "document", "audio", "sticker") or not isinstance(item, dict):
                return ""
            return str(item.get("id") or "")[:200]

        entries = payload.get("entry") or []
        with db_lock:
            conn = connect()
            try:
                for entry in entries:
                    for change in entry.get("changes") or []:
                        value = change.get("value") or {}
                        contacts = {}
                        for contact in value.get("contacts") or []:
                            wa_id = str(contact.get("wa_id") or "")
                            profile = contact.get("profile") or {}
                            if wa_id:
                                contacts[wa_id] = str(profile.get("name") or "")[:120]
                        for message in value.get("messages") or []:
                            wa_id = str(message.get("from") or "")[:100]
                            message_id = str(message.get("id") or "")[:200]
                            kind = str(message.get("type") or "unknown")[:40]
                            if not wa_id or not message_id:
                                continue
                            try:
                                sent_at = datetime.fromtimestamp(int(message.get("timestamp")), timezone.utc).replace(microsecond=0).isoformat()
                            except (TypeError, ValueError, OSError):
                                sent_at = now()
                            body = message_text(message, kind)[:4000]
                            media_id = message_media_id(message, kind)
                            display = body or ("Contenu " + kind)
                            name = contacts.get(wa_id, "")
                            conn.execute(
                                "INSERT INTO whatsapp_conversations (wa_id, contact_name, last_message_at, last_message_preview, unread_count, updated_at) "
                                "VALUES (?, ?, ?, '', 0, ?) ON CONFLICT(wa_id) DO UPDATE SET "
                                "contact_name = CASE WHEN excluded.contact_name <> '' THEN excluded.contact_name ELSE whatsapp_conversations.contact_name END, "
                                "updated_at = excluded.updated_at",
                                (wa_id, name, sent_at, now()),
                            )
                            inserted = conn.execute(
                                "INSERT OR IGNORE INTO whatsapp_messages "
                                "(wa_message_id, wa_id, direction, message_type, body, media_id, status, created_at) "
                                "VALUES (?, ?, 'inbound', ?, ?, ?, 'received', ?)",
                                (message_id, wa_id, kind, body, media_id, sent_at),
                            )
                            if inserted.rowcount:
                                conn.execute(
                                    "UPDATE whatsapp_conversations SET last_message_at = ?, last_message_preview = ?, "
                                    "unread_count = unread_count + 1, updated_at = ? WHERE wa_id = ?",
                                    (sent_at, display[:300], now(), wa_id),
                                )
                        for status in value.get("statuses") or []:
                            message_id = str(status.get("id") or "")
                            state = str(status.get("status") or "")[:40]
                            if message_id and state:
                                conn.execute(
                                    "UPDATE whatsapp_messages SET status = ? WHERE wa_message_id = ?",
                                    (state, message_id),
                                )
                conn.commit()
            finally:
                conn.close()

    def handle_whatsapp_webhook(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > MAX_BODY:
            self.send_json(413 if length > MAX_BODY else 400, {"error": "Invalid webhook body."})
            return
        raw = self.rfile.read(length)
        if not WHATSAPP_APP_SECRET:
            self.send_json(503, {"error": "WhatsApp webhook is not configured."})
            return
        signature = self.headers.get("X-Hub-Signature-256") or ""
        expected = "sha256=" + hmac.new(WHATSAPP_APP_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            self.send_json(403, {"error": "Invalid webhook signature."})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Webhook payload must be an object.")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_json(400, {"error": "Invalid webhook JSON."})
            return
        try:
            self.store_whatsapp_payload(payload)
        except (sqlite3.Error, KeyError, TypeError, ValueError):
            self.send_json(500, {"error": "Could not store WhatsApp webhook."})
            return
        self.send_json(200, {"ok": True})

    def send_whatsapp_reply(self, data):
        if not self.require_admin():
            return
        recipient = str(data.get("to") or "").strip()
        body = str(data.get("text") or "").strip()
        if not recipient or len(recipient) > 100 or not body or len(body) > 4096:
            self.send_json(400, {"error": "Ajoute un destinataire et un message de 1 à 4096 caractères."})
            return
        if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID or not WHATSAPP_GRAPH_VERSION:
            self.send_json(503, {"error": "La connexion WhatsApp Business Platform n’est pas configurée."})
            return
        url = "https://graph.facebook.com/%s/%s/messages" % (
            quote(WHATSAPP_GRAPH_VERSION, safe=""),
            quote(WHATSAPP_PHONE_NUMBER_ID, safe=""),
        )
        request_body = json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={
                "Authorization": "Bearer " + WHATSAPP_ACCESS_TOKEN,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "WhatsApp API error.")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                detail = "WhatsApp API error."
            self.send_json(502, {"error": str(detail)[:300]})
            return
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(502, {"error": "WhatsApp n’a pas pu être joint. Réessaie."})
            return
        messages = result.get("messages") or []
        message_id = str((messages[0] if messages else {}).get("id") or "")
        created = now()
        with db_lock:
            conn = connect()
            try:
                conn.execute(
                    "INSERT INTO whatsapp_conversations (wa_id, contact_name, last_message_at, last_message_preview, unread_count, updated_at) "
                    "VALUES (?, '', ?, ?, 0, ?) ON CONFLICT(wa_id) DO UPDATE SET "
                    "last_message_at = excluded.last_message_at, last_message_preview = excluded.last_message_preview, "
                    "updated_at = excluded.updated_at",
                    (recipient, created, body[:300], created),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO whatsapp_messages "
                    "(wa_message_id, wa_id, direction, message_type, body, media_id, status, created_at) "
                    "VALUES (?, ?, 'outbound', 'text', ?, '', 'sent', ?)",
                    (message_id or None, recipient, body, created),
                )
                conn.commit()
            finally:
                conn.close()
        self.send_json(200, {"ok": True, "id": message_id})

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            self.send_json(200, {"ok": True})
            return
        if path == "/api/me":
            me, _customer_id = self.current()
            self.send_json(200, me or {"role": ""})
            return
        if path == "/api/whatsapp/webhook":
            self.whatsapp_webhook_get()
            return
        if path == "/api/admin/whatsapp/status":
            if not self.require_admin():
                return
            enabled = all((WHATSAPP_VERIFY_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_GRAPH_VERSION))
            self.send_json(200, {"enabled": bool(enabled)})
            return
        if path == "/api/admin/whatsapp/conversations":
            if not self.require_admin():
                return
            with db_lock:
                conn = connect()
                try:
                    rows = conn.execute(
                        "SELECT wa_id, contact_name, last_message_at, last_message_preview, unread_count "
                        "FROM whatsapp_conversations ORDER BY last_message_at DESC"
                    ).fetchall()
                    self.send_json(200, {"conversations": [dict(row) for row in rows]})
                finally:
                    conn.close()
            return
        if path.startswith("/api/admin/whatsapp/conversations/"):
            if not self.require_admin():
                return
            parts = path.split("/")
            wa_id = parts[5] if len(parts) > 5 else ""
            with db_lock:
                conn = connect()
                try:
                    rows = conn.execute(
                        "SELECT wa_message_id, wa_id, direction, message_type, body, status, created_at "
                        "FROM whatsapp_messages WHERE wa_id = ? ORDER BY id",
                        (wa_id,),
                    ).fetchall()
                    self.send_json(200, {"messages": [dict(row) for row in rows]})
                finally:
                    conn.close()
            return
        if path == "/api/site":
            with db_lock:
                conn = connect()
                try:
                    self.send_json(200, site_data(conn))
                finally:
                    conn.close()
            return
        if path == "/api/orders":
            customer_id = self.require_customer()
            if customer_id is None:
                return
            with db_lock:
                conn = connect()
                try:
                    rows = conn.execute(
                        "SELECT * FROM orders WHERE customer_id = ? ORDER BY id",
                        (customer_id,),
                    ).fetchall()
                    self.send_json(200, {"orders": [order_view(row) for row in rows]})
                finally:
                    conn.close()
            return
        if path.startswith("/api/orders/"):
            ref = path.split("/")[3] if len(path.split("/")) >= 4 else ""
            customer_id = self.require_customer()
            if customer_id is None:
                return
            with db_lock:
                conn = connect()
                try:
                    row = conn.execute(
                        "SELECT * FROM orders WHERE ref = ? AND customer_id = ?",
                        (ref, customer_id),
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                self.send_json(404, {"error": "Not found."})
                return
            self.send_json(200, order_view(row))
            return
        if path == "/api/admin/orders":
            if not self.require_admin():
                return
            with db_lock:
                conn = connect()
                try:
                    rows = conn.execute(
                        "SELECT orders.*, customers.email AS email, customers.name AS customer_name "
                        "FROM orders JOIN customers ON customers.id = orders.customer_id ORDER BY orders.id"
                    ).fetchall()
                    self.send_json(200, {"orders": [order_view(row, True) for row in rows]})
                finally:
                    conn.close()
            return
        if path.startswith("/api/admin/orders/") and path.endswith("/id"):
            if not self.require_admin():
                return
            parts = path.split("/")
            ref = parts[4] if len(parts) >= 6 else ""
            self.send_id(ref)
            return
        if path == "/api/events":
            self.stream_events()
            return
        self.serve_static(path)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/whatsapp/webhook":
            self.handle_whatsapp_webhook()
            return
        data = self.read_json()
        if data is None:
            self.send_json(400, {"error": "The request could not be read."})
            return
        if path == "/api/register":
            self.register(data)
            return
        if path == "/api/login":
            self.login(data)
            return
        if path == "/api/logout":
            token = self.cookie_token()
            with db_lock:
                conn = connect()
                try:
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    conn.commit()
                finally:
                    conn.close()
            self.send_json(200, {"ok": True}, self.clear_session())
            return
        if path == "/api/admin/login":
            self.admin_login(data)
            return
        if path == "/api/orders":
            self.create_order(data)
            return
        if path == "/api/admin/whatsapp/send":
            self.send_whatsapp_reply(data)
            return
        if path.startswith("/api/admin/whatsapp/conversations/") and path.endswith("/read"):
            if not self.require_admin():
                return
            parts = path.split("/")
            wa_id = parts[5] if len(parts) > 6 else ""
            with db_lock:
                conn = connect()
                try:
                    conn.execute("UPDATE whatsapp_conversations SET unread_count = 0 WHERE wa_id = ?", (wa_id,))
                    conn.commit()
                finally:
                    conn.close()
            self.send_json(200, {"ok": True})
            return
        if path == "/api/admin/site/reset":
            if not self.require_admin():
                return
            with db_lock:
                conn = connect()
                try:
                    saved = save_site(conn, read_site_file())
                finally:
                    conn.close()
            self.send_json(200, saved)
            return
        self.send_json(404, {"error": "Not found."})

    def do_PUT(self):
        path = unquote(urlparse(self.path).path)
        data = self.read_json()
        if data is None:
            self.send_json(400, {"error": "The request could not be read."})
            return
        if path == "/api/admin/site":
            if not self.require_admin():
                return
            with db_lock:
                conn = connect()
                try:
                    saved = save_site(conn, data)
                finally:
                    conn.close()
            self.send_json(200, saved)
            return
        self.send_json(404, {"error": "Not found."})

    def do_PATCH(self):
        path = unquote(urlparse(self.path).path)
        data = self.read_json()
        if data is None:
            self.send_json(400, {"error": "The request could not be read."})
            return
        if path == "/api/me":
            customer_id = self.require_customer()
            if customer_id is None:
                return
            name = str(data.get("name") or "").strip()
            phone = str(data.get("phone") or "").strip()
            if not name:
                self.send_json(400, {"error": "Add your name."})
                return
            with db_lock:
                conn = connect()
                try:
                    conn.execute("UPDATE customers SET name = ?, phone = ? WHERE id = ?", (name[:100], phone[:40], customer_id))
                    conn.commit()
                    row = conn.execute("SELECT id, email, name, phone FROM customers WHERE id = ?", (customer_id,)).fetchone()
                finally:
                    conn.close()
            self.send_json(200, {"role": "customer", "customer": public_customer(row)})
            return
        if path.startswith("/api/admin/orders/"):
            if not self.require_admin():
                return
            ref = path.split("/")[4] if len(path.split("/")) >= 5 else ""
            self.patch_order(ref, data)
            return
        self.send_json(404, {"error": "Not found."})

    def do_DELETE(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/admin/orders/"):
            if not self.require_admin():
                return
            ref = path.split("/")[4] if len(path.split("/")) >= 5 else ""
            self.delete_order(ref)
            return
        self.send_json(404, {"error": "Not found."})

    def register(self, data):
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        name = str(data.get("name") or "").strip()
        phone = str(data.get("phone") or "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            self.send_json(400, {"error": "Enter a valid email."})
            return
        if len(password) < 8:
            self.send_json(400, {"error": "Use a password of at least 8 characters."})
            return
        if not name:
            self.send_json(400, {"error": "Add your name."})
            return
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
        with db_lock:
            conn = connect()
            try:
                if conn.execute("SELECT 1 FROM customers WHERE email = ?", (email,)).fetchone():
                    self.send_json(409, {"error": "An account with that email already exists."})
                    return
                conn.execute(
                    "INSERT INTO customers (email, name, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (email, name[:100], phone[:40], hash_password(password), now()),
                )
                customer_id = conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()["id"]
                conn.execute(
                    "INSERT INTO sessions (token, role, customer_id, created_at, expires_at) VALUES (?, 'customer', ?, ?, ?)",
                    (token, customer_id, now(), expires),
                )
                conn.commit()
                row = conn.execute("SELECT id, email, name, phone FROM customers WHERE id = ?", (customer_id,)).fetchone()
                profile = public_customer(row)
            finally:
                conn.close()
        self.send_json(201, {"role": "customer", "customer": profile}, self.set_session(token))

    def login(self, data):
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        with db_lock:
            conn = connect()
            try:
                row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
                if not row or not verify_password(password, row["password_hash"]):
                    self.send_json(401, {"error": "Email or password is incorrect."})
                    return
                token = secrets.token_urlsafe(32)
                expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
                conn.execute("DELETE FROM sessions WHERE customer_id = ? AND role = 'customer'", (row["id"],))
                conn.execute(
                    "INSERT INTO sessions (token, role, customer_id, created_at, expires_at) VALUES (?, 'customer', ?, ?, ?)",
                    (token, row["id"], now(), expires),
                )
                conn.commit()
                profile = public_customer(row)
            finally:
                conn.close()
        self.send_json(200, {"role": "customer", "customer": profile}, self.set_session(token))

    def admin_login(self, data):
        password = str(data.get("password") or "")
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            self.send_json(401, {"error": "Incorrect admin password."})
            return
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
        with db_lock:
            conn = connect()
            try:
                conn.execute(
                    "INSERT INTO sessions (token, role, customer_id, created_at, expires_at) VALUES (?, 'admin', NULL, ?, ?)",
                    (token, now(), expires),
                )
                conn.commit()
            finally:
                conn.close()
        self.send_json(200, {"role": "admin"}, self.set_session(token))

    def create_order(self, data):
        customer_id = self.require_customer()
        if customer_id is None:
            return
        cleaned, error = clean_order(data)
        if error:
            self.send_json(400, {"error": error})
            return
        with db_lock:
            conn = connect()
            try:
                ref = new_ref(conn)
                created = now()
                cur = conn.execute(
                    "INSERT INTO orders (ref, customer_id, form, status, reply, payload, has_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'Not verified', '', ?, 0, ?, ?)",
                    (ref, customer_id, cleaned["form"], json.dumps(cleaned["payload"]), created, created),
                )
                order_id = cur.lastrowid
                if not store_id(conn, order_id, cleaned["filename"], cleaned["image"]):
                    conn.rollback()
                    self.send_json(400, {"error": "Add an ID document or scan it with your camera."})
                    return
                conn.execute("UPDATE orders SET has_id = 1 WHERE id = ?", (order_id,))
                conn.commit()
                row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                view = order_view(row)
            finally:
                conn.close()
        publish(customer_id, {"type": "order", "ref": ref, "status": "Not verified", "reply": ""})
        self.send_json(201, view)

    def patch_order(self, ref, data):
        status = data.get("status")
        reply = data.get("reply")
        with db_lock:
            conn = connect()
            try:
                row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
                if not row:
                    self.send_json(404, {"error": "Not found."})
                    return
                next_status = row["status"]
                next_reply = row["reply"]
                if status is not None:
                    if status not in STATUSES:
                        self.send_json(400, {"error": "Unknown status."})
                        return
                    next_status = status
                if reply is not None:
                    next_reply = str(reply)[:500]
                conn.execute(
                    "UPDATE orders SET status = ?, reply = ?, updated_at = ? WHERE id = ?",
                    (next_status, next_reply, now(), row["id"]),
                )
                conn.commit()
                updated = conn.execute(
                    "SELECT orders.*, customers.email AS email, customers.name AS customer_name "
                    "FROM orders JOIN customers ON customers.id = orders.customer_id WHERE orders.id = ?",
                    (row["id"],),
                ).fetchone()
                customer_id = row["customer_id"]
                view = order_view(updated, True)
            finally:
                conn.close()
        publish(customer_id, {"type": "order", "ref": ref, "status": next_status, "reply": next_reply})
        self.send_json(200, view)

    def delete_order(self, ref):
        with db_lock:
            conn = connect()
            try:
                row = conn.execute("SELECT id, customer_id FROM orders WHERE ref = ?", (ref,)).fetchone()
                if not row:
                    self.send_json(404, {"error": "Not found."})
                    return
                files = conn.execute("SELECT storage_name FROM id_documents WHERE order_id = ?", (row["id"],)).fetchall()
                conn.execute("DELETE FROM id_documents WHERE order_id = ?", (row["id"],))
                conn.execute("DELETE FROM orders WHERE id = ?", (row["id"],))
                conn.commit()
                customer_id = row["customer_id"]
            finally:
                conn.close()
        for item in files:
            try:
                (IDS / item["storage_name"]).unlink(missing_ok=True)
            except OSError:
                pass
        publish(customer_id, {"type": "order", "ref": ref, "status": "deleted", "reply": ""})
        self.send_json(200, {"ok": True})

    def send_id(self, ref):
        with db_lock:
            conn = connect()
            try:
                row = conn.execute(
                    "SELECT id_documents.storage_name, id_documents.content_type, id_documents.filename "
                    "FROM id_documents JOIN orders ON orders.id = id_documents.order_id WHERE orders.ref = ? "
                    "ORDER BY id_documents.id DESC LIMIT 1",
                    (ref,),
                ).fetchone()
            finally:
                conn.close()
        if not row:
            self.send_json(404, {"error": "Not found."})
            return
        path = (IDS / row["storage_name"]).resolve()
        if not str(path).startswith(str(IDS.resolve())) or not path.is_file():
            self.send_json(404, {"error": "Not found."})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", row["content_type"])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", "inline")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def stream_events(self):
        me, customer_id = self.current()
        if not me:
            self.send_json(401, {"error": "Log in required."})
            return
        item = {"role": me["role"], "customer_id": customer_id, "queue": queue.Queue(20)}
        with listener_lock:
            listeners.append(item)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b": ok\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = item["queue"].get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                message = "data: " + json.dumps(event) + "\n\n"
                self.wfile.write(message.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with listener_lock:
                if item in listeners:
                    listeners.remove(item)

    def serve_static(self, path):
        rel = path.lstrip("/") or "index.html"
        rel = rel.split("?", 1)[0]
        if rel.startswith("data/") or rel.startswith("data\\") or rel.lower() == "server.py":
            self.send_error(404)
            return
        full = (ROOT / rel).resolve()
        if not str(full).startswith(str(ROOT.resolve())) or not full.is_file():
            self.send_error(404)
            return
        ext = full.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }
        body = full.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", types.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        if ext in (".html", ".js", ".css", ".json"):
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main():
    global ADMIN_PASSWORD
    DATA.mkdir(parents=True, exist_ok=True)
    IDS.mkdir(parents=True, exist_ok=True)
    ADMIN_PASSWORD = load_admin_password()
    with db_lock:
        conn = connect()
        try:
            migrate(conn)
            ensure_site_row(conn)
        finally:
            conn.close()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("KABAMAN server at http://%s:%d/" % (HOST, PORT))
    print("Admin sign-in uses KABAMAN_ADMIN_PASSWORD, or the local file data/admin.config.json. The password is not printed.")
    server.serve_forever()


if __name__ == "__main__":
    main()

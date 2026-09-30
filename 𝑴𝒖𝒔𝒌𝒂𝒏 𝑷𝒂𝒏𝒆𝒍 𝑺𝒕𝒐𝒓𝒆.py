import os
import sqlite3
import logging
from datetime import datetime

import telebot
from telebot import types

try:
    import qrcode
except ImportError:
    qrcode = None

# ============================================================
# 𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆 - Professional Telegram Selling Store
# Stack: Python 3 + pyTelegramBotAPI + SQLite
# ============================================================
# IMPORTANT: set these in Termux before running:
# export BOT_TOKEN="YOUR_BOTFATHER_TOKEN"
# export ADMIN_ID="YOUR_TELEGRAM_NUMERIC_ID"
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8782071636:AAF2Rs1m_9um57Xjh2l7BInrEYcJaGwrfdg").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "7940269685") or 0)
DB = "muskan_panel_store.db"

if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise SystemExit("Set BOT_TOKEN first.")
if ADMIN_ID <= 0:
    raise SystemExit("Set ADMIN_ID first.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Temporary admin input state. Normal data is stored in SQLite.
ADMIN_INPUT = {}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def money(value):
    return f"₹{float(value):,.2f}"


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            blocked INTEGER DEFAULT 0,
            referred_by INTEGER,
            referral_rewarded INTEGER DEFAULT 0,
            joined_at TEXT,
            updated_at TEXT,
            last_seen TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            delivery TEXT DEFAULT '',
            stock INTEGER DEFAULT -1,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'completed',
            delivery TEXT DEFAULT '',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            entry_type TEXT NOT NULL,
            reference TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            utr TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value REAL NOT NULL,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            expires_at TEXT DEFAULT '',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS coupon_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coupon_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            used_at TEXT,
            UNIQUE(coupon_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT DEFAULT '',
            message TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            admin_reply TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TEXT
        );
        """
    )
    defaults = {
        "store_name": "𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆",
        "store_tagline": "Premium Digital Store",
        "upi_id": "",
        "upi_name": "",
        "qr_file_id": "",
        "min_deposit": "10",
        "max_deposit": "50000",
        "deposit_amounts": "100,200,500,1000",
        "referral_reward": "0",
        "referral_enabled": "1",
        "support_username": "",
        "support_text": "Contact support for help.",
        "howto_text": "Add balance → pay by UPI → submit UTR → wait for admin verification → buy products.",
        "maintenance": "0",
        "welcome_text": "Welcome to 𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def setting(key, default=""):
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = db()
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def audit(action, details=""):
    conn = db()
    conn.execute(
        "INSERT INTO audit_log(admin_id,action,details,created_at) VALUES(?,?,?,?)",
        (ADMIN_ID, action, details, now()),
    )
    conn.commit()
    conn.close()


def save_user(user, referral_id=None):
    conn = db()
    existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    username = user.username or ""
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    if existing:
        conn.execute(
            "UPDATE users SET first_name=?,last_name=?,username=?,updated_at=?,last_seen=? WHERE user_id=?",
            (first_name, last_name, username, now(), now(), user.id),
        )
    else:
        ref = referral_id if referral_id and int(referral_id) != int(user.id) else None
        conn.execute(
            """INSERT INTO users
            (user_id,first_name,last_name,username,referred_by,joined_at,updated_at,last_seen)
            VALUES(?,?,?,?,?,?,?,?)""",
            (user.id, first_name, last_name, username, ref, now(), now(), now()),
        )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row


def blocked(user_id):
    row = get_user(user_id)
    return bool(row and row["blocked"])


def user_label(row):
    username = f"@{row['username']}" if row["username"] else "No username"
    return f"{row['first_name'] or 'No name'} • {username} • {row['user_id']}"


def safe_send(user_id, text, **kwargs):
    try:
        bot.send_message(user_id, text, **kwargs)
        return True
    except Exception as exc:
        logging.warning("Send failed to %s: %s", user_id, exc)
        return False


# ----------------------------- Keyboards -----------------------------

def user_menu(user_id=None):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🛍️ Shop", callback_data="shop"),
        types.InlineKeyboardButton("💰 Add Balance", callback_data="deposit"),
    )
    k.add(
        types.InlineKeyboardButton("💳 Wallet", callback_data="wallet"),
        types.InlineKeyboardButton("📦 My Orders", callback_data="orders"),
    )
    k.add(
        types.InlineKeyboardButton("👤 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("📜 Transactions", callback_data="transactions"),
    )
    k.add(
        types.InlineKeyboardButton("🎁 Referral", callback_data="referral"),
        types.InlineKeyboardButton("🎟️ Coupon", callback_data="coupon"),
    )
    k.add(
        types.InlineKeyboardButton("🎫 Support", callback_data="support"),
        types.InlineKeyboardButton("📖 How To Use", callback_data="howto"),
    )
    if user_id is not None and is_admin(user_id):
        k.add(types.InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_home"))
    return k


def admin_menu():
    k = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📊 Dashboard", "a_dashboard"),
        ("👥 User Manager", "a_users"),
        ("🛍️ Product Manager", "a_products"),
        ("💰 Payment / UPI", "a_payments"),
        ("📦 Order Manager", "a_orders"),
        ("💳 Wallet Control", "a_wallet"),
        ("🎟️ Coupon Manager", "a_coupons"),
        ("📢 Broadcast", "a_broadcast"),
        ("🎫 Support Tickets", "a_tickets"),
        ("🎁 Referral", "a_referral"),
        ("📈 Reports", "a_reports"),
        ("⚙️ Store Settings", "a_settings"),
        ("🛠️ Maintenance", "a_maintenance"),
        ("📜 Audit Log", "a_audit"),
        ("❓ Admin Help", "a_help"),
    ]
    for text, data in buttons:
        k.add(types.InlineKeyboardButton(text, callback_data=data))
    k.add(types.InlineKeyboardButton("👤 User Panel", callback_data="home"))
    return k


def back_home():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="home"))
    return k


def back_admin():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    return k


def edit_message(call, text, markup=None):
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)


# ----------------------------- User UI -----------------------------

def show_home(chat_id, user_id):
    u = get_user(user_id)
    name = u["first_name"] if u else "User"
    balance = money(u["balance"]) if u else money(0)
    text = (
        f"╔══════════════════════════╗\n"
        f"     ✦ <b>{setting('store_name')}</b> ✦\n"
        f"╚══════════════════════════╝\n\n"
        f"👋 Welcome, <b>{name}</b>\n"
        f"💳 Wallet: <b>{balance}</b>\n\n"
        f"✨ {setting('store_tagline')}\n"
        f"🔐 Secure wallet & order history\n\n"
        f"Select an option below:"
    )
    bot.send_message(chat_id, text, reply_markup=user_menu(user_id))


def show_shop(chat_id):
    conn = db()
    products = conn.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    k = types.InlineKeyboardMarkup(row_width=1)
    for product in products:
        stock = "∞" if product["stock"] < 0 else str(product["stock"])
        k.add(
            types.InlineKeyboardButton(
                f"🛍️ {product['name']} • {money(product['price'])} • Stock {stock}",
                callback_data=f"product:{product['id']}",
            )
        )
    k.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="home"))
    text = "🛍️ <b>𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆</b>\n\nChoose a product:" if products else "🛍️ <b>SHOP</b>\n\nNo active products right now."
    bot.send_message(chat_id, text, reply_markup=k)


def show_product(call, product_id):
    conn = db()
    product = conn.execute(
        "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
    ).fetchone()
    conn.close()
    if not product:
        bot.answer_callback_query(call.id, "Product unavailable.")
        return
    stock = "Unlimited" if product["stock"] < 0 else str(product["stock"])
    k = types.InlineKeyboardMarkup(row_width=1)
    k.add(types.InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy:{product_id}"))
    k.add(types.InlineKeyboardButton("🔙 Shop", callback_data="shop"))
    text = (
        f"🛍️ <b>{product['name']}</b>\n\n"
        f"📝 {product['description'] or 'Premium digital product'}\n\n"
        f"💵 Price: <b>{money(product['price'])}</b>\n"
        f"📦 Stock: <b>{stock}</b>\n\n"
        f"⚡ Delivery:\n{product['delivery'] or 'Contact support after purchase.'}"
    )
    edit_message(call, text, k)


def buy_product(call, product_id):
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        product = conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
        ).fetchone()
        user = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (call.from_user.id,)
        ).fetchone()
        if not product or not user:
            raise ValueError("Product unavailable.")
        if product["stock"] == 0:
            raise ValueError("Out of stock.")
        price = float(product["price"])
        balance = float(user["balance"])
        if balance < price:
            raise ValueError(f"Insufficient balance. Need {money(price - balance)} more.")
        new_balance = round(balance - price, 2)
        conn.execute(
            "UPDATE users SET balance=?,updated_at=? WHERE user_id=?",
            (new_balance, now(), call.from_user.id),
        )
        if product["stock"] > 0:
            conn.execute(
                "UPDATE products SET stock=stock-1,updated_at=? WHERE id=?",
                (now(), product_id),
            )
        cur = conn.execute(
            """INSERT INTO orders
            (user_id,product_id,product_name,amount,status,delivery,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (
                call.from_user.id,
                product_id,
                product["name"],
                price,
                "completed",
                product["delivery"],
                now(),
            ),
        )
        order_id = cur.lastrowid
        conn.execute(
            """INSERT INTO wallet_ledger
            (user_id,amount,balance_after,entry_type,reference,note,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (
                call.from_user.id,
                -price,
                new_balance,
                "debit",
                f"ORDER-{order_id}",
                product["name"],
                now(),
            ),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        bot.answer_callback_query(call.id, str(exc)[:180])
        conn.close()
        return
    conn.close()
    bot.answer_callback_query(call.id, "Purchase successful")
    text = (
        "╔══════════════════════╗\n"
        "       ✅ <b>ORDER SUCCESS</b>\n"
        "╚══════════════════════╝\n\n"
        f"📦 Order ID: <code>#{order_id}</code>\n"
        f"🛍️ Product: <b>{product['name']}</b>\n"
        f"💵 Paid: <b>{money(price)}</b>\n"
        f"💳 Remaining: <b>{money(new_balance)}</b>\n\n"
        f"📨 <b>Delivery</b>\n{product['delivery'] or 'Please contact support.'}"
    )
    bot.send_message(call.message.chat.id, text, reply_markup=back_home())


def wallet(chat_id, user_id):
    u = get_user(user_id)
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("➕ Add Balance", callback_data="deposit"),
        types.InlineKeyboardButton("📜 Transactions", callback_data="transactions"),
    )
    k.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="home"))
    bot.send_message(
        chat_id,
        f"💳 <b>MY WALLET</b>\n\n💰 Balance: <b>{money(u['balance'])}</b>\n\n"
        "Wallet credit is added only after admin verifies your UPI payment.",
        reply_markup=k,
    )


def transactions(chat_id, user_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM wallet_ledger WHERE user_id=? ORDER BY id DESC LIMIT 20",
        (user_id,),
    ).fetchall()
    conn.close()
    if not rows:
        text = "📜 <b>TRANSACTIONS</b>\n\nNo wallet transactions yet."
    else:
        parts = []
        for row in rows:
            sign = "+" if row["amount"] >= 0 else ""
            parts.append(
                f"#{row['id']} • <b>{sign}{money(row['amount'])}</b>\n"
                f"{row['entry_type']} • {row['reference'] or '-'}\n"
                f"Balance: {money(row['balance_after'])}\n{row['created_at']}"
            )
        text = "📜 <b>WALLET TRANSACTIONS</b>\n\n" + "\n\n".join(parts)
    bot.send_message(chat_id, text, reply_markup=back_home())


def profile(chat_id, user_id):
    u = get_user(user_id)
    username = f"@{u['username']}" if u["username"] else "Not set"
    conn = db()
    orders_count = conn.execute("SELECT COUNT(*) c FROM orders WHERE user_id=?", (user_id,)).fetchone()["c"]
    deposits_count = conn.execute("SELECT COUNT(*) c FROM deposits WHERE user_id=? AND status='approved'", (user_id,)).fetchone()["c"]
    conn.close()
    text = (
        "👤 <b>MY PROFILE</b>\n\n"
        f"🆔 User ID: <code>{u['user_id']}</code>\n"
        f"👤 Name: <b>{u['first_name'] or 'Not set'}</b>\n"
        f"🔗 Username: <b>{username}</b>\n"
        f"💰 Balance: <b>{money(u['balance'])}</b>\n"
        f"📦 Orders: <b>{orders_count}</b>\n"
        f"💳 Approved Deposits: <b>{deposits_count}</b>\n"
        f"📅 Joined: <b>{u['joined_at']}</b>"
    )
    bot.send_message(chat_id, text, reply_markup=back_home())


def orders(chat_id, user_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    conn.close()
    if not rows:
        text = "📦 <b>MY ORDERS</b>\n\nNo orders yet."
    else:
        text = "📦 <b>MY ORDERS</b>\n\n" + "\n\n".join(
            f"#{r['id']} • <b>{r['product_name']}</b>\n"
            f"Amount: {money(r['amount'])} • {r['status']}\n{r['created_at']}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_home())


def referral(chat_id, user_id):
    if setting("referral_enabled", "1") != "1":
        bot.send_message(chat_id, "🎁 <b>REFERRAL</b>\n\nReferral system is currently disabled.", reply_markup=back_home())
        return
    me = bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id}"
    conn = db()
    count = conn.execute("SELECT COUNT(*) c FROM users WHERE referred_by=?", (user_id,)).fetchone()["c"]
    conn.close()
    reward = money(setting("referral_reward", "0"))
    text = (
        "🎁 <b>REFERRAL PROGRAM</b>\n\n"
        f"🔗 Your link:\n<code>{link}</code>\n\n"
        f"👥 Referred users: <b>{count}</b>\n"
        f"💵 Reward per eligible referral: <b>{reward}</b>"
    )
    bot.send_message(chat_id, text, reply_markup=back_home())


def show_deposit(chat_id, user_id):
    min_amount = float(setting("min_deposit", "10"))
    max_amount = float(setting("max_deposit", "50000"))
    amounts = []
    for raw in setting("deposit_amounts", "100,200,500,1000").split(","):
        try:
            amount = float(raw.strip())
            if min_amount <= amount <= max_amount:
                amounts.append(amount)
        except ValueError:
            continue

    k = types.InlineKeyboardMarkup(row_width=2)
    for amount in amounts[:20]:
        label = f"₹{int(amount) if amount.is_integer() else amount:g}"
        k.add(types.InlineKeyboardButton(label, callback_data=f"depamt:{amount:g}"))
    k.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="home"))

    if not setting("upi_id"):
        text = (
            "💰 <b>ADD BALANCE</b>\n\n"
            "UPI payment is not configured yet.\n"
            "Please contact the store administrator."
        )
    else:
        text = (
            "💰 <b>ADD BALANCE</b>\n\n"
            f"Select an amount between {money(min_amount)} and {money(max_amount)}.\n\n"
            "The QR/payment instructions will appear only when the admin has configured a valid UPI ID."
        )
    bot.send_message(chat_id, text, reply_markup=k)


def send_payment_request(chat_id, user_id, amount):
    upi_id = setting("upi_id").strip()
    upi_name = setting("upi_name").strip() or setting("store_name")
    if not upi_id:
        bot.send_message(chat_id, "❌ UPI is not configured by the admin yet.", reply_markup=back_home())
        return

    conn = db()
    pending = conn.execute(
        "SELECT * FROM deposits WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if pending:
        bot.send_message(
            chat_id,
            f"⏳ You already have a pending payment request <b>#{pending['id']}</b> for {money(pending['amount'])}.\n\nWait for admin review before creating another request.",
            reply_markup=back_home(),
        )
        return

    qr_file_id = setting("qr_file_id").strip()
    upi_uri = f"upi://pay?pa={upi_id}&pn={upi_name}&am={amount:.2f}&cu=INR"
    k = types.InlineKeyboardMarkup(row_width=1)
    k.add(types.InlineKeyboardButton("🧾 I Have Paid — Submit UTR", callback_data=f"utr:{amount:g}"))
    k.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="home"))

    caption = (
        "💳 <b>UPI PAYMENT</b>\n\n"
        f"💰 Amount: <b>{money(amount)}</b>\n"
        f"🏦 UPI ID: <code>{upi_id}</code>\n"
        f"👤 Name: <b>{upi_name}</b>\n\n"
        "1️⃣ Pay the exact amount.\n"
        "2️⃣ Keep your UTR/reference number.\n"
        "3️⃣ Tap the button below and submit the UTR.\n\n"
        "⚠️ Wallet credit happens only after admin verification."
    )

    # FIX: never generate/show a random QR. A QR is shown only when a valid UPI ID
    # exists, and a custom admin-uploaded QR takes priority over generated QR.
    if qr_file_id:
        bot.send_photo(chat_id, qr_file_id, caption=caption, reply_markup=k)
        return

    if qrcode is None:
        bot.send_message(chat_id, caption + "\n\n📷 QR image is not configured. Use the UPI ID above.", reply_markup=k)
        return

    try:
        qr = qrcode.QRCode(box_size=8, border=4)
        qr.add_data(upi_uri)
        qr.make(fit=True)
        image = qr.make_image()
        stream = __import__("io").BytesIO()
        image.save(stream, format="PNG")
        stream.seek(0)
        bot.send_photo(chat_id, stream, caption=caption, reply_markup=k)
    except Exception:
        bot.send_message(chat_id, caption + "\n\n📷 QR could not be generated. Use the UPI ID above.", reply_markup=k)


def receive_utr(message, amount):
    if message.chat.type != "private":
        return
    if blocked(message.from_user.id):
        return
    utr = (message.text or "").strip()
    if len(utr) < 4 or len(utr) > 80 or " " in utr:
        bot.send_message(message.chat.id, "❌ Invalid UTR/reference. Send the exact UTR without spaces.")
        return
    try:
        amount = float(amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid payment amount.")
        return
    min_amount = float(setting("min_deposit", "10"))
    max_amount = float(setting("max_deposit", "50000"))
    if not min_amount <= amount <= max_amount:
        bot.send_message(message.chat.id, "❌ Payment amount is outside the allowed range.")
        return

    conn = db()
    duplicate = conn.execute("SELECT id FROM deposits WHERE utr=?", (utr,)).fetchone()
    pending = conn.execute(
        "SELECT id FROM deposits WHERE user_id=? AND status='pending'", (message.from_user.id,)
    ).fetchone()
    if duplicate:
        conn.close()
        bot.send_message(message.chat.id, "❌ This UTR has already been submitted.", reply_markup=back_home())
        return
    if pending:
        conn.close()
        bot.send_message(message.chat.id, "⏳ You already have a pending payment request.", reply_markup=back_home())
        return
    conn.execute(
        "INSERT INTO deposits(user_id,amount,utr,status,created_at) VALUES(?,?,?,?,?)",
        (message.from_user.id, amount, utr, "pending", now()),
    )
    conn.commit()
    deposit_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    conn.close()

    bot.send_message(
        message.chat.id,
        f"⏳ <b>PAYMENT SUBMITTED</b>\n\nRequest: <code>#{deposit_id}</code>\nAmount: <b>{money(amount)}</b>\nUTR: <code>{utr}</code>\n\nWait for admin verification.",
        reply_markup=back_home(),
    )
    notify_admin_payment(deposit_id)


def notify_admin_payment(deposit_id):
    conn = db()
    row = conn.execute(
        "SELECT d.*,u.first_name,u.username FROM deposits d LEFT JOIN users u ON u.user_id=d.user_id WHERE d.id=?",
        (deposit_id,),
    ).fetchone()
    conn.close()
    if not row:
        return
    username = f"@{row['username']}" if row["username"] else "No username"
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔎 Review", callback_data=f"depview:{deposit_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"depreject:{deposit_id}"),
    )
    safe_send(
        ADMIN_ID,
        "🔔 <b>NEW PAYMENT REQUEST</b>\n\n"
        f"Request: <code>#{deposit_id}</code>\n"
        f"User ID: <code>{row['user_id']}</code>\n"
        f"Name: <b>{row['first_name'] or 'Unknown'}</b>\n"
        f"Username: <b>{username}</b>\n"
        f"Amount: <b>{money(row['amount'])}</b>\n"
        f"UTR: <code>{row['utr']}</code>\n"
        f"Created: {row['created_at']}",
        reply_markup=k,
    )


def apply_referral_reward(new_user_id):
    reward = float(setting("referral_reward", "0") or 0)
    if reward <= 0 or setting("referral_enabled", "1") != "1":
        return
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    new_user = conn.execute("SELECT * FROM users WHERE user_id=?", (new_user_id,)).fetchone()
    if not new_user or not new_user["referred_by"] or new_user["referral_rewarded"]:
        conn.rollback()
        conn.close()
        return
    referrer = conn.execute("SELECT * FROM users WHERE user_id=?", (new_user["referred_by"],)).fetchone()
    if not referrer or referrer["blocked"]:
        conn.rollback()
        conn.close()
        return
    new_balance = round(float(referrer["balance"]) + reward, 2)
    conn.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, referrer["user_id"]))
    conn.execute("UPDATE users SET referral_rewarded=1 WHERE user_id=?", (new_user_id,))
    conn.execute(
        """INSERT INTO wallet_ledger(user_id,amount,balance_after,entry_type,reference,note,created_at)
        VALUES(?,?,?,?,?,?,?)""",
        (referrer["user_id"], reward, new_balance, "referral", f"REF-{new_user_id}", "Referral reward", now()),
    )
    conn.commit()
    conn.close()
    safe_send(referrer["user_id"], f"🎁 Referral reward credited: <b>{money(reward)}</b>")


# ----------------------------- Admin UI -----------------------------

def admin_panel(chat_id):
    bot.send_message(
        chat_id,
        "╔══════════════════════════╗\n"
        "       🔐 <b>ADMIN CONTROL CENTER</b>\n"
        "╚══════════════════════════╝\n\n"
        "Manage users, wallet, UPI, products, orders, coupons, tickets, reports and store settings.",
        reply_markup=admin_menu(),
    )


def a_dashboard(chat_id):
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    blocked_users = conn.execute("SELECT COUNT(*) c FROM users WHERE blocked=1").fetchone()["c"]
    today_users = conn.execute("SELECT COUNT(*) c FROM users WHERE joined_at LIKE ?", (datetime.now().strftime("%Y-%m-%d") + "%",)).fetchone()["c"]
    total_orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    total_sales = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status='completed'").fetchone()["s"]
    pending = conn.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]
    approved = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE status='approved'").fetchone()["s"]
    products = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    active_products = conn.execute("SELECT COUNT(*) c FROM products WHERE active=1").fetchone()["c"]
    open_tickets = conn.execute("SELECT COUNT(*) c FROM tickets WHERE status='open'").fetchone()["c"]
    wallet_total = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"]
    conn.close()
    text = (
        "📊 <b>STORE DASHBOARD</b>\n\n"
        f"👥 Total Users: <b>{total_users}</b>\n"
        f"🟢 Active Users: <b>{total_users - blocked_users}</b>\n"
        f"🚫 Blocked Users: <b>{blocked_users}</b>\n"
        f"🆕 Joined Today: <b>{today_users}</b>\n\n"
        f"🛍️ Products: <b>{products}</b> | Active: <b>{active_products}</b>\n"
        f"📦 Total Orders: <b>{total_orders}</b>\n"
        f"💵 Sales: <b>{money(total_sales)}</b>\n"
        f"💳 Approved Deposits: <b>{money(approved)}</b>\n"
        f"⏳ Pending Payments: <b>{pending}</b>\n"
        f"💰 User Wallet Total: <b>{money(wallet_total)}</b>\n"
        f"🎫 Open Tickets: <b>{open_tickets}</b>\n\n"
        f"🟢 UPI: <b>{'Configured' if setting('upi_id') else 'Not configured'}</b>\n"
        f"🛠️ Maintenance: <b>{'ON' if setting('maintenance') == '1' else 'OFF'}</b>"
    )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_users(chat_id, page=0):
    page = max(0, int(page))
    limit = 12
    offset = page * limit
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) c FROM users WHERE blocked=0").fetchone()["c"]
    blocked_count = conn.execute("SELECT COUNT(*) c FROM users WHERE blocked=1").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id" if False else "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    text = (
        "👥 <b>USER MANAGEMENT</b>\n\n"
        f"👤 Total Users: <b>{total}</b>\n"
        f"🟢 Active: <b>{active}</b>\n"
        f"🚫 Blocked: <b>{blocked_count}</b>\n\n"
        "Use the buttons to inspect individual users."
    )
    k = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        status = "🚫" if row["blocked"] else "🟢"
        uname = f"@{row['username']}" if row["username"] else "NoUsername"
        k.add(types.InlineKeyboardButton(f"{status} {row['user_id']} • {row['first_name'] or 'No name'} • {uname}", callback_data=f"auser:{row['user_id']}:{page}"))
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ Previous", callback_data=f"ausers:{page-1}"))
    if offset + len(rows) < total:
        nav.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"ausers:{page+1}"))
    if nav:
        k.row(*nav)
    k.add(types.InlineKeyboardButton("🔎 Search User", callback_data="asearch_user"))
    k.add(types.InlineKeyboardButton("📋 User ID List", callback_data="auser_ids"))
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    bot.send_message(chat_id, text, reply_markup=k)


def a_user_detail(call, user_id, page=0):
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        bot.answer_callback_query(call.id, "User not found.")
        return
    order_count = conn.execute("SELECT COUNT(*) c FROM orders WHERE user_id=?", (user_id,)).fetchone()["c"]
    spent = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE user_id=?", (user_id,)).fetchone()["s"]
    deposits = conn.execute("SELECT COUNT(*) c FROM deposits WHERE user_id=? AND status='approved'", (user_id,)).fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) c FROM deposits WHERE user_id=? AND status='pending'", (user_id,)).fetchone()["c"]
    conn.close()
    username = f"@{user['username']}" if user["username"] else "No username"
    status = "🚫 BLOCKED" if user["blocked"] else "🟢 ACTIVE"
    text = (
        "👤 <b>USER DETAILS</b>\n\n"
        f"🆔 User ID: <code>{user['user_id']}</code>\n"
        f"👤 Name: <b>{user['first_name'] or 'No name'} {user['last_name'] or ''}</b>\n"
        f"🔗 Username: <b>{username}</b>\n"
        f"💰 Balance: <b>{money(user['balance'])}</b>\n"
        f"📦 Orders: <b>{order_count}</b>\n"
        f"💵 Total Spent: <b>{money(spent)}</b>\n"
        f"💳 Approved Deposits: <b>{deposits}</b>\n"
        f"⏳ Pending Deposits: <b>{pending}</b>\n"
        f"📅 Joined: {user['joined_at']}\n"
        f"🕐 Last Seen: {user['last_seen']}\n"
        f"📌 Status: <b>{status}</b>"
    )
    k = types.InlineKeyboardMarkup(row_width=2)
    if user["blocked"]:
        k.add(types.InlineKeyboardButton("🟢 Unblock", callback_data=f"unblock:{user_id}"))
    else:
        k.add(types.InlineKeyboardButton("🚫 Block", callback_data=f"block:{user_id}"))
    k.add(types.InlineKeyboardButton("💰 Adjust Balance", callback_data=f"adjbal:{user_id}"))
    k.add(types.InlineKeyboardButton("📦 Orders", callback_data=f"uorders:{user_id}"))
    k.add(types.InlineKeyboardButton("💳 Payments", callback_data=f"udep:{user_id}"))
    k.add(types.InlineKeyboardButton("🔙 Users", callback_data=f"ausers:{page}"))
    edit_message(call, text, k)


def a_user_ids(chat_id):
    conn = db()
    rows = conn.execute("SELECT user_id,first_name,username,blocked FROM users ORDER BY joined_at DESC LIMIT 100").fetchall()
    conn.close()
    if not rows:
        text = "📋 <b>USER LIST</b>\n\nNo users found."
    else:
        lines = []
        for row in rows:
            uname = f"@{row['username']}" if row["username"] else "No username"
            status = "BLOCKED" if row["blocked"] else "ACTIVE"
            lines.append(f"<code>{row['user_id']}</code> • {row['first_name'] or 'No name'} • {uname} • {status}")
        text = "📋 <b>USER ID / USERNAME LIST</b>\n\n" + "\n".join(lines)
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_search_user(chat_id):
    msg = bot.send_message(chat_id, "🔎 <b>SEARCH USER</b>\n\nSend User ID or username:")
    bot.register_next_step_handler(msg, process_user_search)


def process_user_search(message):
    query = (message.text or "").strip().lstrip("@")
    conn = db()
    row = None
    if query.isdigit():
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (int(query),)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (query,)).fetchone()
    conn.close()
    if not row:
        bot.send_message(message.chat.id, "❌ User not found.", reply_markup=back_admin())
        return
    # Send a fresh detail message for a clean admin flow.
    username = f"@{row['username']}" if row["username"] else "No username"
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("👤 Open Full Details", callback_data=f"auser:{row['user_id']}:0"))
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    bot.send_message(
        message.chat.id,
        f"🔎 <b>USER FOUND</b>\n\nID: <code>{row['user_id']}</code>\nName: <b>{row['first_name'] or 'No name'}</b>\nUsername: <b>{username}</b>\nBalance: <b>{money(row['balance'])}</b>",
        reply_markup=k,
    )


def a_products(chat_id):
    conn = db()
    rows = conn.execute("SELECT * FROM products ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    k = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        status = "🟢" if row["active"] else "🔴"
        k.add(types.InlineKeyboardButton(f"{status} #{row['id']} {row['name']} • {money(row['price'])}", callback_data=f"aprod:{row['id']}"))
    k.add(types.InlineKeyboardButton("➕ Add Product", callback_data="addproduct"))
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    text = "🛍️ <b>PRODUCT MANAGER</b>\n\nSelect a product or add a new one."
    bot.send_message(chat_id, text, reply_markup=k)


def a_product_detail(call, product_id):
    conn = db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "Product not found.")
        return
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🟢 Enable", callback_data=f"ptoggle:{product_id}:1"),
        types.InlineKeyboardButton("🔴 Disable", callback_data=f"ptoggle:{product_id}:0"),
    )
    k.add(types.InlineKeyboardButton("🗑️ Delete", callback_data=f"pdelete:{product_id}"))
    k.add(types.InlineKeyboardButton("🔙 Products", callback_data="a_products"))
    text = (
        f"🛍️ <b>PRODUCT #{product_id}</b>\n\n"
        f"Name: <b>{row['name']}</b>\n"
        f"Price: <b>{money(row['price'])}</b>\n"
        f"Stock: <b>{'Unlimited' if row['stock'] < 0 else row['stock']}</b>\n"
        f"Status: <b>{'Enabled' if row['active'] else 'Disabled'}</b>\n\n"
        f"Description:\n{row['description'] or '-'}\n\n"
        f"Delivery:\n{row['delivery'] or '-'}"
    )
    edit_message(call, text, k)


def a_payments(chat_id):
    conn = db()
    pending = conn.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]
    approved = conn.execute("SELECT COUNT(*) c FROM deposits WHERE status='approved'").fetchone()["c"]
    rejected = conn.execute("SELECT COUNT(*) c FROM deposits WHERE status='rejected'").fetchone()["c"]
    total = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE status='approved'").fetchone()["s"]
    rows = conn.execute(
        "SELECT d.*,u.first_name,u.username FROM deposits d LEFT JOIN users u ON u.user_id=d.user_id WHERE d.status='pending' ORDER BY d.id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    k = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        uname = f"@{row['username']}" if row["username"] else "NoUsername"
        k.add(types.InlineKeyboardButton(f"⏳ #{row['id']} • {row['user_id']} • {money(row['amount'])} • {uname}", callback_data=f"depview:{row['id']}"))
    k.add(types.InlineKeyboardButton("⚙️ UPI Setup", callback_data="a_upi_setup"))
    k.add(types.InlineKeyboardButton("📷 Set QR Image", callback_data="a_qr_setup"))
    k.add(types.InlineKeyboardButton("💵 Deposit Amounts", callback_data="a_deposit_amounts"))
    k.add(types.InlineKeyboardButton("📋 All Payment History", callback_data="a_payment_history"))
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    text = (
        "💰 <b>PAYMENT / UPI MANAGER</b>\n\n"
        f"⏳ Pending: <b>{pending}</b>\n"
        f"✅ Approved: <b>{approved}</b>\n"
        f"❌ Rejected: <b>{rejected}</b>\n"
        f"💵 Approved Total: <b>{money(total)}</b>\n\n"
        f"UPI ID: <code>{setting('upi_id') or 'NOT SET'}</code>\n"
        f"UPI Name: <b>{setting('upi_name') or 'NOT SET'}</b>\n"
        f"Custom QR: <b>{'SET' if setting('qr_file_id') else 'NOT SET'}</b>"
    )
    bot.send_message(chat_id, text, reply_markup=k)


def payment_history(chat_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM deposits ORDER BY id DESC LIMIT 40"
    ).fetchall()
    conn.close()
    if not rows:
        text = "📋 <b>PAYMENT HISTORY</b>\n\nNo payment records."
    else:
        text = "📋 <b>PAYMENT HISTORY</b>\n\n" + "\n\n".join(
            f"#{r['id']} • User <code>{r['user_id']}</code> • {money(r['amount'])}\n"
            f"UTR: <code>{r['utr']}</code> • <b>{r['status']}</b>\n{r['created_at']}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def dep_view(call, deposit_id):
    conn = db()
    row = conn.execute(
        "SELECT d.*,u.first_name,u.username,u.balance FROM deposits d LEFT JOIN users u ON u.user_id=d.user_id WHERE d.id=?",
        (deposit_id,),
    ).fetchone()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "Payment not found.")
        return
    username = f"@{row['username']}" if row["username"] else "No username"
    k = types.InlineKeyboardMarkup(row_width=2)
    if row["status"] == "pending":
        k.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"depapprove:{deposit_id}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"depreject:{deposit_id}"),
        )
    k.add(types.InlineKeyboardButton("🔙 Payments", callback_data="a_payments"))
    text = (
        f"💳 <b>PAYMENT #{deposit_id}</b>\n\n"
        f"User ID: <code>{row['user_id']}</code>\n"
        f"Name: <b>{row['first_name'] or 'Unknown'}</b>\n"
        f"Username: <b>{username}</b>\n"
        f"Amount: <b>{money(row['amount'])}</b>\n"
        f"UTR: <code>{row['utr']}</code>\n"
        f"Status: <b>{row['status'].upper()}</b>\n"
        f"Current Wallet: <b>{money(row['balance'] or 0)}</b>\n"
        f"Created: {row['created_at']}"
    )
    edit_message(call, text, k)


def approve_deposit(call, deposit_id):
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM deposits WHERE id=?", (deposit_id,)).fetchone()
        if not row:
            raise ValueError("Payment not found.")
        if row["status"] != "pending":
            raise ValueError("Payment has already been reviewed.")
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (row["user_id"],)).fetchone()
        if not user:
            raise ValueError("User not found.")
        new_balance = round(float(user["balance"]) + float(row["amount"]), 2)
        conn.execute("UPDATE users SET balance=?,updated_at=? WHERE user_id=?", (new_balance, now(), row["user_id"]))
        conn.execute("UPDATE deposits SET status='approved',reviewed_at=? WHERE id=?", (now(), deposit_id))
        conn.execute(
            """INSERT INTO wallet_ledger(user_id,amount,balance_after,entry_type,reference,note,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (row["user_id"], row["amount"], new_balance, "deposit", f"DEP-{deposit_id}", "UPI deposit approved", now()),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        bot.answer_callback_query(call.id, str(exc)[:180])
        return
    conn.close()
    audit("payment_approved", f"deposit={deposit_id}")
    safe_send(row["user_id"], f"✅ <b>PAYMENT APPROVED</b>\n\n{money(row['amount'])} has been added to your wallet.\nNew balance: <b>{money(new_balance)}</b>")
    bot.answer_callback_query(call.id, "Approved")
    edit_message(call, f"✅ Payment <b>#{deposit_id}</b> approved.\n\nCredited: <b>{money(row['amount'])}</b>\nNew wallet: <b>{money(new_balance)}</b>", back_admin())


def reject_deposit(call, deposit_id):
    conn = db()
    row = conn.execute("SELECT * FROM deposits WHERE id=?", (deposit_id,)).fetchone()
    if not row:
        conn.close()
        bot.answer_callback_query(call.id, "Payment not found.")
        return
    if row["status"] != "pending":
        conn.close()
        bot.answer_callback_query(call.id, "Already reviewed.")
        return
    conn.execute("UPDATE deposits SET status='rejected',reviewed_at=? WHERE id=?", (now(), deposit_id))
    conn.commit()
    conn.close()
    audit("payment_rejected", f"deposit={deposit_id}")
    safe_send(row["user_id"], f"❌ <b>PAYMENT REJECTED</b>\n\nRequest #{deposit_id}\nUTR: <code>{row['utr']}</code>\n\nPlease contact support if you believe this is incorrect.")
    bot.answer_callback_query(call.id, "Rejected")
    edit_message(call, f"❌ Payment <b>#{deposit_id}</b> rejected.", back_admin())


def a_orders(chat_id):
    conn = db()
    rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 40").fetchall()
    total = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status='completed'").fetchone()["s"]
    conn.close()
    text = "📦 <b>ORDER MANAGER</b>\n\n" f"Total displayed: <b>{len(rows)}</b>\nSales total: <b>{money(total)}</b>\n\n"
    if rows:
        text += "\n".join(
            f"#{r['id']} • User <code>{r['user_id']}</code> • {r['product_name']} • {money(r['amount'])} • {r['status']}"
            for r in rows
        )
    else:
        text += "No orders yet."
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_wallet(chat_id):
    bot.send_message(
        chat_id,
        "💳 <b>WALLET CONTROL</b>\n\n"
        "Use these commands for manual wallet adjustments:\n\n"
        "<code>/balance USER_ID AMOUNT</code>\n"
        "Positive amount = credit\n"
        "Negative amount = debit\n\n"
        "Every manual adjustment is recorded in the wallet ledger and audit log.",
        reply_markup=back_admin(),
    )


def a_coupons(chat_id):
    conn = db()
    rows = conn.execute("SELECT * FROM coupons ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    text = (
        "🎟️ <b>COUPON MANAGER</b>\n\n"
        "Create: <code>/addcoupon CODE | percent/fixed | VALUE | MAX_USES | EXPIRES</code>\n"
        "Example: <code>/addcoupon SAVE10 | percent | 10 | 100 | 2026-12-31</code>\n"
        "Use 0 for unlimited uses and blank expiry for no expiry.\n\n"
    )
    if rows:
        text += "\n".join(
            f"#{r['id']} • <code>{r['code']}</code> • {r['discount_type']} {r['discount_value']} • Uses {r['used_count']}/{r['max_uses'] or '∞'} • {'ON' if r['active'] else 'OFF'}"
            for r in rows
        )
    else:
        text += "No coupons yet."
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_broadcast(chat_id):
    bot.send_message(
        chat_id,
        "📢 <b>BROADCAST CENTER</b>\n\n"
        "Use:\n<code>/broadcast Your message</code>\n\n"
        "The message will be sent to saved users who have not been deleted from the bot.",
        reply_markup=back_admin(),
    )


def a_tickets(chat_id):
    conn = db()
    rows = conn.execute("SELECT * FROM tickets WHERE status='open' ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    if not rows:
        text = "🎫 <b>SUPPORT TICKETS</b>\n\nNo open tickets."
    else:
        text = "🎫 <b>OPEN TICKETS</b>\n\n" + "\n\n".join(
            f"#{r['id']} • User <code>{r['user_id']}</code>\n<b>{r['subject'] or 'No subject'}</b>\n{r['message'][:300]}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_referral(chat_id):
    conn = db()
    total_referrals = conn.execute("SELECT COUNT(*) c FROM users WHERE referred_by IS NOT NULL").fetchone()["c"]
    rewarded = conn.execute("SELECT COUNT(*) c FROM users WHERE referral_rewarded=1").fetchone()["c"]
    conn.close()
    bot.send_message(
        chat_id,
        "🎁 <b>REFERRAL CONTROL</b>\n\n"
        f"Enabled: <b>{'YES' if setting('referral_enabled') == '1' else 'NO'}</b>\n"
        f"Reward: <b>{money(setting('referral_reward','0'))}</b>\n"
        f"Total referred users: <b>{total_referrals}</b>\n"
        f"Rewards issued: <b>{rewarded}</b>\n\n"
        "Commands:\n"
        "<code>/setreferral AMOUNT</code>\n"
        "<code>/referral on</code>\n"
        "<code>/referral off</code>",
        reply_markup=back_admin(),
    )


def a_reports(chat_id):
    conn = db()
    sales = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status='completed'").fetchone()["s"]
    deposits = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE status='approved'").fetchone()["s"]
    pending = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE status='pending'").fetchone()["s"]
    avg_order = conn.execute("SELECT COALESCE(AVG(amount),0) a FROM orders WHERE status='completed'").fetchone()["a"]
    top = conn.execute("SELECT product_name,COUNT(*) c,SUM(amount) s FROM orders GROUP BY product_id,product_name ORDER BY c DESC LIMIT 10").fetchall()
    conn.close()
    text = (
        "📈 <b>STORE REPORTS</b>\n\n"
        f"💵 Completed sales: <b>{money(sales)}</b>\n"
        f"💳 Approved deposits: <b>{money(deposits)}</b>\n"
        f"⏳ Pending deposit value: <b>{money(pending)}</b>\n"
        f"🧮 Average order value: <b>{money(avg_order)}</b>\n\n"
        "🏆 <b>TOP PRODUCTS</b>\n"
    )
    text += "\n".join(f"{i}. {r['product_name']} • {r['c']} orders • {money(r['s'])}" for i, r in enumerate(top, 1)) if top else "No sales yet."
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_settings(chat_id):
    text = (
        "⚙️ <b>STORE SETTINGS</b>\n\n"
        f"Store Name: <b>{setting('store_name')}</b>\n"
        f"Tagline: <b>{setting('store_tagline')}</b>\n"
        f"Support: <b>{('@' + setting('support_username').lstrip('@')) if setting('support_username') else 'Not set'}</b>\n"
        f"Min Deposit: <b>{money(setting('min_deposit'))}</b>\n"
        f"Max Deposit: <b>{money(setting('max_deposit'))}</b>\n"
        f"Deposit Buttons: <b>{setting('deposit_amounts')}</b>\n"
        f"UPI ID: <code>{setting('upi_id') or 'NOT SET'}</code>\n"
        f"UPI Name: <b>{setting('upi_name') or 'NOT SET'}</b>\n"
        f"QR Image: <b>{'SET' if setting('qr_file_id') else 'NOT SET'}</b>\n"
        f"Referral Reward: <b>{money(setting('referral_reward','0'))}</b>\n"
        f"Maintenance: <b>{'ON' if setting('maintenance') == '1' else 'OFF'}</b>\n\n"
        "Commands:\n"
        "<code>/setstore NAME</code>\n"
        "<code>/settagline TEXT</code>\n"
        "<code>/setupi UPI_ID | ACCOUNT_NAME</code>\n"
        "<code>/setdeposit MIN | MAX | 100,200,500,1000</code>\n"
        "<code>/setsupport USERNAME | TEXT</code>\n"
        "<code>/sethowto TEXT</code>\n"
        "<code>/setwelcome TEXT</code>"
    )
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(types.InlineKeyboardButton("⚙️ UPI Setup", callback_data="a_upi_setup"), types.InlineKeyboardButton("📷 QR Setup", callback_data="a_qr_setup"))
    k.add(types.InlineKeyboardButton("💵 Deposit Buttons", callback_data="a_deposit_amounts"))
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    bot.send_message(chat_id, text, reply_markup=k)


def a_upi_setup(chat_id):
    bot.send_message(
        chat_id,
        "⚙️ <b>UPI SETUP</b>\n\n"
        "Send:\n<code>/setupi yourupi@bank | Account Name</code>\n\n"
        "The bot will NOT display or generate a QR until a UPI ID is actually saved.",
        reply_markup=back_admin(),
    )


def a_qr_setup(chat_id):
    msg = bot.send_message(
        chat_id,
        "📷 <b>SET CUSTOM UPI QR</b>\n\nSend the QR image as a photo now.\n\n"
        "If no custom QR is saved, the bot can generate a QR from the configured UPI ID.\n"
        "If neither is configured, it will show no QR instead of a random image."
    )
    bot.register_next_step_handler(msg, receive_qr_photo)


def receive_qr_photo(message):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        bot.send_message(message.chat.id, "❌ Please send the QR as a photo.", reply_markup=back_admin())
        return
    file_id = message.photo[-1].file_id
    set_setting("qr_file_id", file_id)
    audit("qr_updated", "Custom UPI QR image updated")
    bot.send_message(message.chat.id, "✅ Custom UPI QR saved successfully.", reply_markup=back_admin())


def a_deposit_amounts(chat_id):
    bot.send_message(
        chat_id,
        "💵 <b>DEPOSIT AMOUNT BUTTONS</b>\n\n"
        f"Current: <code>{setting('deposit_amounts')}</code>\n\n"
        "Set with:\n<code>/setdeposit MIN | MAX | 100,200,500,1000</code>\n\n"
        "Only amounts inside MIN/MAX are shown to users.",
        reply_markup=back_admin(),
    )


def a_maintenance(chat_id):
    status = setting("maintenance") == "1"
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🟢 Turn ON", callback_data="maint:1"),
        types.InlineKeyboardButton("🔴 Turn OFF", callback_data="maint:0"),
    )
    k.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_home"))
    bot.send_message(chat_id, f"🛠️ <b>MAINTENANCE</b>\n\nCurrent status: <b>{'ON' if status else 'OFF'}</b>", reply_markup=k)


def a_audit(chat_id):
    conn = db()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 40").fetchall()
    conn.close()
    if not rows:
        text = "📜 <b>AUDIT LOG</b>\n\nNo admin activity recorded yet."
    else:
        text = "📜 <b>AUDIT LOG</b>\n\n" + "\n\n".join(
            f"#{r['id']} • <b>{r['action']}</b>\n{r['details']}\n{r['created_at']}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def a_help(chat_id):
    text = (
        "❓ <b>ADMIN HELP</b>\n\n"
        "/admin — open admin panel\n"
        "/addproduct Name | Description | Price | Delivery | Stock\n"
        "/setupi UPI_ID | Account Name\n"
        "/setdeposit MIN | MAX | 100,200,500,1000\n"
        "/setstore NAME\n"
        "/settagline TEXT\n"
        "/setreferral AMOUNT\n"
        "/referral on/off\n"
        "/balance USER_ID AMOUNT\n"
        "/block USER_ID\n"
        "/unblock USER_ID\n"
        "/addcoupon CODE | percent/fixed | VALUE | MAX_USES | EXPIRES\n"
        "/broadcast MESSAGE\n"
        "/maintenance on/off\n\n"
        "UPI payments are manual-verification based. Never credit a wallet merely because a user claims payment was made."
    )
    bot.send_message(chat_id, text, reply_markup=back_admin())


# ----------------------------- Commands -----------------------------

@bot.message_handler(commands=["start"])
def start(message):
    referral_id = None
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referral_id = int(parts[1][4:])
        except ValueError:
            referral_id = None
    is_new = get_user(message.from_user.id) is None
    save_user(message.from_user, referral_id)
    if is_new:
        apply_referral_reward(message.from_user.id)
    if blocked(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Your account is blocked. Please contact support.")
        return
    if setting("maintenance") == "1" and not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🛠️ Store is under maintenance. Please try again later.")
        return
    show_home(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    save_user(message.from_user)
    if is_admin(message.from_user.id):
        admin_panel(message.chat.id)
    else:
        bot.send_message(message.chat.id, "⛔ Admin access denied.")


@bot.message_handler(commands=["addproduct"])
def add_product_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 5:
        bot.send_message(message.chat.id, "Usage:\n<code>/addproduct Name | Description | Price | Delivery | Stock</code>\nStock -1 = unlimited")
        return
    name, description, price_raw, delivery, stock_raw = parts
    try:
        price = float(price_raw)
        stock = int(stock_raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ Price must be positive and stock must be an integer.")
        return
    conn = db()
    conn.execute(
        "INSERT INTO products(name,description,price,delivery,stock,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (name, description, price, delivery, stock, 1, now(), now()),
    )
    conn.commit()
    product_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    conn.close()
    audit("product_added", f"product={product_id}")
    bot.send_message(message.chat.id, f"✅ Product <b>#{product_id}</b> added.", reply_markup=back_admin())


@bot.message_handler(commands=["setupi"])
def setupi_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in payload.split("|", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        bot.send_message(message.chat.id, "Usage:\n<code>/setupi UPI_ID | Account Name</code>")
        return
    upi_id, name = parts
    if " " in upi_id or "@" not in upi_id:
        bot.send_message(message.chat.id, "❌ Please provide a valid-looking UPI ID such as name@bank.")
        return
    set_setting("upi_id", upi_id)
    set_setting("upi_name", name)
    audit("upi_updated", f"upi={upi_id}")
    bot.send_message(message.chat.id, "✅ UPI ID and account name saved.\n\nNo QR will be shown unless a valid UPI ID is configured or a custom QR is uploaded.", reply_markup=back_admin())


@bot.message_handler(commands=["setdeposit"])
def setdeposit_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 3:
        bot.send_message(message.chat.id, "Usage:\n<code>/setdeposit MIN | MAX | 100,200,500,1000</code>")
        return
    try:
        minimum = float(parts[0])
        maximum = float(parts[1])
        amounts = []
        for raw in parts[2].split(","):
            value = float(raw.strip())
            if minimum <= value <= maximum:
                amounts.append(value)
        if minimum <= 0 or maximum < minimum or not amounts:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid deposit settings.")
        return
    set_setting("min_deposit", minimum)
    set_setting("max_deposit", maximum)
    set_setting("deposit_amounts", ",".join(f"{x:g}" for x in amounts))
    audit("deposit_settings_updated", f"min={minimum},max={maximum},amounts={amounts}")
    bot.send_message(message.chat.id, "✅ Deposit settings updated.", reply_markup=back_admin())


@bot.message_handler(commands=["setstore"])
def setstore_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip()
    if not value:
        bot.send_message(message.chat.id, "Usage: <code>/setstore 𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆</code>")
        return
    set_setting("store_name", value[:80])
    audit("store_name_updated", value[:80])
    bot.send_message(message.chat.id, "✅ Store name updated.", reply_markup=back_admin())


@bot.message_handler(commands=["settagline"])
def settagline_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip()
    if not value:
        bot.send_message(message.chat.id, "Usage: <code>/settagline Premium Digital Store</code>")
        return
    set_setting("store_tagline", value[:120])
    audit("tagline_updated", value[:120])
    bot.send_message(message.chat.id, "✅ Tagline updated.", reply_markup=back_admin())


@bot.message_handler(commands=["setsupport"])
def setsupport_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in payload.split("|", 1)]
    if len(parts) != 2:
        bot.send_message(message.chat.id, "Usage: <code>/setsupport username | Support text</code>")
        return
    set_setting("support_username", parts[0].lstrip("@"))
    set_setting("support_text", parts[1])
    audit("support_updated", parts[0])
    bot.send_message(message.chat.id, "✅ Support settings updated.", reply_markup=back_admin())


@bot.message_handler(commands=["sethowto"])
def sethowto_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip()
    if value:
        set_setting("howto_text", value[:3000])
    bot.send_message(message.chat.id, "✅ How-To content updated.", reply_markup=back_admin())


@bot.message_handler(commands=["setwelcome"])
def setwelcome_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip()
    if value:
        set_setting("welcome_text", value[:500])
    bot.send_message(message.chat.id, "✅ Welcome text updated.", reply_markup=back_admin())


@bot.message_handler(commands=["setreferral"])
def setreferral_cmd(message):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.partition(" ")[2].strip()
    try:
        value = float(raw)
        if value < 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "Usage: <code>/setreferral 10</code>")
        return
    set_setting("referral_reward", value)
    audit("referral_reward_updated", str(value))
    bot.send_message(message.chat.id, f"✅ Referral reward set to {money(value)}.", reply_markup=back_admin())


@bot.message_handler(commands=["referral"])
def referral_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip().lower()
    if value not in ("on", "off"):
        bot.send_message(message.chat.id, "Usage: <code>/referral on</code> or <code>/referral off</code>")
        return
    set_setting("referral_enabled", "1" if value == "on" else "0")
    audit("referral_toggled", value)
    bot.send_message(message.chat.id, f"✅ Referral system {value}.", reply_markup=back_admin())


@bot.message_handler(commands=["maintenance"])
def maintenance_cmd(message):
    if not is_admin(message.from_user.id):
        return
    value = message.text.partition(" ")[2].strip().lower()
    if value not in ("on", "off"):
        bot.send_message(message.chat.id, "Usage: <code>/maintenance on</code> or <code>/maintenance off</code>")
        return
    set_setting("maintenance", "1" if value == "on" else "0")
    audit("maintenance_toggled", value)
    bot.send_message(message.chat.id, f"🛠️ Maintenance {value}.", reply_markup=back_admin())


@bot.message_handler(commands=["block", "unblock"])
def block_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "Usage: <code>/block USER_ID</code> or <code>/unblock USER_ID</code>")
        return
    user_id = int(parts[1])
    blocked_value = 1 if message.text.startswith("/block") else 0
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        bot.send_message(message.chat.id, "❌ User not found.")
        return
    conn.execute("UPDATE users SET blocked=?,updated_at=? WHERE user_id=?", (blocked_value, now(), user_id))
    conn.commit()
    conn.close()
    audit("user_blocked" if blocked_value else "user_unblocked", f"user={user_id}")
    bot.send_message(message.chat.id, f"✅ User <code>{user_id}</code> {'blocked' if blocked_value else 'unblocked'}.", reply_markup=back_admin())


@bot.message_handler(commands=["balance"])
def balance_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "Usage: <code>/balance USER_ID AMOUNT</code>\nExample: <code>/balance 123456789 50</code>\nDebit: <code>/balance 123456789 -50</code>")
        return
    user_id = int(parts[1])
    try:
        amount = float(parts[2])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount.")
        return
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found.")
        new_balance = round(float(user["balance"]) + amount, 2)
        if new_balance < 0:
            raise ValueError("Balance cannot become negative.")
        conn.execute("UPDATE users SET balance=?,updated_at=? WHERE user_id=?", (new_balance, now(), user_id))
        conn.execute(
            "INSERT INTO wallet_ledger(user_id,amount,balance_after,entry_type,reference,note,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, amount, new_balance, "admin_adjustment", f"ADMIN-{ADMIN_ID}", "Manual admin wallet adjustment", now()),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        bot.send_message(message.chat.id, f"❌ {exc}")
        return
    conn.close()
    audit("wallet_adjusted", f"user={user_id},amount={amount}")
    safe_send(user_id, f"💳 Wallet updated by admin.\nChange: <b>{money(amount)}</b>\nNew balance: <b>{money(new_balance)}</b>")
    bot.send_message(message.chat.id, f"✅ Wallet updated.\nUser: <code>{user_id}</code>\nChange: <b>{money(amount)}</b>\nNew balance: <b>{money(new_balance)}</b>", reply_markup=back_admin())


@bot.message_handler(commands=["addcoupon"])
def addcoupon_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 5:
        bot.send_message(message.chat.id, "Usage: <code>/addcoupon CODE | percent/fixed | VALUE | MAX_USES | EXPIRES</code>")
        return
    code, discount_type, value_raw, max_raw, expires = parts
    discount_type = discount_type.lower()
    if discount_type not in ("percent", "fixed"):
        bot.send_message(message.chat.id, "❌ Discount type must be percent or fixed.")
        return
    try:
        value = float(value_raw)
        max_uses = int(max_raw)
        if value <= 0 or max_uses < 0 or (discount_type == "percent" and value > 100):
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid coupon values.")
        return
    conn = db()
    try:
        conn.execute(
            "INSERT INTO coupons(code,discount_type,discount_value,max_uses,expires_at,created_at) VALUES(?,?,?,?,?,?)",
            (code.upper(), discount_type, value, max_uses, expires, now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        bot.send_message(message.chat.id, "❌ Coupon code already exists.")
        return
    conn.close()
    audit("coupon_added", code.upper())
    bot.send_message(message.chat.id, f"✅ Coupon <code>{code.upper()}</code> created.", reply_markup=back_admin())


@bot.message_handler(commands=["broadcast"])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        return
    payload = message.text.partition(" ")[2].strip()
    if not payload:
        bot.send_message(message.chat.id, "Usage: <code>/broadcast Your message</code>")
        return
    conn = db()
    rows = conn.execute("SELECT user_id FROM users WHERE blocked=0").fetchall()
    conn.close()
    sent = 0
    failed = 0
    for row in rows:
        if safe_send(row["user_id"], payload):
            sent += 1
        else:
            failed += 1
    audit("broadcast", f"sent={sent},failed={failed}")
    bot.send_message(message.chat.id, f"📢 Broadcast complete.\n\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>", reply_markup=back_admin())


@bot.message_handler(commands=["user"])
def user_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "Usage: <code>/user USER_ID</code>")
        return
    user_id = int(parts[1])
    row = get_user(user_id)
    if not row:
        bot.send_message(message.chat.id, "❌ User not found.")
        return
    username = f"@{row['username']}" if row["username"] else "No username"
    bot.send_message(message.chat.id, f"👤 <b>USER</b>\n\nID: <code>{user_id}</code>\nName: <b>{row['first_name']}</b>\nUsername: <b>{username}</b>\nBalance: <b>{money(row['balance'])}</b>\nStatus: <b>{'BLOCKED' if row['blocked'] else 'ACTIVE'}</b>", reply_markup=back_admin())


@bot.message_handler(commands=["help"])
def help_cmd(message):
    if is_admin(message.from_user.id):
        a_help(message.chat.id)
    else:
        bot.send_message(message.chat.id, f"📖 <b>HELP</b>\n\n{setting('howto_text')}", reply_markup=back_home())


# ----------------------------- Callback Router -----------------------------

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    try:
        save_user(call.from_user)
        data = call.data or ""

        if blocked(call.from_user.id) and not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Your account is blocked.")
            return

        if data == "home":
            edit_message(call, f"🤖 <b>{setting('store_name')}</b>\n\nChoose an option:", user_menu(call.from_user.id))
        elif data == "shop":
            bot.answer_callback_query(call.id)
            show_shop(call.message.chat.id)
        elif data.startswith("product:"):
            show_product(call, int(data.split(":")[1]))
        elif data.startswith("buy:"):
            buy_product(call, int(data.split(":")[1]))
        elif data == "wallet":
            wallet(call.message.chat.id, call.from_user.id)
        elif data == "deposit":
            show_deposit(call.message.chat.id, call.from_user.id)
        elif data.startswith("depamt:"):
            amount = float(data.split(":")[1])
            send_payment_request(call.message.chat.id, call.from_user.id, amount)
            bot.answer_callback_query(call.id)
        elif data.startswith("utr:"):
            amount = float(data.split(":")[1])
            msg = bot.send_message(call.message.chat.id, f"🧾 <b>SUBMIT UTR</b>\n\nAmount: <b>{money(amount)}</b>\n\nSend the exact UTR/reference number:")
            bot.register_next_step_handler(msg, receive_utr, amount)
            bot.answer_callback_query(call.id)
        elif data == "transactions":
            transactions(call.message.chat.id, call.from_user.id)
        elif data == "orders":
            orders(call.message.chat.id, call.from_user.id)
        elif data == "profile":
            profile(call.message.chat.id, call.from_user.id)
        elif data == "referral":
            referral(call.message.chat.id, call.from_user.id)
        elif data == "coupon":
            msg = bot.send_message(call.message.chat.id, "🎟️ Enter coupon code:")
            bot.register_next_step_handler(msg, receive_coupon)
        elif data == "support":
            support_text = setting("support_text")
            if setting("support_username"):
                support_text += f"\n\nContact: @{setting('support_username').lstrip('@')}"
            edit_message(call, f"🎫 <b>SUPPORT</b>\n\n{support_text}", back_home())
        elif data == "howto":
            edit_message(call, f"📖 <b>HOW TO USE</b>\n\n{setting('howto_text')}", back_home())

        # Admin routing
        elif data == "admin_home" and is_admin(call.from_user.id):
            edit_message(call, "🔐 <b>ADMIN CONTROL CENTER</b>\n\nChoose a section:", admin_menu())
        elif data == "a_dashboard" and is_admin(call.from_user.id):
            a_dashboard(call.message.chat.id)
        elif data == "a_users" and is_admin(call.from_user.id):
            a_users(call.message.chat.id, 0)
        elif data.startswith("ausers:") and is_admin(call.from_user.id):
            a_users(call.message.chat.id, int(data.split(":")[1]))
        elif data.startswith("auser:") and is_admin(call.from_user.id):
            _, uid, page = data.split(":")
            fake_call = call
            a_user_detail(fake_call, int(uid), int(page))
        elif data == "auser_ids" and is_admin(call.from_user.id):
            a_user_ids(call.message.chat.id)
        elif data == "asearch_user" and is_admin(call.from_user.id):
            a_search_user(call.message.chat.id)
        elif data == "a_products" and is_admin(call.from_user.id):
            a_products(call.message.chat.id)
        elif data == "addproduct" and is_admin(call.from_user.id):
            bot.send_message(call.message.chat.id, "Use:\n<code>/addproduct Name | Description | Price | Delivery | Stock</code>\nStock -1 = unlimited", reply_markup=back_admin())
        elif data.startswith("aprod:") and is_admin(call.from_user.id):
            a_product_detail(call, int(data.split(":")[1]))
        elif data.startswith("ptoggle:") and is_admin(call.from_user.id):
            _, pid, value = data.split(":")
            conn = db()
            conn.execute("UPDATE products SET active=?,updated_at=? WHERE id=?", (int(value), now(), int(pid)))
            conn.commit()
            conn.close()
            audit("product_status", f"product={pid},active={value}")
            bot.answer_callback_query(call.id, "Product status updated")
            a_products(call.message.chat.id)
        elif data.startswith("pdelete:") and is_admin(call.from_user.id):
            pid = int(data.split(":")[1])
            conn = db()
            conn.execute("DELETE FROM products WHERE id=?", (pid,))
            conn.commit()
            conn.close()
            audit("product_deleted", f"product={pid}")
            bot.answer_callback_query(call.id, "Deleted")
            a_products(call.message.chat.id)
        elif data == "a_payments" and is_admin(call.from_user.id):
            a_payments(call.message.chat.id)
        elif data == "a_upi_setup" and is_admin(call.from_user.id):
            a_upi_setup(call.message.chat.id)
        elif data == "a_qr_setup" and is_admin(call.from_user.id):
            a_qr_setup(call.message.chat.id)
        elif data == "a_deposit_amounts" and is_admin(call.from_user.id):
            a_deposit_amounts(call.message.chat.id)
        elif data == "a_payment_history" and is_admin(call.from_user.id):
            payment_history(call.message.chat.id)
        elif data.startswith("depview:") and is_admin(call.from_user.id):
            dep_view(call, int(data.split(":")[1]))
        elif data.startswith("depapprove:") and is_admin(call.from_user.id):
            approve_deposit(call, int(data.split(":")[1]))
        elif data.startswith("depreject:") and is_admin(call.from_user.id):
            reject_deposit(call, int(data.split(":")[1]))
        elif data == "a_orders" and is_admin(call.from_user.id):
            a_orders(call.message.chat.id)
        elif data == "a_wallet" and is_admin(call.from_user.id):
            a_wallet(call.message.chat.id)
        elif data == "a_coupons" and is_admin(call.from_user.id):
            a_coupons(call.message.chat.id)
        elif data == "a_broadcast" and is_admin(call.from_user.id):
            a_broadcast(call.message.chat.id)
        elif data == "a_tickets" and is_admin(call.from_user.id):
            a_tickets(call.message.chat.id)
        elif data == "a_referral" and is_admin(call.from_user.id):
            a_referral(call.message.chat.id)
        elif data == "a_reports" and is_admin(call.from_user.id):
            a_reports(call.message.chat.id)
        elif data == "a_settings" and is_admin(call.from_user.id):
            a_settings(call.message.chat.id)
        elif data == "a_maintenance" and is_admin(call.from_user.id):
            a_maintenance(call.message.chat.id)
        elif data.startswith("maint:") and is_admin(call.from_user.id):
            value = data.split(":")[1]
            set_setting("maintenance", value)
            audit("maintenance_toggled", value)
            bot.answer_callback_query(call.id, "Updated")
            a_maintenance(call.message.chat.id)
        elif data == "a_audit" and is_admin(call.from_user.id):
            a_audit(call.message.chat.id)
        elif data == "a_help" and is_admin(call.from_user.id):
            a_help(call.message.chat.id)
        elif data.startswith("block:") and is_admin(call.from_user.id):
            uid = int(data.split(":")[1])
            if uid == ADMIN_ID:
                bot.answer_callback_query(call.id, "You cannot block the owner.")
                return
            conn = db()
            conn.execute("UPDATE users SET blocked=1,updated_at=? WHERE user_id=?", (now(), uid))
            conn.commit()
            conn.close()
            audit("user_blocked", f"user={uid}")
            bot.answer_callback_query(call.id, "Blocked")
            safe_send(uid, "🚫 Your account has been blocked by the store administrator.")
            a_user_detail(call, uid, 0)
        elif data.startswith("unblock:") and is_admin(call.from_user.id):
            uid = int(data.split(":")[1])
            conn = db()
            row = conn.execute("SELECT blocked FROM users WHERE user_id=?", (uid,)).fetchone()
            if not row:
                conn.close()
                bot.answer_callback_query(call.id, "User not found.")
                return
            if not row["blocked"]:
                conn.close()
                bot.answer_callback_query(call.id, "User is already unblocked.")
                return
            conn.execute("UPDATE users SET blocked=0,updated_at=? WHERE user_id=?", (now(), uid))
            conn.commit()
            conn.close()
            audit("user_unblocked", f"user={uid}")
            bot.answer_callback_query(call.id, "Unblocked")
            safe_send(uid, "🟢 Your account has been unblocked.")
            a_user_detail(call, uid, 0)
        elif data.startswith("adjbal:") and is_admin(call.from_user.id):
            uid = int(data.split(":")[1])
            msg = bot.send_message(call.message.chat.id, f"💰 Send wallet change for User <code>{uid}</code>.\nExample: <code>+100</code> or <code>-50</code>")
            bot.register_next_step_handler(msg, process_balance_adjustment, uid)
        elif data.startswith("uorders:") and is_admin(call.from_user.id):
            uid = int(data.split(":")[1])
            admin_user_orders(call.message.chat.id, uid)
        elif data.startswith("udep:") and is_admin(call.from_user.id):
            uid = int(data.split(":")[1])
            admin_user_deposits(call.message.chat.id, uid)
        else:
            bot.answer_callback_query(call.id, "Option unavailable.")
    except Exception as exc:
        logging.exception("Callback error")
        try:
            bot.answer_callback_query(call.id, "Something went wrong. Try again.")
        except Exception:
            pass


def process_balance_adjustment(message, user_id):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = float((message.text or "").strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount.", reply_markup=back_admin())
        return
    # Reuse the same safe ledger logic as /balance.
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found.")
        new_balance = round(float(user["balance"]) + amount, 2)
        if new_balance < 0:
            raise ValueError("Balance cannot become negative.")
        conn.execute("UPDATE users SET balance=?,updated_at=? WHERE user_id=?", (new_balance, now(), user_id))
        conn.execute(
            "INSERT INTO wallet_ledger(user_id,amount,balance_after,entry_type,reference,note,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, amount, new_balance, "admin_adjustment", f"ADMIN-{ADMIN_ID}", "Manual adjustment", now()),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        bot.send_message(message.chat.id, f"❌ {exc}", reply_markup=back_admin())
        return
    conn.close()
    audit("wallet_adjusted", f"user={user_id},amount={amount}")
    safe_send(user_id, f"💳 Wallet changed by admin.\nChange: <b>{money(amount)}</b>\nNew balance: <b>{money(new_balance)}</b>")
    bot.send_message(message.chat.id, f"✅ Wallet updated. New balance: <b>{money(new_balance)}</b>", reply_markup=back_admin())


def admin_user_orders(chat_id, user_id):
    conn = db()
    rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 30", (user_id,)).fetchall()
    conn.close()
    if not rows:
        text = f"📦 <b>USER ORDERS</b>\n\nUser <code>{user_id}</code> has no orders."
    else:
        text = f"📦 <b>USER ORDERS</b>\n\nUser: <code>{user_id}</code>\n\n" + "\n\n".join(
            f"#{r['id']} • {r['product_name']} • {money(r['amount'])}\n{r['status']} • {r['created_at']}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def admin_user_deposits(chat_id, user_id):
    conn = db()
    rows = conn.execute("SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 30", (user_id,)).fetchall()
    conn.close()
    if not rows:
        text = f"💳 <b>USER PAYMENTS</b>\n\nUser <code>{user_id}</code> has no payments."
    else:
        text = f"💳 <b>USER PAYMENTS</b>\n\nUser: <code>{user_id}</code>\n\n" + "\n\n".join(
            f"#{r['id']} • {money(r['amount'])} • <b>{r['status']}</b>\nUTR: <code>{r['utr']}</code>\n{r['created_at']}"
            for r in rows
        )
    bot.send_message(chat_id, text, reply_markup=back_admin())


def receive_coupon(message):
    code = (message.text or "").strip().upper()
    if not code:
        bot.send_message(message.chat.id, "❌ Invalid coupon code.", reply_markup=back_home())
        return
    conn = db()
    row = conn.execute("SELECT * FROM coupons WHERE code=? AND active=1", (code,)).fetchone()
    if not row:
        conn.close()
        bot.send_message(message.chat.id, "❌ Coupon not found or inactive.", reply_markup=back_home())
        return
    if row["max_uses"] and row["used_count"] >= row["max_uses"]:
        conn.close()
        bot.send_message(message.chat.id, "❌ Coupon usage limit reached.", reply_markup=back_home())
        return
    if row["expires_at"]:
        try:
            expiry = datetime.strptime(row["expires_at"], "%Y-%m-%d")
            if datetime.now() > expiry:
                conn.close()
                bot.send_message(message.chat.id, "❌ Coupon has expired.", reply_markup=back_home())
                return
        except ValueError:
            pass
    used = conn.execute("SELECT id FROM coupon_uses WHERE coupon_id=? AND user_id=?", (row["id"], message.from_user.id)).fetchone()
    if used:
        conn.close()
        bot.send_message(message.chat.id, "❌ You have already used this coupon.", reply_markup=back_home())
        return
    conn.execute("INSERT INTO coupon_uses(coupon_id,user_id,used_at) VALUES(?,?,?)", (row["id"], message.from_user.id, now()))
    conn.execute("UPDATE coupons SET used_count=used_count+1 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()
    # Coupon is recorded for future checkout use; no fake wallet credit is issued.
    discount = f"{row['discount_value']}%" if row["discount_type"] == "percent" else money(row["discount_value"])
    bot.send_message(message.chat.id, f"✅ Coupon <code>{code}</code> applied for your next eligible purchase.\nDiscount: <b>{discount}</b>", reply_markup=back_home())


# ----------------------------- Startup -----------------------------

init_db()

if __name__ == "__main__":
    logging.info("𝑴𝒖𝒔𝒌𝒂𝒏 𝑷𝒂𝒏𝒆𝒍 𝑺𝒕𝒐𝒓𝒆 is starting...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

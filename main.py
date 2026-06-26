import asyncio
import csv
import html
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Set
from unicodedata import normalize

import aiohttp
from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    User,
    WebAppInfo,
)
from dotenv import load_dotenv


PROJECT_PRICES = {
    "telegram_bot_simple": ("Oddiy biznes / menyu Telegram bot", 150),
    "telegram_twa": ("Telegram Web App (TWA) bot", 300),
    "telegram_order_bot": ("Kurer / buyurtma Telegram bot", 400),
    "website_landing": ("Landing Page", 200),
    "website_corporate": ("Korporativ sayt", 400),
    "website_store": ("Online do'kon / murakkab veb tizim", 600),
    "mobile_app": ("Mobil ilova", 800),
    "crm_system": ("CRM tizimi", 350),
    "accounting_system": ("Hisob-kitob / statistika tizimi", 400),
}

PROJECT_ALIASES = {
    "telegram_bot": "telegram_bot_simple",
    "website": "website_landing",
}

SERVICE_PRICE_TEXT = """ZettaCode Tech - Xizmatlarimiz Narxlari

Biznesingizni raqamlashtirish va avtomatlashtirish qancha turadi? Har bir loyiha uning murakkabligi va talablaridan kelib chiqib individual baholanadi. Boshlang'ich narxlar:

1. Kuchli va aqlli Telegram botlar
- Oddiy biznes va menyu botlar: 150$ dan boshlab
- Telegram Web Apps (TWA) botlar: 300$ dan boshlab
- Avtomatlashtirilgan kurer/buyurtma botlari: 400$ dan boshlab

2. Veb-saytlar yaratish
- Landing Page: 200$ dan boshlab
- Korporativ saytlar: 400$ dan boshlab
- Onlayn do'konlar / murakkab tizimlar: 600$ dan boshlab

3. Zamonaviy mobil ilovalar
- Startaplar va xizmat ko'rsatish ilovalari: 800$ dan boshlab

4. CRM va hisob-kitob tizimlari
- Mijozlar bazasini yuritish (CRM): 350$ dan boshlab
- Hisob-kitob va statistika tizimlari: 400$ dan boshlab

To'lov turi va shartlari:
ZettaCode Tech xizmatlari uchun predoplata plastik karta orqali qabul qilinadi. Loyiha boshlanishidan oldin kelishilgan summaning 50% qismi predoplata sifatida qabul qilinadi.
Mijoz buyurtma qilayotgan loyiha ichidagi to'lov funksiyasi esa faqat naqd to'lov sifatida ko'rib chiqiladi. Click, Payme, Paynet yoki boshqa online to'lov integratsiyalari loyiha funksiyasi sifatida taklif qilinmaydi.

Nega aynan biz?
- Narx ichiga nafaqat kod yozish, balki to'g'ri strategiya va tizimni to'liq sozlash kiradi.
- Loyiha topshirilgandan keyin ham ma'lum muddat texnik qo'llab-quvvatlash bepul.

Aloqa:
Telegram: @toshmirzayevinomjon
Nomer: +998-95-184-07-51
Kanal: @zettacodetech
Portfolio: https://toshmirzayev-inomjon.online/"""

STATUS_LABELS = {
    "payment_confirmation": "To'lov roziligi kutilmoqda",
    "awaiting_receipt": "Chek kutilmoqda",
    "checking": "Admin tekshiryapti",
    "admin_contact": "Admin bilan kelishish kerak",
    "paid": "To'lov qabul qilindi",
    "rejected": "To'lov tasdiqlanmadi",
}

PIPELINE_STAGES = {
    "new": "Yangi",
    "requirements": "Talab olinmoqda",
    "priced": "Narx berildi",
    "prepayment": "Predoplata",
    "in_progress": "Ish boshlandi",
    "done": "Tugatildi",
}

COMPLEXITY_RULES = [
    (("admin", "panel", "dashboard"), 150),
    (("tolov", "payment", "naqd", "naxd", "cash"), 75),
    (("login", "registratsiya", "ro'yxat", "profil", "kabinet"), 100),
    (("savatcha", "katalog", "mahsulot"), 150),
    (("ai", "sun'iy", "chatgpt", "openai", "aqlli"), 200),
    (("xarita", "gps", "lokatsiya", "geolokatsiya"), 150),
    (("api", "integratsiya", "baza", "database", "hisobot"), 100),
    (("sms", "email", "bildirishnoma", "notification"), 75),
    (("rasm", "video", "fayl", "upload"), 75),
    (("dizayn", "figma", "animatsiya"), 100),
]

BUSINESS_KEYWORDS = (
    "loyiha",
    "buyurtma",
    "narx",
    "qancha",
    "qilish",
    "kerak",
    "admin",
    "panel",
    "tolov",
    "naqd",
    "naxd",
    "cash",
    "dostavka",
    "magazin",
    "crm",
    "ai",
    "sun'iy",
    "integratsiya",
    "api",
    "baza",
    "login",
    "registratsiya",
    "twa",
    "web app",
    "kurer",
    "online do'kon",
    "hisob-kitob",
    "statistika",
    "portfolio",
    "kanal",
)

TWA_KEYWORDS = ("twa", "telegram web app", "web app", "webapp")
ORDER_BOT_KEYWORDS = ("kurer", "courier", "yetkazib", "dostavka", "buyurtma")
TELEGRAM_KEYWORDS = ("telegram", "bot", "tg", "kanal", "guruh", "avtojavob", "webhook")
STORE_KEYWORDS = ("online do'kon", "online dokon", "internet magazin", "ecommerce", "e-commerce", "marketplace")
CORPORATE_SITE_KEYWORDS = ("korporativ", "kompaniya", "biznes sayt", "company")
LANDING_KEYWORDS = ("landing", "lend", "bir sahifali", "sayt", "veb", "portfolio")
MOBILE_KEYWORDS = ("mobil", "ilova", "android", "ios", "mobile app", "telefon", "play market", "app store")
ACCOUNTING_KEYWORDS = ("hisob", "hisob-kitob", "statistika", "hisobot", "kassa", "moliya")
CRM_KEYWORDS = ("crm", "mijozlar bazasi", "mijozlar", "ombor", "dashboard")
ONLINE_PAYMENT_KEYWORDS = (
    "click",
    "payme",
    "paynet",
    "uzum",
    "apelsin",
    "karta",
    "card",
    "online tolov",
    "online to'lov",
    "onlayn tolov",
    "onlayn to'lov",
)

MAIN_MENU_TEXT = "Asosiy menyu"
START_ORDER_TEXT = "Buyurtma berish"
PRICE_TEXT = "Narxlar"
ADMIN_PANEL_TEXT = "Admin panel"
CANCEL_TEXT = "Bekor qilish"
CALCULATE_TEXT = "Narxni hisoblash"
RATE_LIMIT_WINDOW_SECONDS = 8
RATE_LIMIT_MAX_MESSAGES = 8
DEFAULT_REMINDER_AFTER_HOURS = 24
WEB_ADMIN_DEFAULT_PORT = 8088
WEBAPP_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "index.html")
PROMO_CODES = {
    "ZETTA10": 10,
    "START5": 5,
}


@dataclass
class EstimateResult:
    estimate: int
    summary: str
    features: list[str]
    ai_used: bool = False


@dataclass
class ConversationResult:
    relevant: bool
    reply: str
    suggested_projects: list[str] = field(default_factory=list)
    captured_requirements: str = ""
    should_estimate: bool = False
    enough_details: bool = False
    missing_questions: list[str] = field(default_factory=list)
    ai_used: bool = False


@dataclass
class RequirementValidation:
    enough: bool
    reply: str
    missing_questions: list[str] = field(default_factory=list)
    ai_used: bool = False


@dataclass
class UserSession:
    stage: str = "choose_project"
    selected_projects: Set[str] = field(default_factory=set)
    requirements: str = ""
    estimate: int = 0
    prepayment: int = 0
    order_id: int | None = None
    ai_summary: str = ""
    ai_features: list[str] = field(default_factory=list)
    ai_used: bool = False
    estimated_duration: str = ""
    lead_score: str = ""
    is_admin_test: bool = False
    asked_questions: int = 0
    off_topic_count: int = 0
    requirements_validated: bool = False
    pending_note_order_id: int | None = None
    pending_search_query: str = ""
    pending_broadcast_text: str = ""
    pending_task_order_id: int | None = None
    promo_code: str = ""
    promo_discount_percent: int = 0


sessions: Dict[int, UserSession] = {}
rate_limits: Dict[int, list[float]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> str:
    return os.getenv("DB_PATH", "orders.db")


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(db_path())
    connection.row_factory = sqlite3.Row
    return connection


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with db_connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT,
                projects TEXT NOT NULL,
                requirements TEXT NOT NULL,
                estimate INTEGER NOT NULL,
                prepayment INTEGER NOT NULL,
                ai_summary TEXT NOT NULL DEFAULT '',
                ai_features TEXT NOT NULL DEFAULT '[]',
                ai_used INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                receipt_file_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_column(connection, "orders", "pipeline_stage", "TEXT NOT NULL DEFAULT 'new'")
        ensure_column(connection, "orders", "deadline", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "orders", "assignee", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "orders", "reminded_at", "TEXT")
        ensure_column(connection, "orders", "lead_score", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "orders", "estimated_duration", "TEXT NOT NULL DEFAULT ''")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                assignee TEXT NOT NULL DEFAULT '',
                deadline TEXT NOT NULL DEFAULT '',
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def track_user(user: User) -> None:
    now = utc_now()
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, full_name, username, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                username = excluded.username,
                last_seen = excluded.last_seen
            """,
            (user.id, user.full_name, user.username or "", now, now),
        )


def create_order(user: User, session: UserSession) -> int:
    username = user.username or ""
    now = utc_now()
    with db_connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO orders (
                user_id, full_name, username, projects, requirements, estimate, prepayment,
                ai_summary, ai_features, ai_used, status, pipeline_stage, lead_score,
                estimated_duration, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                user.full_name,
                username,
                ",".join(ordered_project_keys(session.selected_projects)),
                session.requirements,
                session.estimate,
                session.prepayment,
                session.ai_summary,
                json.dumps(session.ai_features, ensure_ascii=False),
                1 if session.ai_used else 0,
                "payment_confirmation",
                "priced",
                session.lead_score,
                session.estimated_duration,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def update_order_status(
    order_id: int | None,
    status: str,
    receipt_file_id: str | None = None,
) -> None:
    if order_id is None:
        return

    fields = ["status = ?", "updated_at = ?"]
    values: list[Any] = [status, utc_now()]
    if receipt_file_id is not None:
        fields.append("receipt_file_id = ?")
        values.append(receipt_file_id)
    values.append(order_id)

    with db_connect() as connection:
        connection.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def update_order_price(order_id: int | None, estimate: int, prepayment: int) -> None:
    if order_id is None:
        return
    with db_connect() as connection:
        connection.execute(
            "UPDATE orders SET estimate = ?, prepayment = ?, updated_at = ? WHERE id = ?",
            (estimate, prepayment, utc_now(), order_id),
        )


def update_order_metadata(
    order_id: int | None,
    *,
    pipeline_stage: str | None = None,
    deadline: str | None = None,
    assignee: str | None = None,
    lead_score: str | None = None,
    estimated_duration: str | None = None,
    reminded_at: str | None = None,
) -> None:
    if order_id is None:
        return

    fields = ["updated_at = ?"]
    values: list[Any] = [utc_now()]
    updates = {
        "pipeline_stage": pipeline_stage,
        "deadline": deadline,
        "assignee": assignee,
        "lead_score": lead_score,
        "estimated_duration": estimated_duration,
        "reminded_at": reminded_at,
    }
    for column, value in updates.items():
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)
    values.append(order_id)

    with db_connect() as connection:
        connection.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def get_order(order_id: int) -> sqlite3.Row | None:
    with db_connect() as connection:
        return connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def latest_orders(limit: int = 8) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )


def latest_orders_by_status(status: str, limit: int = 8) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        )


def latest_orders_by_pipeline(stage: str, limit: int = 8) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM orders WHERE pipeline_stage = ? ORDER BY id DESC LIMIT ?",
                (stage, limit),
            ).fetchall()
        )


def search_orders(query: str, limit: int = 10) -> list[sqlite3.Row]:
    clean_query = query.strip().lstrip("@")
    if not clean_query:
        return []

    with db_connect() as connection:
        if clean_query.isdigit():
            return list(
                connection.execute(
                    """
                    SELECT * FROM orders
                    WHERE id = ? OR user_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (int(clean_query), int(clean_query), limit),
                ).fetchall()
            )

        pattern = f"%{clean_query}%"
        return list(
            connection.execute(
                """
                SELECT * FROM orders
                WHERE username LIKE ? OR full_name LIKE ? OR requirements LIKE ?
                ORDER BY id DESC LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        )


def latest_order_for_user(user_id: int) -> sqlite3.Row | None:
    with db_connect() as connection:
        return connection.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def order_notes(order_id: int) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM order_notes WHERE order_id = ? ORDER BY id DESC LIMIT 5",
                (order_id,),
            ).fetchall()
        )


def add_order_note(order_id: int, admin_id: int, note: str) -> bool:
    if get_order(order_id) is None:
        return False
    with db_connect() as connection:
        connection.execute(
            "INSERT INTO order_notes (order_id, admin_id, note, created_at) VALUES (?, ?, ?, ?)",
            (order_id, admin_id, note.strip(), utc_now()),
        )
    return True


def add_order_task(order_id: int, task: str, assignee: str = "", deadline: str = "") -> bool:
    if get_order(order_id) is None:
        return False
    now = utc_now()
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO order_tasks (order_id, task, assignee, deadline, done, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (order_id, task.strip(), assignee.strip(), deadline.strip(), now, now),
        )
    return True


def order_tasks(order_id: int, include_done: bool = False) -> list[sqlite3.Row]:
    query = "SELECT * FROM order_tasks WHERE order_id = ?"
    values: list[Any] = [order_id]
    if not include_done:
        query += " AND done = 0"
    query += " ORDER BY id DESC LIMIT 10"
    with db_connect() as connection:
        return list(connection.execute(query, values).fetchall())


def mark_task_done(task_id: int) -> bool:
    with db_connect() as connection:
        cursor = connection.execute(
            "UPDATE order_tasks SET done = 1, updated_at = ? WHERE id = ?",
            (utc_now(), task_id),
        )
        return cursor.rowcount > 0


def order_stats() -> tuple[int, int, list[sqlite3.Row]]:
    with db_connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        paid_sum = connection.execute(
            "SELECT COALESCE(SUM(estimate), 0) FROM orders WHERE status = 'paid'"
        ).fetchone()[0]
        statuses = list(
            connection.execute(
                "SELECT status, COUNT(*) AS count FROM orders GROUP BY status ORDER BY count DESC"
            ).fetchall()
        )
        return int(total), int(paid_sum), statuses


def pipeline_stats() -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT pipeline_stage, COUNT(*) AS count FROM orders GROUP BY pipeline_stage ORDER BY count DESC"
            ).fetchall()
        )


def service_stats() -> list[tuple[str, int]]:
    stats = {key: 0 for key in PROJECT_PRICES}
    with db_connect() as connection:
        rows = connection.execute("SELECT projects FROM orders").fetchall()
    for row in rows:
        for key in row["projects"].split(","):
            key = normalize_project_key(key)
            if key in stats:
                stats[key] += 1
    return [(PROJECT_PRICES[key][0], count) for key, count in stats.items() if count]


def all_user_ids() -> list[int]:
    with db_connect() as connection:
        return [
            int(row["user_id"])
            for row in connection.execute("SELECT user_id FROM users ORDER BY last_seen DESC").fetchall()
        ]


def pending_reminder_orders(after_hours: int) -> list[sqlite3.Row]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=after_hours)
    rows = latest_orders(limit=200)
    pending_statuses = {"payment_confirmation", "awaiting_receipt", "admin_contact"}
    result = []
    for row in rows:
        if row["status"] not in pending_statuses or row["reminded_at"]:
            continue
        try:
            created_at = datetime.fromisoformat(row["created_at"])
        except ValueError:
            continue
        if created_at <= cutoff:
            result.append(row)
    return result


def export_orders_csv_bytes() -> bytes:
    with db_connect() as connection:
        rows = list(connection.execute("SELECT * FROM orders ORDER BY id DESC").fetchall())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "user_id",
            "full_name",
            "username",
            "projects",
            "estimate",
            "prepayment",
            "status",
            "pipeline_stage",
            "lead_score",
            "estimated_duration",
            "created_at",
            "updated_at",
            "requirements",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["user_id"],
                row["full_name"],
                row["username"],
                projects_from_order(row),
                row["estimate"],
                row["prepayment"],
                STATUS_LABELS.get(row["status"], row["status"]),
                PIPELINE_STAGES.get(row["pipeline_stage"], row["pipeline_stage"]),
                row["lead_score"],
                row["estimated_duration"],
                row["created_at"],
                row["updated_at"],
                row["requirements"],
            ]
        )
    return buffer.getvalue().encode("utf-8")


def is_blocked_user(user_id: int) -> bool:
    with db_connect() as connection:
        return connection.execute(
            "SELECT 1 FROM blocked_users WHERE user_id = ?",
            (user_id,),
        ).fetchone() is not None


def block_user(user_id: int, reason: str = "") -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO blocked_users (user_id, reason, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                reason = excluded.reason,
                created_at = excluded.created_at
            """,
            (user_id, reason.strip(), utc_now()),
        )


def unblock_user(user_id: int) -> None:
    with db_connect() as connection:
        connection.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))


def get_session(user_id: int) -> UserSession:
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    return sessions[user_id]


def reset_session(user_id: int, is_admin_test: bool = False) -> UserSession:
    sessions[user_id] = UserSession(is_admin_test=is_admin_test)
    return sessions[user_id]


def admin_chat_id() -> int | None:
    value = os.getenv("ADMIN_CHAT_ID")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logging.warning("ADMIN_CHAT_ID noto'g'ri formatda: %s", value)
        return None


def admin_chat_ids() -> list[int]:
    values: list[str] = []
    if os.getenv("ADMIN_CHAT_IDS"):
        values.extend(os.getenv("ADMIN_CHAT_IDS", "").split(","))
    if os.getenv("ADMIN_CHAT_ID"):
        values.append(os.getenv("ADMIN_CHAT_ID", ""))

    admin_ids: list[int] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        try:
            admin_id = int(value)
        except ValueError:
            logging.warning("Admin ID noto'g'ri formatda: %s", value)
            continue
        if admin_id not in admin_ids:
            admin_ids.append(admin_id)
    return admin_ids


def admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "toshmirzayevinomjon").strip().lstrip("@")


def admin_contact_text() -> str:
    username = admin_username()
    return (
        "Tushunarli. Agar oldindan predoplata qilish bo'yicha kelishmoqchi bo'lsangiz, "
        "admin bilan gaplashing.\n\n"
        f"Admin lichkasi: @{username}\n"
        f"To'g'ridan-to'g'ri yozish: https://t.me/{username}"
    )


def contact_text() -> str:
    username = admin_username()
    return (
        "ZettaCode Tech bilan aloqa:\n\n"
        f"Telegram: @{username}\n"
        "Telefon: +998-95-184-07-51\n"
        "Kanal: @zettacodetech\n"
        "Portfolio: https://toshmirzayev-inomjon.online/"
    )


def user_help_text() -> str:
    return (
        "Foydalanish uchun commandlar:\n\n"
        "/start - asosiy menyu\n"
        "/new - yangi buyurtma boshlash\n"
        "/prices - xizmatlar narxlarini ko'rish\n"
        "/portfolio - portfolio havolasi\n"
        "/contact - admin bilan aloqa\n"
        "/status - oxirgi buyurtma holati\n"
        "/invoice - oxirgi buyurtma invoice PDF\n"
        "/faq - ko'p beriladigan savollar\n"
        "/promo PROMOKOD - promo kod kiritish\n"
        "/help - yordam\n"
        "/cancel - joriy buyurtmani bekor qilish\n\n"
        "Buyurtma berishda loyiha nima qilishi, foydalanuvchi va admin qanday amallarni bajarishi kerakligini batafsil yozing."
    )


def admin_help_text() -> str:
    return (
        "Admin commandlar:\n\n"
        "/admin - admin panel\n"
        "/orders - oxirgi buyurtmalar\n"
        "/stats - buyurtmalar statistikasi\n"
        "/ai - AI ulanish holati\n"
        "/testorder - mijoz sifatida test buyurtma\n\n"
        "/search matn - buyurtma qidirish\n"
        "/note ID izoh - buyurtmaga ichki izoh qo'shish\n"
        "/draft ID - texnik topshiriq drafti\n"
        "/invoice ID - invoice PDF\n"
        "/stage ID BOSQICH - CRM bosqichini o'zgartirish\n"
        "/task ID matn - buyurtmaga vazifa qo'shish\n"
        "/tasks ID - vazifalar ro'yxati\n"
        "/done TASK_ID - vazifani yopish\n"
        "/deadline ID YYYY-MM-DD - deadline qo'yish\n"
        "/assign ID ism - mas'ul biriktirish\n"
        "/web - web admin panel havolasi\n"
        "/export - buyurtmalarni CSV qilish\n"
        "/broadcast matn - hammaga xabar yuborish\n"
        "/block USER_ID sabab - foydalanuvchini bloklash\n"
        "/unblock USER_ID - blokdan chiqarish\n"
        "/backup - database backup faylini olish\n\n"
        "User commandlar ham ishlaydi: /start, /prices, /portfolio, /contact, /status, /invoice, /faq, /promo, /help, /cancel."
    )


def user_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="new", description="Yangi buyurtma boshlash"),
        BotCommand(command="prices", description="Narxlarni ko'rish"),
        BotCommand(command="portfolio", description="Portfolioni ko'rish"),
        BotCommand(command="contact", description="Admin bilan aloqa"),
        BotCommand(command="status", description="Buyurtma holati"),
        BotCommand(command="invoice", description="Invoice PDF"),
        BotCommand(command="faq", description="Savol-javob"),
        BotCommand(command="promo", description="Promo kod kiritish"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Buyurtmani bekor qilish"),
    ]


def admin_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Admin panel"),
        BotCommand(command="admin", description="Admin panelni ochish"),
        BotCommand(command="orders", description="Oxirgi buyurtmalar"),
        BotCommand(command="stats", description="Statistika"),
        BotCommand(command="search", description="Buyurtma qidirish"),
        BotCommand(command="note", description="Buyurtmaga izoh"),
        BotCommand(command="draft", description="TT draft"),
        BotCommand(command="invoice", description="Invoice PDF"),
        BotCommand(command="stage", description="CRM bosqich"),
        BotCommand(command="task", description="Vazifa qo'shish"),
        BotCommand(command="tasks", description="Vazifalar"),
        BotCommand(command="done", description="Vazifani yopish"),
        BotCommand(command="deadline", description="Deadline"),
        BotCommand(command="assign", description="Mas'ul"),
        BotCommand(command="web", description="Web admin panel"),
        BotCommand(command="export", description="CSV export"),
        BotCommand(command="broadcast", description="Hammaga xabar"),
        BotCommand(command="block", description="User bloklash"),
        BotCommand(command="unblock", description="Blokdan chiqarish"),
        BotCommand(command="backup", description="DB backup"),
        BotCommand(command="ai", description="AI holati"),
        BotCommand(command="testorder", description="Mijoz sifatida test"),
        BotCommand(command="prices", description="Narxlarni ko'rish"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Joriy jarayonni bekor qilish"),
    ]


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(user_bot_commands(), scope=BotCommandScopeDefault())
        for admin_id in admin_chat_ids():
            await bot.set_my_commands(admin_bot_commands(), scope=BotCommandScopeChat(chat_id=admin_id))
    except Exception as exc:
        logging.warning("Bot command menyusini sozlab bo'lmadi: %s", exc)


def web_app_url() -> str:
    return os.getenv("WEB_APP_URL", "https://zettacodetechbot-production.up.railway.app/").strip()


def web_app_button_text() -> str:
    text = os.getenv("WEB_APP_BUTTON_TEXT", "Web App").strip()
    return text[:20] or "Web App"


async def setup_menu_button(bot: Bot) -> None:
    url = web_app_url()
    if not url.startswith("https://"):
        logging.warning("WEB_APP_URL HTTPS bo'lishi kerak: %s", url)
        return

    try:
        menu_button = MenuButtonWebApp(
            text=web_app_button_text(),
            web_app=WebAppInfo(url=url),
        )
        await bot.set_chat_menu_button(menu_button=menu_button)
        for admin_id in admin_chat_ids():
            await bot.set_chat_menu_button(chat_id=admin_id, menu_button=menu_button)
        logging.info("Telegram Menu Web App sozlandi: %s", url)
    except Exception as exc:
        logging.warning("Telegram Menu Web App sozlanmadi: %s", exc)


def is_admin_user(user_id: int) -> bool:
    return user_id in admin_chat_ids()


def is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    timestamps = [
        timestamp
        for timestamp in rate_limits.get(user_id, [])
        if now - timestamp <= RATE_LIMIT_WINDOW_SECONDS
    ]
    timestamps.append(now)
    rate_limits[user_id] = timestamps
    return len(timestamps) > RATE_LIMIT_MAX_MESSAGES


class SecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if isinstance(event, Message):
            track_user(user)

        if is_admin_user(user.id):
            return await handler(event, data)

        if is_blocked_user(user.id):
            if isinstance(event, Message):
                await event.answer("Sizning profilingiz vaqtincha bloklangan. Admin bilan bog'laning.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Siz vaqtincha bloklangansiz.", show_alert=True)
            return None

        if is_rate_limited(user.id):
            if isinstance(event, Message):
                await event.answer("Juda ko'p xabar yuborildi. Iltimos, biroz kutib yozing.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Biroz sekinroq.", show_alert=True)
            return None

        return await handler(event, data)


def normalize_project_key(key: str) -> str:
    return PROJECT_ALIASES.get(key, key)


def ordered_project_keys(keys: Iterable[str]) -> list[str]:
    normalized_keys = {normalize_project_key(key) for key in keys}
    return [key for key in PROJECT_PRICES if key in normalized_keys]


def selected_project_titles(session: UserSession) -> str:
    return ", ".join(PROJECT_PRICES[key][0] for key in ordered_project_keys(session.selected_projects))


def projects_from_order(order: sqlite3.Row) -> str:
    keys = [normalize_project_key(key) for key in order["projects"].split(",")]
    keys = [key for key in keys if key in PROJECT_PRICES]
    return ", ".join(PROJECT_PRICES[key][0] for key in keys)


def minimum_price_for_order(order: sqlite3.Row) -> int:
    keys = [normalize_project_key(key) for key in order["projects"].split(",")]
    return sum(PROJECT_PRICES[key][1] for key in keys if key in PROJECT_PRICES)


def complexity_label_for_order(order: sqlite3.Row) -> str:
    base_price = minimum_price_for_order(order)
    if base_price <= 0:
        return "Aniqlanmagan"
    if order["estimate"] >= base_price + 450:
        return "Murakkab"
    if order["estimate"] >= base_price + 150:
        return "O'rta"
    return "Oddiy"


def minimum_price_for_project(project_key: str, requirements: str) -> int:
    original_key = project_key
    project_key = normalize_project_key(project_key)
    text = requirements.lower()

    if original_key == "telegram_bot":
        if any(keyword in text for keyword in ("kurer", "courier", "yetkazib", "dostavka", "buyurtma")):
            return 400
        if any(keyword in text for keyword in ("twa", "web app", "webapp", "telegram web app")):
            return 300
        return 150

    if original_key == "website":
        if any(
            keyword in text
            for keyword in ("online do'kon", "online dokon", "internet magazin", "ecommerce", "e-commerce", "murakkab", "buyurtma", "savatcha", "katalog")
        ):
            return 600
        if any(keyword in text for keyword in ("korporativ", "kompaniya", "biznes sayt")):
            return 400
        return 200

    return PROJECT_PRICES.get(project_key, ("", 0))[1]


def minimum_price_for_session(session: UserSession) -> int:
    return sum(
        minimum_price_for_project(key, session.requirements)
        for key in ordered_project_keys(session.selected_projects)
    )


def calculate_fallback_estimate(session: UserSession) -> int:
    base_price = minimum_price_for_session(session)
    normalized_text = session.requirements.lower()
    complexity_price = 0

    for keywords, price in COMPLEXITY_RULES:
        if any(keyword in normalized_text for keyword in keywords):
            complexity_price += price

    return base_price + complexity_price


def configured_promo_codes() -> dict[str, int]:
    codes = dict(PROMO_CODES)
    raw_codes = os.getenv("PROMO_CODES", "")
    for item in raw_codes.split(","):
        if ":" not in item:
            continue
        code, percent = item.split(":", 1)
        code = code.strip().upper()
        try:
            percent_value = int(percent.strip())
        except ValueError:
            continue
        if code and 1 <= percent_value <= 50:
            codes[code] = percent_value
    return codes


def set_session_promo(session: UserSession, promo_code: str) -> bool:
    code = promo_code.strip().upper()
    discount = configured_promo_codes().get(code)
    if discount is None:
        return False
    session.promo_code = code
    session.promo_discount_percent = discount
    return True


def apply_promo_discount(session: UserSession, estimate: int) -> int:
    if not session.promo_discount_percent:
        return estimate
    minimum = minimum_price_for_session(session)
    discounted = round(estimate * (100 - session.promo_discount_percent) / 100)
    return max(minimum, int(discounted))


def complexity_label(session: UserSession, estimate: int | None = None) -> str:
    base_price = minimum_price_for_session(session)
    actual_estimate = estimate if estimate is not None else calculate_fallback_estimate(session)
    if base_price <= 0:
        return "Aniqlanmagan"
    if actual_estimate >= base_price + 450:
        return "Murakkab"
    if actual_estimate >= base_price + 150:
        return "O'rta"
    return "Oddiy"


def estimate_duration_label(session: UserSession, estimate: int | None = None) -> str:
    label = complexity_label(session, estimate)
    project_count = len(ordered_project_keys(session.selected_projects))
    if label == "Murakkab" or project_count >= 3:
        return "14-30 kun"
    if label == "O'rta" or project_count == 2:
        return "7-14 kun"
    return "3-7 kun"


def lead_score_label(session: UserSession, estimate: int | None = None) -> str:
    score = 0
    text = session.requirements.lower()
    if len(session.requirements) >= 180:
        score += 2
    elif len(session.requirements) >= 90:
        score += 1
    if any(word in text for word in ("tez", "bugun", "ertaga", "shoshilinch", "boshlash")):
        score += 2
    if any(word in text for word in ("admin panel", "crm", "buyurtma", "katalog", "dostavka", "hisobot")):
        score += 1
    if estimate and estimate >= 600:
        score += 1
    if session.promo_code:
        score += 1

    if score >= 5:
        return "Issiq lead"
    if score >= 3:
        return "O'rta lead"
    return "Sovuq lead"


def detect_project_keys(text: str) -> list[str]:
    normalized_text = text.lower()
    found = []

    if any(keyword in normalized_text for keyword in TWA_KEYWORDS):
        found.append("telegram_twa")
    elif any(keyword in normalized_text for keyword in ORDER_BOT_KEYWORDS) and any(
        keyword in normalized_text for keyword in TELEGRAM_KEYWORDS
    ):
        found.append("telegram_order_bot")
    elif any(keyword in normalized_text for keyword in TELEGRAM_KEYWORDS):
        found.append("telegram_bot_simple")

    has_site_word = any(keyword in normalized_text for keyword in ("sayt", "veb", "web"))
    has_store_feature = any(keyword in normalized_text for keyword in ("buyurtma", "savatcha", "katalog", "mahsulot"))

    if any(keyword in normalized_text for keyword in STORE_KEYWORDS) or (has_site_word and has_store_feature):
        found.append("website_store")
    elif any(keyword in normalized_text for keyword in CORPORATE_SITE_KEYWORDS):
        found.append("website_corporate")
    elif any(keyword in normalized_text for keyword in LANDING_KEYWORDS):
        found.append("website_landing")

    if any(keyword in normalized_text for keyword in MOBILE_KEYWORDS):
        found.append("mobile_app")

    if any(keyword in normalized_text for keyword in ACCOUNTING_KEYWORDS):
        found.append("accounting_system")
    elif any(keyword in normalized_text for keyword in CRM_KEYWORDS):
        found.append("crm_system")

    return found


def looks_project_related(text: str) -> bool:
    normalized_text = text.lower()
    if detect_project_keys(normalized_text):
        return True
    return any(keyword in normalized_text for keyword in BUSINESS_KEYWORDS)


def add_requirements_text(session: UserSession, text: str) -> None:
    clean_text = normalize_payment_policy_text(text.strip())
    if not clean_text:
        return
    session.requirements_validated = False
    if session.requirements:
        session.requirements = f"{session.requirements}\n{clean_text}"
    else:
        session.requirements = clean_text


def has_online_payment_request(text: str) -> bool:
    normalized_text = text.lower()
    return any(keyword in normalized_text for keyword in ONLINE_PAYMENT_KEYWORDS)


def normalize_payment_policy_text(text: str) -> str:
    if not has_online_payment_request(text):
        return text

    normalized = text
    replacements = {
        "Click Payme": "naqd to'lov",
        "Click/Payme": "naqd to'lov",
        "click payme": "naqd to'lov",
        "click/payme": "naqd to'lov",
        "Click": "naqd to'lov",
        "click": "naqd to'lov",
        "Payme": "naqd to'lov",
        "payme": "naqd to'lov",
        "Paynet": "naqd to'lov",
        "paynet": "naqd to'lov",
        "karta": "naqd to'lov",
        "Karta": "naqd to'lov",
        "online to'lov": "naqd to'lov",
        "online tolov": "naqd to'lov",
        "onlayn to'lov": "naqd to'lov",
        "onlayn tolov": "naqd to'lov",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    cleanup_replacements = {
        "naqd to'lov va naqd to'lov tolov": "naqd to'lov",
        "naqd to'lov va naqd to'lov": "naqd to'lov",
        "naqd to'lov tolov": "naqd to'lov",
        "naqd to'lov to'lov": "naqd to'lov",
    }
    for old, new in cleanup_replacements.items():
        normalized = normalized.replace(old, new)
    return f"{normalized}\nTo'lov siyosati: faqat naqd to'lov, online to'lovsiz."


def is_prepayment_refusal(normalized_text: str) -> bool:
    refusal_words = (
        "yoq",
        "yo'q",
        "no",
        "rad",
        "istamayman",
        "istemayman",
        "istamiman",
        "xohlamayman",
        "xoxlamayman",
        "tolamayman",
        "to'lamayman",
        "qilmayman",
        "bermayman",
    )
    admin_words = ("admin", "gaplash", "kelish")
    if any(word in normalized_text for word in refusal_words):
        return True
    return any(word in normalized_text for word in admin_words)


def local_requirement_validation(session: UserSession) -> RequirementValidation:
    text = session.requirements.strip()
    normalized_text = text.lower()
    words = [word for word in normalized_text.replace("\n", " ").split(" ") if word]
    feature_keywords = (
        "admin",
        "panel",
        "to'lov",
        "tolov",
        "naqd",
        "naxd",
        "buyurtma",
        "katalog",
        "savatcha",
        "mahsulot",
        "xizmat",
        "login",
        "registratsiya",
        "profil",
        "mijoz",
        "foydalanuvchi",
        "dostavka",
        "kurer",
        "statistika",
        "hisobot",
        "hisob",
        "crm",
        "baza",
        "api",
        "integratsiya",
        "sms",
        "xabar",
        "bildirishnoma",
        "menyu",
        "forma",
        "sahifa",
        "portfolio",
        "kontakt",
    )
    feature_count = sum(1 for keyword in feature_keywords if keyword in normalized_text)
    missing_questions: list[str] = []

    if not session.selected_projects:
        missing_questions.append("Loyiha turi qaysi: Telegram bot, TWA, sayt, mobil ilova, CRM yoki hisob-kitob tizimimi?")

    if (len(words) < 14 or len(text) < 80) and feature_count < 4:
        missing_questions.append("Loyiha aniq nima vazifani bajaradi?")

    if feature_count < 2:
        missing_questions.append("Foydalanuvchi va admin qanday amallarni bajaradi?")

    if any(key in session.selected_projects for key in ("telegram_order_bot", "website_store")):
        commerce_keywords = ("katalog", "mahsulot", "savatcha", "buyurtma", "to'lov", "tolov", "dostavka", "kurer")
        if sum(1 for keyword in commerce_keywords if keyword in normalized_text) < 2:
            missing_questions.append("Katalog, buyurtma, to'lov va yetkazib berish qanday ishlaydi?")

    if any(key in session.selected_projects for key in ("crm_system", "accounting_system")):
        system_keywords = ("mijoz", "hisob", "statistika", "hisobot", "ombor", "xodim", "rol", "baza")
        if sum(1 for keyword in system_keywords if keyword in normalized_text) < 2:
            missing_questions.append("Qaysi ma'lumotlar saqlanadi va qanday hisobotlar kerak?")

    if missing_questions:
        questions_text = "\n".join(f"- {question}" for question in missing_questions[:4])
        return RequirementValidation(
            enough=False,
            reply=(
                "Bu ma'lumot kam. Bu bilan sizning loyihangizni qila olmaymiz.\n\n"
                "Iltimos, quyidagilarni yozib bering:\n"
                f"{questions_text}"
            ),
            missing_questions=missing_questions[:4],
        )

    return RequirementValidation(
        enough=True,
        reply="Ma'lumotlar yetarli. Endi loyihani baholab, taxminiy narx chiqarish mumkin.",
    )


def only_minor_detail_questions(questions: list[str]) -> bool:
    if not questions:
        return True

    minor_keywords = (
        "maydon",
        "field",
        "status",
        "rang",
        "dizayn",
        "ichki sozlama",
        "sozlamalari",
        "nomlari",
        "rasmi",
        "tavsifi",
        "narxi",
        "miqdor",
        "matn",
        "logo",
        "rasmlar",
    )
    return all(any(keyword in question.lower() for keyword in minor_keywords) for question in questions)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("AI javobida JSON topilmadi.")
    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(cleaned[start:])
    if not isinstance(parsed, dict):
        raise ValueError("AI javobi JSON obyekt emas.")
    return parsed


async def groq_json(
    messages: list[dict[str, str]],
    max_tokens: int = 600,
    temperature: float = 0.2,
) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY sozlanmagan.")

    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(timeout=timeout) as client:
        async with client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response_text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Groq API xatosi {response.status}: {response_text[:200]}")

    data = json.loads(response_text)
    content = data["choices"][0]["message"]["content"]
    return parse_json_object(content)


async def estimate_with_ai(session: UserSession) -> EstimateResult:
    fallback = calculate_fallback_estimate(session)
    fallback_summary = (
        "Talablaringiz minimal narxlar va funksional murakkablik bo'yicha baholandi."
    )
    fallback_features = ["Loyiha talablari", "Asosiy ishlab chiqish", "Boshlang'ich sozlash"]

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return EstimateResult(fallback, fallback_summary, fallback_features)

    min_price = minimum_price_for_session(session)
    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech kompaniyasining loyiha baholash yordamchisisan. "
                "Faqat o'zbek tilida fikr yurit. Mijoz buyurtma qilayotgan loyiha ichidagi to'lov funksiyasi uchun "
                "Click, Payme, Paynet, karta yoki boshqa online to'lov integratsiyasini taklif qilma. "
                "Loyiha ichidagi to'lov funksiyasi faqat naqd to'lov bo'ladi. "
                "ZettaCode xizmatiga predoplata alohida karta orqali qabul qilinadi, bu baholash qismida muhokama qilinmaydi. "
                "Boshlang'ich narxlar: oddiy Telegram bot 150$, TWA bot 300$, "
                "kurer/buyurtma Telegram bot 400$, landing page 200$, korporativ sayt 400$, "
                "online do'kon yoki murakkab veb tizim 600$, mobil ilova 800$, CRM 350$, "
                "hisob-kitob va statistika tizimi 400$. "
                "Agar bir nechta loyiha turi tanlangan bo'lsa, minimal narxlarni qo'sh. "
                "Talab murakkab bo'lsa, narxni oshir. Tavsiya narx minimal narxdan past bo'lmasin. "
                "Javobni faqat JSON shaklida qaytar: "
                "{\"estimate\": integer, \"summary\": string, \"features\": [string, string, string]}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Tanlangan loyiha turlari: {selected_project_titles(session)}\n"
                f"Minimal umumiy narx: ${min_price}\n"
                f"Qoidaviy fallback narx: ${fallback}\n"
                f"Mijoz talablari:\n{session.requirements}"
            ),
        },
    ]

    try:
        parsed = await groq_json(messages, max_tokens=600, temperature=0.2)
        estimate = int(parsed.get("estimate", fallback))
        estimate = max(estimate, fallback, min_price)
        features = parsed.get("features") or fallback_features
        if not isinstance(features, list):
            features = fallback_features
        features = [str(item).strip() for item in features if str(item).strip()][:5]
        summary = str(parsed.get("summary") or fallback_summary).strip()
        return EstimateResult(
            estimate=estimate,
            summary=summary,
            features=features or fallback_features,
            ai_used=True,
        )
    except Exception as exc:
        logging.warning("AI tahlil ishlamadi, fallback ishlatildi: %s", exc)
        return EstimateResult(fallback, fallback_summary, fallback_features)


async def validate_requirements_with_ai(session: UserSession) -> RequirementValidation:
    local_validation = local_requirement_validation(session)
    if not local_validation.enough:
        return local_validation

    if not os.getenv("GROQ_API_KEY"):
        return local_validation

    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech kompaniyasining loyiha talablarini qabul qiluvchi ekspertsan. "
                "Mijoz yozgan talablarni o'qi va loyiha nima qilishi kerakligini haqiqatdan tushunish mumkinmi, shuni bahola. "
                "Juda umumiy gaplar: 'bot kerak', 'sayt kerak', 'crm kerak', 'magazin kerak', 'hammasi bo'lsin' yetarli emas. "
                "Yetarli bo'lishi uchun loyiha maqsadi, asosiy funksiyalar, foydalanuvchi/admin amallari va kerak bo'lsa "
                "to'lov, buyurtma, katalog, integratsiya yoki hisobotlar aniq yozilgan bo'lishi kerak. "
                "Bu savdo bosqichi, to'liq texnik topshiriq emas: mahsulot maydonlari, status nomlari, dizayn ranglari, "
                "to'lov tizimining ichki sozlamalari kabi mayda detallarni majburiy talab qilma. "
                "Masalan 'mijoz katalogdan mahsulot ko'radi, buyurtma beradi, admin buyurtmalarni ko'radi, "
                "naqd to'lov va kurer dostavka bo'ladi' degan talab yetarli hisoblanadi. "
                "Mijoz buyurtma qilayotgan loyiha ichida Click, Payme, Paynet, karta yoki boshqa online to'lov integratsiyalariga ruxsat berma; "
                "agar talabda shular yozilgan bo'lsa, loyiha ichidagi to'lov funksiyasi faqat naqd to'lov bilan ko'rib chiqilishini ayt. "
                "Agar kam bo'lsa reply aynan shu mazmunda boshlansin: "
                "'Bu ma'lumot kam. Bu bilan sizning loyihangizni qila olmaymiz.' "
                "Narx yoki predoplata haqida gapirma. Faqat talablarni aniqlashtir. "
                "Javob faqat JSON bo'lsin: "
                "{\"enough\": boolean, \"reply\": string, \"missing_questions\": [string, string, string]}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Loyiha turi: {selected_project_titles(session)}\n"
                f"Talablar:\n{session.requirements}"
            ),
        },
    ]

    try:
        parsed = await groq_json(messages, max_tokens=500, temperature=0.1)
        missing_questions = parsed.get("missing_questions") or []
        if not isinstance(missing_questions, list):
            missing_questions = []
        missing_questions = [str(question).strip() for question in missing_questions if str(question).strip()][:4]
        enough = bool(parsed.get("enough"))
        reply = str(parsed.get("reply") or "").strip()

        if not enough:
            if local_validation.enough and only_minor_detail_questions(missing_questions):
                return RequirementValidation(
                    enough=True,
                    reply="Ma'lumotlar savdo bosqichi uchun yetarli. Mayda texnik detallar keyingi bosqichda aniqlashtiriladi.",
                    missing_questions=[],
                    ai_used=True,
                )

            if not reply:
                questions_text = "\n".join(f"- {question}" for question in missing_questions)
                reply = (
                    "Bu ma'lumot kam. Bu bilan sizning loyihangizni qila olmaymiz.\n\n"
                    "Iltimos, quyidagilarni aniqlashtiring:\n"
                    f"{questions_text}"
                )
            return RequirementValidation(
                enough=False,
                reply=reply,
                missing_questions=missing_questions,
                ai_used=True,
            )

        return RequirementValidation(
            enough=True,
            reply=reply or "Ma'lumotlar yetarli. Endi loyihani baholab, taxminiy narx chiqarish mumkin.",
            ai_used=True,
        )
    except Exception as exc:
        logging.warning("AI talab tekshiruvi ishlamadi, lokal tekshiruv ishlatildi: %s", exc)
        return local_validation


async def guide_conversation_with_ai(session: UserSession, text: str) -> ConversationResult:
    fallback_relevant = looks_project_related(text) or bool(session.selected_projects)
    fallback_projects = detect_project_keys(text)
    fallback_session = UserSession(
        selected_projects=set(session.selected_projects).union(fallback_projects),
        requirements=f"{session.requirements}\n{text}".strip(),
    )
    fallback_validation = local_requirement_validation(fallback_session)
    if not fallback_relevant:
        fallback_reply = (
            "Kechirasiz, men faqat Telegram bot, veb-sayt, mobil ilova, CRM va hisob-kitob tizimi buyurtmalari bo'yicha "
            "yordam bera olaman. Iltimos, loyiha turi yoki talablaringizni yozing."
        )
    elif not fallback_validation.enough:
        fallback_reply = fallback_validation.reply
    else:
        fallback_reply = "Ma'lumotlar yetarli ko'rinyapti. Xohlasangiz narxni hisoblash tugmasini bosing."

    if not os.getenv("GROQ_API_KEY"):
        return ConversationResult(
            relevant=fallback_relevant,
            reply=fallback_reply,
            suggested_projects=fallback_projects,
            captured_requirements=text if fallback_relevant else "",
            should_estimate=fallback_relevant and fallback_validation.enough,
            enough_details=fallback_validation.enough,
            missing_questions=fallback_validation.missing_questions,
        )

    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech kompaniyasining o'zbek tilidagi AI savdo agentisan. "
                "Vazifang: mijoz bilan faqat Telegram bot, veb-sayt, mobil ilova, CRM va hisob-kitob tizimi buyurtmasi haqida "
                "professional suhbatlashish. Mavzudan tashqari savollar, shaxsiy suhbat, siyosat, yangilik, "
                "kripto, dars, kod yozib berish, hazil yoki umumiy maslahatlarni davom ettirma; muloyim tarzda "
                "loyiha buyurtmasiga qaytar. Mijoz buyurtma qilayotgan loyiha ichidagi to'lov funksiyasi uchun "
                "Click, Payme, Paynet, karta yoki boshqa online to'lov integratsiyasini taklif qilma; "
                "loyiha ichidagi to'lov faqat naqd bo'lishini ayt. "
                "Narxni yakuniy hisoblash alohida bosqichda bo'ladi, sen bu javobda to'lov so'ramaysan. "
                "Agar talablar noaniq bo'lsa yoki loyiha nima qilishi tushunarsiz bo'lsa, "
                "reply matnini aynan shu mazmunda boshla: 'Bu ma'lumot kam. Bu bilan sizning loyihangizni qila olmaymiz.' "
                "Keyin 2-4 ta aniq savol ber. Agar loyiha nima qilishi, asosiy funksiyalar, foydalanuvchi/admin amallari "
                "va muhim integratsiyalar tushunarli bo'lsa, enough_details=true va should_estimate=true qil. "
                "To'liq texnik topshiriq talab qilma: katalog, buyurtma, admin panel, to'lov, dostavka kabi asosiy oqim "
                "yozilgan bo'lsa, bu savdo bosqichi uchun yetarli. "
                "Agar mijoz o'z loyihasiga Click/Payme/Paynet yoki online to'lov integratsiyasi so'rasa, bu ruxsat emasligini va loyiha ichidagi to'lov faqat naqd bo'lishini tushuntir. "
                "Javob faqat JSON bo'lsin: "
                "suggested_projects faqat shu kalitlardan bo'lsin: telegram_bot_simple, telegram_twa, "
                "telegram_order_bot, website_landing, website_corporate, website_store, mobile_app, "
                "crm_system, accounting_system. "
                "Javob formati: "
                "{\"relevant\": boolean, \"reply\": string, \"suggested_projects\": [\"telegram_twa\"], "
                "\"captured_requirements\": string, \"should_estimate\": boolean, "
                "\"enough_details\": boolean, \"missing_questions\": [string, string, string]}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bosqich: {session.stage}\n"
                f"Tanlangan loyiha turlari: {selected_project_titles(session) or 'hali tanlanmagan'}\n"
                f"Oldingi talablar:\n{session.requirements or '-'}\n\n"
                f"Mijozning yangi xabari:\n{text}"
            ),
        },
    ]

    try:
        parsed = await groq_json(messages, max_tokens=500, temperature=0.1)
        local_projects = detect_project_keys(text)
        suggested_projects = local_projects or parsed.get("suggested_projects") or fallback_projects
        if not isinstance(suggested_projects, list):
            suggested_projects = fallback_projects
        suggested_projects = [key for key in suggested_projects if key in PROJECT_PRICES]
        return ConversationResult(
            relevant=bool(parsed.get("relevant")),
            reply=str(parsed.get("reply") or fallback_reply).strip(),
            suggested_projects=suggested_projects,
            captured_requirements=str(parsed.get("captured_requirements") or "").strip(),
            should_estimate=bool(parsed.get("should_estimate")) and bool(parsed.get("enough_details")),
            enough_details=bool(parsed.get("enough_details")),
            missing_questions=[
                str(question).strip()
                for question in (parsed.get("missing_questions") or [])
                if str(question).strip()
            ][:4],
            ai_used=True,
        )
    except Exception as exc:
        logging.warning("AI suhbat tahlili ishlamadi, fallback ishlatildi: %s", exc)
        return ConversationResult(
            relevant=fallback_relevant,
            reply=fallback_reply,
            suggested_projects=fallback_projects,
            captured_requirements=text if fallback_relevant else "",
            should_estimate=fallback_relevant and fallback_validation.enough,
            enough_details=fallback_validation.enough,
            missing_questions=fallback_validation.missing_questions,
        )


def project_keyboard(selected: Set[str]) -> InlineKeyboardMarkup:
    rows = []
    for key, (title, _) in PROJECT_PRICES.items():
        mark = "[x]" if key in selected else "[ ]"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {title}",
                    callback_data=f"project:{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Tasdiqlash", callback_data="project:confirm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def welcome_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Buyurtma berish", callback_data="menu:start_order")],
            [InlineKeyboardButton(text="Narxlarni ko'rish", callback_data="menu:prices")],
            [
                InlineKeyboardButton(text="Buyurtma holati", callback_data="menu:status"),
                InlineKeyboardButton(text="FAQ", callback_data="menu:faq"),
            ],
            [InlineKeyboardButton(text="Loyiha turini tanlash", callback_data="menu:choose_project")],
        ]
    )


def prices_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Oddiy Telegram bot", callback_data="quick_project:telegram_bot_simple")],
            [InlineKeyboardButton(text="Telegram Web App (TWA)", callback_data="quick_project:telegram_twa")],
            [InlineKeyboardButton(text="Kurer / buyurtma bot", callback_data="quick_project:telegram_order_bot")],
            [InlineKeyboardButton(text="Landing Page", callback_data="quick_project:website_landing")],
            [InlineKeyboardButton(text="Korporativ sayt", callback_data="quick_project:website_corporate")],
            [InlineKeyboardButton(text="Online do'kon", callback_data="quick_project:website_store")],
            [InlineKeyboardButton(text="Mobil ilova buyurtma qilish", callback_data="quick_project:mobile_app")],
            [InlineKeyboardButton(text="CRM tizimi", callback_data="quick_project:crm_system")],
            [InlineKeyboardButton(text="Hisob-kitob / statistika", callback_data="quick_project:accounting_system")],
            [
                InlineKeyboardButton(text="Portfolio", url="https://toshmirzayev-inomjon.online/"),
                InlineKeyboardButton(text="Telegram", url="https://t.me/toshmirzayevinomjon"),
            ],
            [InlineKeyboardButton(text="Kanal", url="https://t.me/zettacodetech")],
            [InlineKeyboardButton(text="Asosiy menyu", callback_data="menu:home")],
        ]
    )


def contact_inline_keyboard() -> InlineKeyboardMarkup:
    username = admin_username()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Admin", url=f"https://t.me/{username}"),
                InlineKeyboardButton(text="Portfolio", url="https://toshmirzayev-inomjon.online/"),
            ],
            [InlineKeyboardButton(text="Kanal", url="https://t.me/zettacodetech")],
            [InlineKeyboardButton(text="Buyurtma berish", callback_data="menu:start_order")],
        ]
    )


def requirements_keyboard(has_requirements: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Yana talab qo'shish", callback_data="requirements:more")],
        [InlineKeyboardButton(text="Talablarni qayta yozish", callback_data="requirements:edit")],
        [InlineKeyboardButton(text="Loyiha turini o'zgartirish", callback_data="requirements:change_project")],
    ]
    if has_requirements:
        rows.insert(0, [InlineKeyboardButton(text="Narxni hisoblash", callback_data="requirements:estimate")])
    rows.append([InlineKeyboardButton(text="Bekor qilish", callback_data="requirements:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=START_ORDER_TEXT), KeyboardButton(text=PRICE_TEXT)],
        [KeyboardButton(text=MAIN_MENU_TEXT), KeyboardButton(text=CANCEL_TEXT)],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text=ADMIN_PANEL_TEXT)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def requirements_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CALCULATE_TEXT), KeyboardButton(text=CANCEL_TEXT)],
            [KeyboardButton(text=PRICE_TEXT), KeyboardButton(text=MAIN_MENU_TEXT)],
        ],
        resize_keyboard=True,
    )


def payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ha", callback_data="payment:yes"),
                InlineKeyboardButton(text="Yo'q", callback_data="payment:no"),
            ],
            [InlineKeyboardButton(text="Talablarni tahrirlash", callback_data="payment:edit")],
            [InlineKeyboardButton(text="Invoice PDF", callback_data="payment:invoice")],
        ]
    )


def admin_review_keyboard(user_id: int, order_id: int | None) -> InlineKeyboardMarkup:
    suffix = f":{order_id}" if order_id is not None else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="PUL TUSHDI (Ha)",
                    callback_data=f"admin:paid:{user_id}{suffix}",
                ),
                InlineKeyboardButton(
                    text="PUL TUSHMADI (Yo'q)",
                    callback_data=f"admin:not_paid:{user_id}{suffix}",
                ),
            ],
            [InlineKeyboardButton(text="Buyurtmani ko'rish", callback_data=f"panel:order:{order_id}")],
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Buyurtmalar", callback_data="panel:orders")],
            [
                InlineKeyboardButton(text="Kutilayotgan", callback_data="panel:orders:payment_confirmation"),
                InlineKeyboardButton(text="Chek kutilmoqda", callback_data="panel:orders:awaiting_receipt"),
            ],
            [
                InlineKeyboardButton(text="Tekshiruv", callback_data="panel:orders:checking"),
                InlineKeyboardButton(text="Admin kelishuv", callback_data="panel:orders:admin_contact"),
            ],
            [
                InlineKeyboardButton(text="To'langan", callback_data="panel:orders:paid"),
                InlineKeyboardButton(text="Rad etilgan", callback_data="panel:orders:rejected"),
            ],
            [
                InlineKeyboardButton(text="Pipeline: Narx", callback_data="panel:pipeline:priced"),
                InlineKeyboardButton(text="Pipeline: Ish", callback_data="panel:pipeline:in_progress"),
            ],
            [InlineKeyboardButton(text="Statistika", callback_data="panel:stats")],
            [
                InlineKeyboardButton(text="CSV export", callback_data="panel:export"),
                InlineKeyboardButton(text="Backup", callback_data="panel:backup"),
            ],
            [
                InlineKeyboardButton(text="Broadcast", callback_data="panel:broadcast"),
                InlineKeyboardButton(text="AI holati", callback_data="panel:ai_status"),
            ],
            [InlineKeyboardButton(text="Web panel", url=web_admin_url())],
            [InlineKeyboardButton(text="Mijoz sifatida test", callback_data="panel:test_order")],
        ]
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Yuborish", callback_data="panel:confirm_broadcast"),
                InlineKeyboardButton(text="Bekor qilish", callback_data="panel:cancel_broadcast"),
            ]
        ]
    )


def orders_keyboard(orders: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    rows = []
    for order in orders:
        status = STATUS_LABELS.get(order["status"], order["status"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{order['id']} - {status} - ${order['estimate']}",
                    callback_data=f"panel:order:{order['id']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="Hammasi", callback_data="panel:orders"),
            InlineKeyboardButton(text="To'langan", callback_data="panel:orders:paid"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Tekshiruv", callback_data="panel:orders:checking"),
            InlineKeyboardButton(text="Admin kelishuv", callback_data="panel:orders:admin_contact"),
        ]
    )
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data="panel:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_detail_keyboard(order: sqlite3.Row) -> InlineKeyboardMarkup:
    rows = []
    if order["status"] == "checking":
        rows.append(
            [
                InlineKeyboardButton(
                    text="PUL TUSHDI (Ha)",
                    callback_data=f"admin:paid:{order['user_id']}:{order['id']}",
                ),
                InlineKeyboardButton(
                    text="PUL TUSHMADI (Yo'q)",
                    callback_data=f"admin:not_paid:{order['user_id']}:{order['id']}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="TT draft", callback_data=f"panel:draft:{order['id']}"),
            InlineKeyboardButton(text="Izoh qo'shish", callback_data=f"panel:note:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Invoice PDF", callback_data=f"panel:invoice:{order['id']}"),
            InlineKeyboardButton(text="Task qo'shish", callback_data=f"panel:task:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Ish boshlandi", callback_data=f"panel:stage:{order['id']}:in_progress"),
            InlineKeyboardButton(text="Tugatildi", callback_data=f"panel:stage:{order['id']}:done"),
        ]
    )
    rows.append([InlineKeyboardButton(text="Buyurtmalar", callback_data="panel:orders")])
    rows.append([InlineKeyboardButton(text="Admin panel", callback_data="panel:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def safe_edit_or_answer(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)


async def show_admin_panel(message: Message) -> None:
    await message.answer(
        "ZettaCode Tech admin panel.\n\n"
        "Bu profil admin sifatida belgilangan. Oddiy mijoz buyurtma oqimi avtomatik ochilmaydi.",
        reply_markup=admin_panel_keyboard(),
    )


async def show_main_menu(message: Message, user_id: int) -> None:
    await message.answer(
        "ZettaCode Tech AI savdo agenti tayyor. Pastdagi tugmalardan foydalanishingiz yoki "
        "loyihangiz haqida to'g'ridan-to'g'ri yozishingiz mumkin.",
        reply_markup=main_reply_keyboard(is_admin_user(user_id)),
    )
    await message.answer(
        "Qaysi amalni bajaramiz?",
        reply_markup=welcome_inline_keyboard(),
    )


async def show_prices(message: Message) -> None:
    await message.answer(
        SERVICE_PRICE_TEXT,
        reply_markup=prices_inline_keyboard(),
    )


async def show_contact(message: Message) -> None:
    await message.answer(contact_text(), reply_markup=contact_inline_keyboard())


async def show_portfolio(message: Message) -> None:
    await message.answer(
        portfolio_text("all"),
        reply_markup=portfolio_keyboard(),
    )


def portfolio_text(category: str) -> str:
    texts = {
        "telegram": (
            "Telegram bot portfolio yo'nalishi:\n"
            "- menyu va katalog botlar\n"
            "- buyurtma qabul qiluvchi botlar\n"
            "- admin panel va statistika\n"
            "- TWA mini app botlar\n\n"
            "Portfolio: https://toshmirzayev-inomjon.online/"
        ),
        "web": (
            "Veb-sayt portfolio yo'nalishi:\n"
            "- landing page\n"
            "- korporativ sayt\n"
            "- online katalog va buyurtma tizimlari\n"
            "- admin panel bilan veb tizimlar\n\n"
            "Portfolio: https://toshmirzayev-inomjon.online/"
        ),
        "crm": (
            "CRM va hisob-kitob portfolio yo'nalishi:\n"
            "- mijozlar bazasi\n"
            "- xodimlar va rollar\n"
            "- statistika va hisobot\n"
            "- ombor va kassa jarayonlari\n\n"
            "Portfolio: https://toshmirzayev-inomjon.online/"
        ),
        "mobile": (
            "Mobil ilova portfolio yo'nalishi:\n"
            "- Android/iOS xizmat ilovalari\n"
            "- startap MVP\n"
            "- buyurtma va profil oqimlari\n"
            "- admin/API bilan ishlash\n\n"
            "Portfolio: https://toshmirzayev-inomjon.online/"
        ),
    }
    return texts.get(
        category,
        "ZettaCode Tech portfolio:\n"
        "Telegram bot, veb-sayt, mobil ilova, CRM va hisob-kitob tizimlari bo'yicha ishlar.\n\n"
        "Portfolio: https://toshmirzayev-inomjon.online/",
    )


def portfolio_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Telegram botlar", callback_data="portfolio:telegram"),
                InlineKeyboardButton(text="Veb-saytlar", callback_data="portfolio:web"),
            ],
            [
                InlineKeyboardButton(text="CRM", callback_data="portfolio:crm"),
                InlineKeyboardButton(text="Mobil ilova", callback_data="portfolio:mobile"),
            ],
            [InlineKeyboardButton(text="Portfolio sayti", url="https://toshmirzayev-inomjon.online/")],
            [InlineKeyboardButton(text="Buyurtma berish", callback_data="menu:start_order")],
        ]
    )


def faq_text() -> str:
    return (
        "Ko'p beriladigan savollar:\n\n"
        "1. Narx qanday hisoblanadi?\n"
        "Narx loyiha turi, funksiyalar va murakkablikka qarab hisoblanadi.\n\n"
        "2. Ish qachon boshlanadi?\n"
        "Kelishilgan summaning 50% predoplata qismi kartaga tushgandan keyin boshlanadi.\n\n"
        "3. Loyiha ichida online to'lov bo'ladimi?\n"
        "Mijoz buyurtma qilayotgan loyiha ichidagi to'lov qismi faqat naqd to'lov sifatida ko'rib chiqiladi.\n\n"
        "4. Talablar kam bo'lsa nima bo'ladi?\n"
        "Bot narx chiqarmaydi, avval loyiha nima qilishi kerakligini aniqlashtiradi.\n\n"
        "5. Admin bilan qanday bog'lanaman?\n"
        f"Telegram: @{admin_username()}"
    )


async def show_faq(message: Message) -> None:
    await message.answer(faq_text(), reply_markup=contact_inline_keyboard())


async def show_user_status(message: Message, user_id: int | None = None) -> None:
    target_user_id = user_id if user_id is not None else message.from_user.id
    order = latest_order_for_user(target_user_id)
    if order is None:
        await message.answer(
            "Sizda hali buyurtma topilmadi. Yangi buyurtma boshlash uchun /new yuboring.",
            reply_markup=welcome_inline_keyboard(),
        )
        return
    status = STATUS_LABELS.get(order["status"], order["status"])
    await message.answer(
        f"Oxirgi buyurtmangiz: #{order['id']}\n"
        f"Loyiha turi: {projects_from_order(order)}\n"
        f"Holat: {status}\n"
        f"Taxminiy narx: ${order['estimate']}\n"
        f"50% predoplata: ${order['prepayment']}\n\n"
        "Savol bo'lsa admin bilan bog'lanishingiz mumkin.",
        reply_markup=contact_inline_keyboard(),
    )


async def show_project_menu(
    message: Message,
    user_id: int,
    reset: bool = False,
    is_admin_test: bool = False,
) -> None:
    session = reset_session(user_id, is_admin_test=is_admin_test) if reset else get_session(user_id)
    session.stage = "choose_project"
    title = "Test buyurtma rejimi.\n\n" if session.is_admin_test else ""
    await message.answer(
        f"{title}Assalomu alaykum! ZettaCode Tech'ga xush kelibsiz.\n\n"
        "Loyihangiz qaysi yo'nalishda bo'ladi? Bir yoki bir nechtasini tanlashingiz mumkin:",
        reply_markup=project_keyboard(session.selected_projects),
    )


def format_features(features: list[str]) -> str:
    return "\n".join(f"- {feature}" for feature in features[:5])


def format_order_detail(order: sqlite3.Row) -> str:
    status = STATUS_LABELS.get(order["status"], order["status"])
    pipeline = PIPELINE_STAGES.get(order["pipeline_stage"], order["pipeline_stage"])
    features = json.loads(order["ai_features"] or "[]")
    feature_text = format_features(features) if features else "-"
    username = f"@{order['username']}" if order["username"] else "username yo'q"
    ai_label = "AI tahlil" if order["ai_used"] else "Tahlil"
    notes = order_notes(order["id"])
    notes_text = "\n".join(f"- {note['note']}" for note in notes) if notes else "-"
    tasks = order_tasks(order["id"])
    tasks_text = (
        "\n".join(
            f"- #{task['id']} {task['task']}"
            + (f" | {task['assignee']}" if task["assignee"] else "")
            + (f" | deadline: {task['deadline']}" if task["deadline"] else "")
            for task in tasks
        )
        if tasks
        else "-"
    )
    return (
        f"Buyurtma #{order['id']}\n\n"
        f"Holat: {status}\n"
        f"CRM bosqich: {pipeline}\n"
        f"Mijoz ID: {order['user_id']}\n"
        f"Mijoz: {order['full_name']} ({username})\n"
        f"Loyiha turi: {projects_from_order(order)}\n"
        f"Murakkablik: {complexity_label_for_order(order)}\n"
        f"Taxminiy muddat: {order['estimated_duration'] or '-'}\n"
        f"Lead score: {order['lead_score'] or '-'}\n"
        f"Mas'ul: {order['assignee'] or '-'}\n"
        f"Deadline: {order['deadline'] or '-'}\n"
        f"Taxminiy narx: ${order['estimate']}\n"
        f"50% predoplata: ${order['prepayment']}\n\n"
        f"{ai_label}: {order['ai_summary']}\n"
        f"Asosiy bandlar:\n{feature_text}\n\n"
        f"Tasklar:\n{tasks_text}\n\n"
        f"Admin izohlari:\n{notes_text}\n\n"
        f"Talablar:\n{order['requirements']}"
    )


def format_stats_text() -> str:
    total, paid_sum, statuses = order_stats()
    pipelines = pipeline_stats()
    services = service_stats()
    lines = [
        "Buyurtmalar statistikasi:",
        "",
        f"Jami buyurtmalar: {total}",
        f"Qabul qilingan umumiy qiymat: ${paid_sum}",
        "",
        "Holatlar:",
    ]
    if statuses:
        lines.extend(
            f"- {STATUS_LABELS.get(row['status'], row['status'])}: {row['count']}"
            for row in statuses
        )
    else:
        lines.append("- Hali ma'lumot yo'q")
    if services:
        lines.extend(["", "Xizmatlar bo'yicha:"])
        lines.extend(f"- {title}: {count}" for title, count in services)
    if pipelines:
        lines.extend(["", "CRM pipeline:"])
        lines.extend(
            f"- {PIPELINE_STAGES.get(row['pipeline_stage'], row['pipeline_stage'])}: {row['count']}"
            for row in pipelines
        )
    return "\n".join(lines)


def ai_status_text() -> str:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    status = "ulangan" if api_key else "ulanmagan"
    return f"AI holati: {status}\nModel: {model}"


def fallback_technical_draft(order: sqlite3.Row) -> str:
    features = json.loads(order["ai_features"] or "[]")
    feature_text = format_features(features) if features else "- Asosiy funksiyalar keyingi bosqichda aniqlashtiriladi"
    return (
        f"Texnik topshiriq drafti - Buyurtma #{order['id']}\n\n"
        f"Loyiha turi: {projects_from_order(order)}\n"
        f"Murakkablik: {complexity_label_for_order(order)}\n"
        f"Taxminiy narx: ${order['estimate']}\n\n"
        "Maqsad:\n"
        f"{order['ai_summary'] or 'Mijoz talablariga mos raqamli yechim ishlab chiqish.'}\n\n"
        f"Asosiy funksiyalar:\n{feature_text}\n\n"
        "To'lov siyosati:\n"
        "- ZettaCode xizmatiga 50% predoplata plastik karta orqali qabul qilinadi.\n"
        "- Mijoz buyurtma qilayotgan loyiha ichidagi to'lov funksiyasi faqat naqd to'lov sifatida ko'rib chiqiladi.\n\n"
        f"Mijoz talablari:\n{order['requirements']}"
    )


async def technical_draft_for_order(order: sqlite3.Row) -> str:
    if not os.getenv("GROQ_API_KEY"):
        return fallback_technical_draft(order)

    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech uchun texnik topshiriq drafti yozuvchi yordamchisan. "
                "O'zbek tilida qisqa, professional TT draft yoz. Online to'lov integratsiyalarini taklif qilma; "
                "loyiha ichidagi to'lov faqat naqd to'lov bo'lishini yoz. "
                "Javob faqat JSON bo'lsin: {\"draft\": string}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Buyurtma ID: {order['id']}\n"
                f"Loyiha turi: {projects_from_order(order)}\n"
                f"Narx: ${order['estimate']}\n"
                f"Tahlil: {order['ai_summary']}\n"
                f"Talablar:\n{order['requirements']}"
            ),
        },
    ]

    try:
        parsed = await groq_json(messages, max_tokens=900, temperature=0.15)
        draft = str(parsed.get("draft") or "").strip()
        return draft or fallback_technical_draft(order)
    except Exception as exc:
        logging.warning("TT draft AI orqali yaratilmadi, fallback ishlatildi: %s", exc)
        return fallback_technical_draft(order)


async def show_orders(message: Message) -> None:
    orders = latest_orders()
    if not orders:
        await message.answer("Hozircha buyurtmalar yo'q.", reply_markup=orders_keyboard([]))
        return
    await message.answer("Oxirgi buyurtmalar:", reply_markup=orders_keyboard(orders))


async def send_orders_export(message: Message) -> None:
    data = export_orders_csv_bytes()
    file = BufferedInputFile(data, filename=f"zettacode_orders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    await message.answer_document(file, caption="Buyurtmalar CSV export fayli.")


async def send_database_backup(message: Message) -> None:
    source = db_path()
    if not os.path.exists(source):
        await message.answer("Database fayli topilmadi.")
        return

    os.makedirs("backups", exist_ok=True)
    backup_name = f"orders_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join("backups", backup_name)
    shutil.copy2(source, backup_path)
    with open(backup_path, "rb") as file_obj:
        data = file_obj.read()
    await message.answer_document(
        BufferedInputFile(data, filename=backup_name),
        caption=f"Database backup yaratildi: {backup_name}",
    )


async def broadcast_to_users(bot: Bot, admin_message: Message, text: str) -> None:
    sent = 0
    failed = 0
    for user_id in all_user_ids():
        if is_admin_user(user_id) or is_blocked_user(user_id):
            continue
        try:
            await bot.send_message(user_id, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await admin_message.answer(f"Broadcast yakunlandi.\nYuborildi: {sent}\nXato: {failed}")


def command_args(message: Message) -> str:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def send_long_message(message: Message, text: str) -> None:
    chunk_size = 3900
    for index in range(0, len(text), chunk_size):
        await message.answer(text[index : index + chunk_size])


async def notify_admins(
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for admin_id in admin_chat_ids():
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception as exc:
            logging.warning("Adminga xabar yuborilmadi (%s): %s", admin_id, exc)


def pdf_safe_text(text: str) -> str:
    cleaned = normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf_bytes(title: str, lines: list[str]) -> bytes:
    visible_lines = [title, ""] + lines
    content_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
    for line in visible_lines[:55]:
        content_lines.append(f"({pdf_safe_text(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "ignore")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def invoice_lines(order: sqlite3.Row) -> list[str]:
    return [
        f"Invoice: ZettaCode Tech buyurtma #{order['id']}",
        f"Mijoz: {order['full_name']} (@{order['username'] or 'username yoq'})",
        f"Loyiha turi: {projects_from_order(order)}",
        f"CRM bosqich: {PIPELINE_STAGES.get(order['pipeline_stage'], order['pipeline_stage'])}",
        f"Lead score: {order['lead_score'] or '-'}",
        f"Taxminiy muddat: {order['estimated_duration'] or '-'}",
        f"Umumiy taxminiy narx: ${order['estimate']}",
        f"50% predoplata: ${order['prepayment']}",
        "",
        "Tolov sharti:",
        "Loyiha boshlanishi uchun 50% predoplata plastik karta orqali qabul qilinadi.",
        "Loyiha ichidagi tolov funksiyasi faqat naqd tolov sifatida korib chiqiladi.",
        "",
        "Talablar:",
        *(order["requirements"].splitlines()[:18] or ["-"]),
    ]


async def send_invoice_pdf(message: Message, order: sqlite3.Row) -> None:
    data = simple_pdf_bytes(f"ZettaCode Tech Invoice #{order['id']}", invoice_lines(order))
    await message.answer_document(
        BufferedInputFile(data, filename=f"zettacode_invoice_{order['id']}.pdf"),
        caption=f"Buyurtma #{order['id']} uchun invoice PDF.",
    )


def format_tasks_text(order_id: int, include_done: bool = True) -> str:
    tasks = order_tasks(order_id, include_done=include_done)
    if not tasks:
        return f"Buyurtma #{order_id} uchun vazifalar yo'q."
    lines = [f"Buyurtma #{order_id} vazifalari:"]
    for task in tasks:
        status = "bajarildi" if task["done"] else "kutilmoqda"
        lines.append(
            f"#{task['id']} - {task['task']} ({status})"
            + (f" | {task['assignee']}" if task["assignee"] else "")
            + (f" | deadline: {task['deadline']}" if task["deadline"] else "")
        )
    return "\n".join(lines)


async def reminder_loop(bot: Bot) -> None:
    await asyncio.sleep(20)
    while True:
        try:
            after_hours = int(os.getenv("REMINDER_AFTER_HOURS", str(DEFAULT_REMINDER_AFTER_HOURS)))
        except ValueError:
            after_hours = DEFAULT_REMINDER_AFTER_HOURS

        for order in pending_reminder_orders(after_hours):
            status = STATUS_LABELS.get(order["status"], order["status"])
            try:
                await bot.send_message(
                    order["user_id"],
                    f"Eslatma: buyurtmangiz #{order['id']} hali yakunlanmagan.\n"
                    f"Holat: {status}\n"
                    f"50% predoplata: ${order['prepayment']}\n\n"
                    "Savol bo'lsa admin bilan bog'lanishingiz mumkin.",
                    reply_markup=contact_inline_keyboard(),
                )
                update_order_metadata(order["id"], reminded_at=utc_now())
                await notify_admins(
                    bot,
                    f"Eslatma yuborildi: buyurtma #{order['id']}\n"
                    f"Mijoz: {order['full_name']} (@{order['username'] or 'username yoq'})\n"
                    f"Holat: {status}",
                )
            except Exception as exc:
                logging.warning("Reminder yuborilmadi: %s", exc)

        await asyncio.sleep(3600)


def web_admin_url() -> str:
    host = os.getenv("WEB_ADMIN_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_ADMIN_PORT", str(WEB_ADMIN_DEFAULT_PORT)))
    token = os.getenv("WEB_ADMIN_TOKEN", "").strip()
    suffix = f"?token={token}" if token else ""
    return f"http://{host}:{port}/admin{suffix}"


def web_authorized(request: web.Request) -> bool:
    token = os.getenv("WEB_ADMIN_TOKEN", "").strip()
    if not token:
        return request.remote in {"127.0.0.1", "::1", "localhost"}
    return request.query.get("token") == token


def web_layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;background:#f6f7f9;color:#111}"
        "table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ddd;padding:8px;text-align:left}"
        "a{color:#0b66c3}.card{background:white;padding:16px;border:1px solid #ddd;margin:12px 0}</style>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


async def web_app_page(request: web.Request) -> web.StreamResponse:
    if os.path.exists(WEBAPP_HTML_PATH):
        return web.FileResponse(WEBAPP_HTML_PATH)
    return web.Response(text="Web app sahifasi topilmadi", status=404)


async def web_index(request: web.Request) -> web.Response:
    if not web_authorized(request):
        return web.Response(text="Unauthorized", status=401)
    token_param = f"?token={html.escape(request.query.get('token', ''))}" if request.query.get("token") else ""
    rows = latest_orders(limit=50)
    stats = html.escape(format_stats_text()).replace("\n", "<br>")
    table_rows = []
    for order in rows:
        table_rows.append(
            "<tr>"
            f"<td><a href='/admin/order/{order['id']}{token_param}'>#{order['id']}</a></td>"
            f"<td>{html.escape(order['full_name'])}</td>"
            f"<td>{html.escape(STATUS_LABELS.get(order['status'], order['status']))}</td>"
            f"<td>{html.escape(PIPELINE_STAGES.get(order['pipeline_stage'], order['pipeline_stage']))}</td>"
            f"<td>${order['estimate']}</td>"
            f"<td>{html.escape(order['lead_score'] or '-')}</td>"
            "</tr>"
        )
    body = (
        f"<div class='card'>{stats}</div>"
        "<table><thead><tr><th>ID</th><th>Mijoz</th><th>Status</th><th>Pipeline</th><th>Narx</th><th>Lead</th></tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody></table>"
    )
    return web.Response(text=web_layout("ZettaCode Admin", body), content_type="text/html")


async def web_order_detail(request: web.Request) -> web.Response:
    if not web_authorized(request):
        return web.Response(text="Unauthorized", status=401)
    try:
        order_id = int(request.match_info["order_id"])
    except ValueError:
        return web.Response(text="Bad order id", status=400)
    order = get_order(order_id)
    if order is None:
        return web.Response(text="Order not found", status=404)
    detail = html.escape(format_order_detail(order)).replace("\n", "<br>")
    token_param = f"?token={html.escape(request.query.get('token', ''))}" if request.query.get("token") else ""
    body = f"<div class='card'>{detail}</div><p><a href='/admin{token_param}'>Orqaga</a></p>"
    return web.Response(text=web_layout(f"Buyurtma #{order_id}", body), content_type="text/html")


async def start_web_admin() -> web.AppRunner | None:
    railway_port = os.getenv("PORT")
    admin_enabled = os.getenv("WEB_ADMIN_ENABLED", "1").strip() not in {"0", "false", "False", "yoq"}
    # Railway (PORT mavjud) bo'lsa web app sahifasi uchun server doim ishlaydi.
    if not railway_port and not admin_enabled:
        return None
    app = web.Application()
    app.router.add_get("/", web_app_page)
    if admin_enabled:
        app.router.add_get("/admin", web_index)
        app.router.add_get("/admin/order/{order_id}", web_order_detail)
    runner = web.AppRunner(app)
    await runner.setup()
    if railway_port:
        host = "0.0.0.0"
        port = int(railway_port)
    else:
        host = os.getenv("WEB_ADMIN_HOST", "127.0.0.1")
        port = int(os.getenv("WEB_ADMIN_PORT", str(WEB_ADMIN_DEFAULT_PORT)))
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info("Web server ishga tushdi: http://%s:%s/ (web app)", host, port)
    if admin_enabled:
        logging.info("Web admin panel: %s", web_admin_url())
    return runner


async def ask_for_more_requirements(message: Message, session: UserSession, text: str | None = None) -> None:
    session.stage = "collect_requirements"
    await message.answer(
        (
            text
            or (
            "Loyihangiz qanday ishlashi kerakligini yozing. Masalan: foydalanuvchi ro'yxatdan o'tishi, "
            "admin panel, to'lov, katalog, buyurtma, bildirishnoma, integratsiya kabi funksiyalarni sanab bering."
            )
        )
        + "\n\nEslatma: buyurtma qilayotgan loyihangiz ichidagi to'lov funksiyasi faqat naqd to'lov bo'ladi. Click, Payme, Paynet yoki boshqa online to'lov integratsiyalari qo'shilmaydi.",
        reply_markup=requirements_reply_keyboard(),
    )
    if session.requirements:
        await message.answer(
            "Hozirgacha yozilgan talablar saqlandi. Ma'lumot yetarli bo'lsa narx hisoblanadi, yetarli bo'lmasa bot aniqlashtiruvchi savol beradi.",
            reply_markup=requirements_keyboard(has_requirements=True),
        )


async def finalize_estimate(message: Message, user: User, session: UserSession, bot: Bot | None = None) -> None:
    if not session.selected_projects:
        session.stage = "choose_project"
        await message.answer(
            "Avval loyiha turini tanlang.",
            reply_markup=project_keyboard(session.selected_projects),
        )
        return

    if not session.requirements.strip():
        await ask_for_more_requirements(
            message,
            session,
            "Narx chiqarish uchun loyiha talablari kerak. Iltimos, loyiha nima vazifalarni bajarishini yozing.",
        )
        return

    if not session.requirements_validated:
        validation = await validate_requirements_with_ai(session)
        if not validation.enough:
            session.stage = "collect_requirements"
            await message.answer(validation.reply, reply_markup=requirements_reply_keyboard())
            await message.answer(
                "Talablarni to'liqroq yozing. Yetarli bo'lgandan keyingina narx hisoblanadi.",
                reply_markup=requirements_keyboard(has_requirements=False),
            )
            return
        session.requirements_validated = True

    await message.answer("Talablaringiz AI orqali tahlil qilinyapti, iltimos biroz kuting...")
    result = await estimate_with_ai(session)
    original_estimate = result.estimate
    session.estimate = apply_promo_discount(session, result.estimate)
    session.prepayment = session.estimate // 2
    session.ai_summary = result.summary
    session.ai_features = result.features
    session.ai_used = result.ai_used
    session.estimated_duration = estimate_duration_label(session, original_estimate)
    session.lead_score = lead_score_label(session, session.estimate)
    if session.order_id is None:
        session.order_id = create_order(user, session)
    else:
        update_order_price(session.order_id, session.estimate, session.prepayment)
        update_order_metadata(
            session.order_id,
            pipeline_stage="priced",
            lead_score=session.lead_score,
            estimated_duration=session.estimated_duration,
        )
    session.stage = "payment_confirmation"

    ai_label = "AI tahlil" if session.ai_used else "Tahlil"
    promo_text = ""
    if session.promo_discount_percent:
        promo_text = (
            f"Promo kod: {session.promo_code} (-{session.promo_discount_percent}%)\n"
            f"Chegirmadan oldingi narx: ${original_estimate}\n"
        )
    await message.answer(
        f"Tanlangan yo'nalish: {selected_project_titles(session)}\n"
        f"Murakkablik: {complexity_label(session, original_estimate)}\n"
        f"Taxminiy muddat: {session.estimated_duration}\n"
        f"Lead darajasi: {session.lead_score}\n"
        f"{ai_label}: {session.ai_summary}\n\n"
        f"Asosiy bandlar:\n{format_features(session.ai_features)}\n\n"
        f"{promo_text}"
        f"Talablaringiz asosida taxminiy narx: ${session.estimate}\n"
        f"Boshlash uchun 50% predoplata: ${session.prepayment}\n\n"
        "Loyiha boshlanishi uchun kelishilgan summaning yarmi (50% predoplata) "
        "plastik karta orqali qabul qilinadi. To'lov qilishga rozimisiz?",
        reply_markup=payment_keyboard(),
    )
    if bot is not None and not session.is_admin_test:
        await notify_admins(
            bot,
            f"Yangi narx chiqarildi: buyurtma #{session.order_id}\n"
            f"Mijoz: {user.full_name} (@{user.username or 'username yoq'})\n"
            f"Loyiha: {selected_project_titles(session)}\n"
            f"Narx: ${session.estimate}, predoplata: ${session.prepayment}\n"
            f"Muddat: {session.estimated_duration}\n"
            f"Lead: {session.lead_score}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Buyurtmani ko'rish", callback_data=f"panel:order:{session.order_id}")]
                ]
            ),
        )


async def send_payment_details(message: Message, session: UserSession) -> None:
    card_number = os.getenv("CARD_NUMBER", "[Karta raqami]")
    card_holder = os.getenv("CARD_HOLDER", "TOSHMIRZA YUSUPOV")
    session.stage = "awaiting_receipt"
    update_order_status(session.order_id, "awaiting_receipt")
    update_order_metadata(session.order_id, pipeline_stage="prepayment")
    await message.answer(
        f"Karta raqami: {card_number}\n"
        f"Karta egasi: {card_holder}\n\n"
        "To'lov chekini yuborishni unutmang. Iltimos, to'lov chekini (rasmini) shu yerga yuboring."
    )


async def main() -> None:
    load_dotenv(dotenv_path=".env")
    logging.basicConfig(level=logging.INFO)
    init_db()

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan.")

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    security_middleware = SecurityMiddleware()
    dp.message.middleware(security_middleware)
    dp.callback_query.middleware(security_middleware)
    await setup_bot_commands(bot)
    await setup_menu_button(bot)
    web_runner = await start_web_admin()
    reminder_task = asyncio.create_task(reminder_loop(bot))

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if is_admin_user(message.from_user.id):
            await show_admin_panel(message)
            return
        reset_session(message.from_user.id)
        await show_main_menu(message, user_id=message.from_user.id)

    @dp.message(Command("admin"))
    async def admin_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu bo'lim faqat admin uchun.")
            return
        await show_admin_panel(message)

    @dp.message(Command("new"))
    async def new_order_handler(message: Message) -> None:
        if is_admin_user(message.from_user.id):
            await message.answer(
                "Siz adminsiz. Mijoz oqimini sinash uchun admin paneldagi "
                "`Mijoz sifatida test` tugmasidan foydalaning.",
                reply_markup=admin_panel_keyboard(),
            )
            return
        await show_project_menu(message, user_id=message.from_user.id, reset=True)

    @dp.message(Command("prices"))
    async def prices_handler(message: Message) -> None:
        await show_prices(message)

    @dp.message(Command("portfolio"))
    async def portfolio_handler(message: Message) -> None:
        await show_portfolio(message)

    @dp.message(Command("contact"))
    async def contact_handler(message: Message) -> None:
        await show_contact(message)

    @dp.message(Command("status"))
    async def status_handler(message: Message) -> None:
        await show_user_status(message)

    @dp.message(Command("invoice"))
    async def invoice_handler(message: Message) -> None:
        args = command_args(message)
        if is_admin_user(message.from_user.id) and args:
            if not args.isdigit():
                await message.answer("Invoice olish: /invoice BUYURTMA_ID")
                return
            order = get_order(int(args))
        else:
            order = latest_order_for_user(message.from_user.id)
        if order is None:
            await message.answer("Invoice uchun buyurtma topilmadi.")
            return
        await send_invoice_pdf(message, order)

    @dp.message(Command("faq"))
    async def faq_handler(message: Message) -> None:
        await show_faq(message)

    @dp.message(Command("promo"))
    async def promo_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        promo_code = command_args(message)
        if not promo_code:
            await message.answer("Promo kodni shunday yuboring: /promo ZETTA10")
            return
        if not set_session_promo(session, promo_code):
            await message.answer("Bu promo kod topilmadi yoki amal qilmaydi.")
            return
        await message.answer(
            f"Promo kod qabul qilindi: {session.promo_code}\n"
            f"Chegirma: {session.promo_discount_percent}%\n"
            "Chegirma keyingi narx hisoblashda qo'llanadi va minimal narxlardan pastga tushirmaydi."
        )

    @dp.message(Command("help"))
    async def help_handler(message: Message) -> None:
        if is_admin_user(message.from_user.id):
            await message.answer(admin_help_text(), reply_markup=admin_panel_keyboard())
            return
        await message.answer(user_help_text(), reply_markup=welcome_inline_keyboard())

    @dp.message(Command("cancel"))
    async def cancel_handler(message: Message) -> None:
        reset_session(message.from_user.id, is_admin_test=False)
        await message.answer("Joriy buyurtma bekor qilindi.")
        if is_admin_user(message.from_user.id):
            await show_admin_panel(message)
        else:
            await show_main_menu(message, user_id=message.from_user.id)

    @dp.message(Command("orders"))
    async def orders_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        status = command_args(message)
        if status:
            if status not in STATUS_LABELS:
                await message.answer(
                    "Status noto'g'ri. Variantlar: " + ", ".join(STATUS_LABELS.keys())
                )
                return
            orders = latest_orders_by_status(status)
            await message.answer(
                f"{STATUS_LABELS[status]} bo'yicha buyurtmalar:",
                reply_markup=orders_keyboard(orders),
            )
            return
        await show_orders(message)

    @dp.message(Command("stats"))
    async def stats_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(format_stats_text(), reply_markup=admin_panel_keyboard())

    @dp.message(Command("ai"))
    async def ai_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(ai_status_text(), reply_markup=admin_panel_keyboard())

    @dp.message(Command("testorder"))
    async def test_order_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await show_project_menu(
            message,
            user_id=message.from_user.id,
            reset=True,
            is_admin_test=True,
        )

    @dp.message(Command("search"))
    async def search_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        query = command_args(message)
        if not query:
            session = get_session(message.from_user.id)
            session.stage = "admin_search"
            await message.answer("Qidirish uchun buyurtma ID, user ID, username yoki matn yuboring.")
            return
        orders = search_orders(query)
        await message.answer(
            f"Qidiruv natijalari: {query}" if orders else "Hech narsa topilmadi.",
            reply_markup=orders_keyboard(orders),
        )

    @dp.message(Command("note"))
    async def note_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message)
        parts = args.split(maxsplit=1)
        if len(parts) < 2 or not parts[0].isdigit():
            await message.answer("Izoh qo'shish: /note BUYURTMA_ID izoh matni")
            return
        order_id = int(parts[0])
        note = parts[1].strip()
        if not add_order_note(order_id, message.from_user.id, note):
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer(f"Buyurtma #{order_id} uchun izoh saqlandi.")

    @dp.message(Command("draft"))
    async def draft_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("TT draft olish: /draft BUYURTMA_ID")
            return
        order = get_order(int(order_id_text))
        if order is None:
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer("TT draft tayyorlanyapti...")
        await send_long_message(message, await technical_draft_for_order(order))

    @dp.message(Command("stage"))
    async def stage_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit() or args[1] not in PIPELINE_STAGES:
            await message.answer("CRM bosqich: /stage BUYURTMA_ID new|requirements|priced|prepayment|in_progress|done")
            return
        order_id = int(args[0])
        if get_order(order_id) is None:
            await message.answer("Buyurtma topilmadi.")
            return
        update_order_metadata(order_id, pipeline_stage=args[1])
        await message.answer(f"Buyurtma #{order_id} CRM bosqichi: {PIPELINE_STAGES[args[1]]}")

    @dp.message(Command("task"))
    async def task_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await message.answer("Vazifa qo'shish: /task BUYURTMA_ID vazifa matni")
            return
        order_id = int(args[0])
        if not add_order_task(order_id, args[1]):
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer(f"Buyurtma #{order_id} uchun vazifa qo'shildi.")

    @dp.message(Command("tasks"))
    async def tasks_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("Vazifalar: /tasks BUYURTMA_ID")
            return
        await message.answer(format_tasks_text(int(order_id_text), include_done=True))

    @dp.message(Command("done"))
    async def done_task_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        task_id_text = command_args(message)
        if not task_id_text.isdigit():
            await message.answer("Vazifani yopish: /done TASK_ID")
            return
        if not mark_task_done(int(task_id_text)):
            await message.answer("Vazifa topilmadi.")
            return
        await message.answer(f"Vazifa #{task_id_text} bajarildi deb belgilandi.")

    @dp.message(Command("deadline"))
    async def deadline_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await message.answer("Deadline: /deadline BUYURTMA_ID YYYY-MM-DD")
            return
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[1]):
            await message.answer("Deadline formati YYYY-MM-DD bo'lishi kerak.")
            return
        order_id = int(args[0])
        if get_order(order_id) is None:
            await message.answer("Buyurtma topilmadi.")
            return
        update_order_metadata(order_id, deadline=args[1])
        await message.answer(f"Buyurtma #{order_id} deadline: {args[1]}")

    @dp.message(Command("assign"))
    async def assign_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await message.answer("Mas'ul biriktirish: /assign BUYURTMA_ID ism")
            return
        order_id = int(args[0])
        if get_order(order_id) is None:
            await message.answer("Buyurtma topilmadi.")
            return
        update_order_metadata(order_id, assignee=args[1])
        await message.answer(f"Buyurtma #{order_id} mas'ul: {args[1]}")

    @dp.message(Command("web"))
    async def web_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(f"Web admin panel:\n{web_admin_url()}")

    @dp.message(Command("export"))
    async def export_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await send_orders_export(message)

    @dp.message(Command("backup"))
    async def backup_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await send_database_backup(message)

    @dp.message(Command("broadcast"))
    async def broadcast_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        text = command_args(message)
        if not text:
            session = get_session(message.from_user.id)
            session.stage = "admin_broadcast"
            await message.answer("Broadcast xabar matnini yuboring.")
            return
        session = get_session(message.from_user.id)
        session.stage = "admin_broadcast_confirm"
        session.pending_broadcast_text = text
        await message.answer(
            f"Broadcast matni:\n\n{text}\n\nYuborilsinmi?",
            reply_markup=broadcast_confirm_keyboard(),
        )

    @dp.message(Command("block"))
    async def block_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message)
        parts = args.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await message.answer("Bloklash: /block USER_ID sabab")
            return
        user_id = int(parts[0])
        if is_admin_user(user_id):
            await message.answer("Adminni bloklab bo'lmaydi.")
            return
        block_user(user_id, parts[1] if len(parts) == 2 else "")
        await message.answer(f"User {user_id} bloklandi.")

    @dp.message(Command("unblock"))
    async def unblock_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        user_id_text = command_args(message)
        if not user_id_text.isdigit():
            await message.answer("Blokdan chiqarish: /unblock USER_ID")
            return
        unblock_user(int(user_id_text))
        await message.answer(f"User {user_id_text} blokdan chiqarildi.")

    @dp.callback_query(F.data.startswith("menu:"))
    async def menu_callback(callback: CallbackQuery) -> None:
        action = callback.data.split(":", 1)[1]

        if action in ("start_order", "choose_project"):
            if is_admin_user(callback.from_user.id):
                await callback.message.answer(
                    "Siz adminsiz. Mijoz oqimini sinash uchun admin paneldagi "
                    "`Mijoz sifatida test` tugmasidan foydalaning.",
                    reply_markup=admin_panel_keyboard(),
                )
                await callback.answer()
                return
            await show_project_menu(callback.message, user_id=callback.from_user.id, reset=True)
            await callback.answer()
            return

        if action == "prices":
            await show_prices(callback.message)
            await callback.answer()
            return

        if action == "status":
            await show_user_status(callback.message, user_id=callback.from_user.id)
            await callback.answer()
            return

        if action == "faq":
            await show_faq(callback.message)
            await callback.answer()
            return

        if action == "home":
            if is_admin_user(callback.from_user.id):
                await show_admin_panel(callback.message)
            else:
                await show_main_menu(callback.message, user_id=callback.from_user.id)
            await callback.answer()
            return

        await callback.answer()

    @dp.callback_query(F.data.startswith("portfolio:"))
    async def portfolio_callback(callback: CallbackQuery) -> None:
        category = callback.data.split(":", 1)[1]
        await safe_edit_or_answer(
            callback,
            portfolio_text(category),
            reply_markup=portfolio_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("quick_project:"))
    async def quick_project_callback(callback: CallbackQuery) -> None:
        current_session = get_session(callback.from_user.id)
        if is_admin_user(callback.from_user.id) and not current_session.is_admin_test:
            await show_admin_panel(callback.message)
            await callback.answer()
            return

        project_key = normalize_project_key(callback.data.split(":", 1)[1])
        if project_key not in PROJECT_PRICES:
            await callback.answer("Loyiha turi topilmadi.", show_alert=True)
            return

        session = reset_session(
            callback.from_user.id,
            is_admin_test=is_admin_user(callback.from_user.id),
        )
        session.selected_projects.add(project_key)
        await ask_for_more_requirements(
            callback.message,
            session,
            f"{PROJECT_PRICES[project_key][0]} tanlandi. Endi loyiha nima vazifalarni bajarishini batafsil yozing.",
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("panel:"))
    async def admin_panel_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(callback.from_user.id):
            await callback.answer("Bu bo'lim faqat admin uchun.", show_alert=True)
            return

        parts = callback.data.split(":")
        action = parts[1] if len(parts) > 1 else "home"

        if action == "home":
            await safe_edit_or_answer(
                callback,
                "ZettaCode Tech admin panel.",
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "test_order":
            await show_project_menu(
                callback.message,
                user_id=callback.from_user.id,
                reset=True,
                is_admin_test=True,
            )
            await callback.answer("Test buyurtma rejimi ochildi.")
            return

        if action == "orders":
            status_filter = parts[2] if len(parts) > 2 else ""
            orders = latest_orders_by_status(status_filter) if status_filter else latest_orders()
            title = (
                f"{STATUS_LABELS.get(status_filter, status_filter)} bo'yicha buyurtmalar:"
                if status_filter
                else "Oxirgi buyurtmalar:"
            )
            if not orders:
                await safe_edit_or_answer(
                    callback,
                    "Bu filter bo'yicha buyurtmalar yo'q." if status_filter else "Hozircha buyurtmalar yo'q.",
                    reply_markup=orders_keyboard([]),
                )
            else:
                await safe_edit_or_answer(
                    callback,
                    title,
                    reply_markup=orders_keyboard(orders),
                )
            await callback.answer()
            return

        if action == "pipeline" and len(parts) == 3:
            stage = parts[2]
            if stage not in PIPELINE_STAGES:
                await callback.answer("Pipeline bosqichi noto'g'ri.", show_alert=True)
                return
            orders = latest_orders_by_pipeline(stage)
            await safe_edit_or_answer(
                callback,
                f"{PIPELINE_STAGES[stage]} bosqichidagi buyurtmalar:" if orders else "Bu pipeline bosqichida buyurtma yo'q.",
                reply_markup=orders_keyboard(orders),
            )
            await callback.answer()
            return

        if action == "order" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return

            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return

            await safe_edit_or_answer(
                callback,
                format_order_detail(order),
                reply_markup=order_detail_keyboard(order),
            )
            await callback.answer()
            return

        if action == "stage" and len(parts) == 4:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            stage = parts[3]
            if stage not in PIPELINE_STAGES:
                await callback.answer("Pipeline bosqichi noto'g'ri.", show_alert=True)
                return
            if get_order(order_id) is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            update_order_metadata(order_id, pipeline_stage=stage)
            order = get_order(order_id)
            await safe_edit_or_answer(
                callback,
                format_order_detail(order),
                reply_markup=order_detail_keyboard(order),
            )
            await callback.answer(f"CRM bosqich: {PIPELINE_STAGES[stage]}")
            return

        if action == "stats":
            await safe_edit_or_answer(
                callback,
                format_stats_text(),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "invoice" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await send_invoice_pdf(callback.message, order)
            await callback.answer("Invoice yuborildi.")
            return

        if action == "task" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            if get_order(order_id) is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            session = get_session(callback.from_user.id)
            session.stage = "admin_task"
            session.pending_task_order_id = order_id
            await callback.message.answer(f"Buyurtma #{order_id} uchun vazifa matnini yuboring.")
            await callback.answer()
            return

        if action == "export":
            await send_orders_export(callback.message)
            await callback.answer("CSV export yuborildi.")
            return

        if action == "backup":
            await send_database_backup(callback.message)
            await callback.answer("Backup yuborildi.")
            return

        if action == "broadcast":
            session = get_session(callback.from_user.id)
            session.stage = "admin_broadcast"
            await callback.message.answer("Broadcast xabar matnini yuboring.")
            await callback.answer()
            return

        if action == "confirm_broadcast":
            session = get_session(callback.from_user.id)
            if not session.pending_broadcast_text:
                await callback.answer("Broadcast matni topilmadi.", show_alert=True)
                return
            text = session.pending_broadcast_text
            session.pending_broadcast_text = ""
            session.stage = "choose_project"
            await callback.message.answer("Broadcast yuborilyapti...")
            await broadcast_to_users(bot, callback.message, text)
            await callback.answer()
            return

        if action == "cancel_broadcast":
            session = get_session(callback.from_user.id)
            session.pending_broadcast_text = ""
            session.stage = "choose_project"
            await callback.message.answer("Broadcast bekor qilindi.", reply_markup=admin_panel_keyboard())
            await callback.answer()
            return

        if action == "draft" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer("TT draft tayyorlanyapti...")
            await send_long_message(callback.message, await technical_draft_for_order(order))
            await callback.answer()
            return

        if action == "note" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            if get_order(order_id) is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            session = get_session(callback.from_user.id)
            session.stage = "admin_note"
            session.pending_note_order_id = order_id
            await callback.message.answer(f"Buyurtma #{order_id} uchun izoh matnini yuboring.")
            await callback.answer()
            return

        if action == "ai_status":
            await safe_edit_or_answer(
                callback,
                ai_status_text(),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        await callback.answer()

    @dp.callback_query(F.data.startswith("project:"))
    async def project_callback(callback: CallbackQuery) -> None:
        session = get_session(callback.from_user.id)
        if is_admin_user(callback.from_user.id) and not session.is_admin_test:
            await show_admin_panel(callback.message)
            await callback.answer()
            return

        action = callback.data.split(":", 1)[1]

        if action == "confirm":
            if not session.selected_projects:
                await callback.answer("Kamida bitta yo'nalishni tanlang.", show_alert=True)
                return

            await ask_for_more_requirements(
                callback.message,
                session,
                "Loyihangiz to'liq qanday ishlashi va nima vazifalarni bajarishi kerakligini batafsil yozib bering.",
            )
            await callback.answer()
            return

        project_key = normalize_project_key(action)
        if project_key in PROJECT_PRICES:
            if project_key in session.selected_projects:
                session.selected_projects.remove(project_key)
            else:
                session.selected_projects.add(project_key)

            await callback.message.edit_reply_markup(
                reply_markup=project_keyboard(session.selected_projects)
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("requirements:"))
    async def requirements_callback(callback: CallbackQuery) -> None:
        session = get_session(callback.from_user.id)
        action = callback.data.split(":", 1)[1]

        if action == "estimate":
            await finalize_estimate(callback.message, callback.from_user, session, bot=bot)
            await callback.answer()
            return

        if action == "more":
            await ask_for_more_requirements(
                callback.message,
                session,
                "Qo'shimcha talablaringizni yozing. Men faqat loyiha funksiyalari bo'yicha ma'lumot qabul qilaman.",
            )
            await callback.answer()
            return

        if action == "edit":
            session.requirements = ""
            session.requirements_validated = False
            session.order_id = None
            session.estimate = 0
            session.prepayment = 0
            await ask_for_more_requirements(
                callback.message,
                session,
                "Talablarni qayta yozing. Loyiha nima qilishi kerakligini batafsil yuboring.",
            )
            await callback.answer("Talablarni qayta yozish rejimi ochildi.")
            return

        if action == "change_project":
            session.selected_projects.clear()
            await show_project_menu(callback.message, user_id=callback.from_user.id)
            await callback.answer()
            return

        if action == "cancel":
            reset_session(callback.from_user.id, is_admin_test=is_admin_user(callback.from_user.id))
            if is_admin_user(callback.from_user.id):
                await show_admin_panel(callback.message)
            else:
                await show_main_menu(callback.message, user_id=callback.from_user.id)
            await callback.answer("Buyurtma bekor qilindi.")
            return

        await callback.answer()

    @dp.message(F.photo)
    async def photo_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        if session.stage == "checking":
            await message.answer(
                "To'lov chekingiz adminga yuborilgan. Iltimos, admin javobini kuting."
            )
            return

        if session.stage != "awaiting_receipt":
            if is_admin_user(message.from_user.id):
                await show_admin_panel(message)
                return
            await message.answer(
                "Buyurtma boshlash uchun avval loyiha yo'nalishini tanlang.",
                reply_markup=project_keyboard(session.selected_projects),
            )
            return

        receipt_file_id = message.photo[-1].file_id
        update_order_status(session.order_id, "checking", receipt_file_id=receipt_file_id)
        await message.answer(
            "To'lov chekingiz qabul qilindi, hozir adminimiz buni tekshirmoqda. "
            "Iltimos, biroz kuting..."
        )

        admin_ids = admin_chat_ids()
        if not admin_ids:
            logging.warning("Admin ID sozlanmagan, chek adminga yuborilmadi.")
            return

        user = message.from_user
        username = f"@{user.username}" if user.username else "username yo'q"
        order_label = f"Buyurtma #{session.order_id}" if session.order_id else "Yangi buyurtma"
        test_label = "TEST BUYURTMA\n\n" if session.is_admin_test else ""
        admin_text = (
            f"{test_label}{order_label}: yangi to'lov cheki keldi.\n\n"
            f"Mijoz ID: {user.id}\n"
            f"Mijoz: {user.full_name} ({username})\n"
            f"Loyiha turi: {selected_project_titles(session)}\n"
            f"Taxminiy narx: ${session.estimate}\n"
            f"50% predoplata: ${session.prepayment}\n\n"
            f"Tahlil: {session.ai_summary}\n\n"
            f"Talablar:\n{session.requirements}"
        )

        for admin_id in admin_ids:
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_review_keyboard(user.id, session.order_id),
            )
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

    @dp.callback_query(F.data.startswith("payment:"))
    async def payment_callback(callback: CallbackQuery) -> None:
        session = get_session(callback.from_user.id)
        action = callback.data.split(":", 1)[1]

        if session.stage != "payment_confirmation":
            await callback.answer()
            return

        if action == "no":
            update_order_status(session.order_id, "admin_contact")
            update_order_metadata(session.order_id, pipeline_stage="requirements")
            session.stage = "admin_contact"
            await callback.message.answer(admin_contact_text())
            await notify_admins(
                bot,
                f"Mijoz predoplatani oldindan qilishni istamadi.\n"
                f"Buyurtma #{session.order_id}\n"
                f"Mijoz: {callback.from_user.full_name} (@{callback.from_user.username or 'username yoq'})",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Buyurtmani ko'rish", callback_data=f"panel:order:{session.order_id}")]
                    ]
                ),
            )
            await callback.answer()
            return

        if action == "edit":
            update_order_status(session.order_id, "rejected")
            session.requirements = ""
            session.requirements_validated = False
            session.order_id = None
            session.estimate = 0
            session.prepayment = 0
            await ask_for_more_requirements(
                callback.message,
                session,
                "Talablarni qayta yozing. Loyiha nima qilishi kerakligini batafsil yuboring.",
            )
            await callback.answer("Tahrirlash rejimi ochildi.")
            return

        if action == "invoice":
            order = get_order(session.order_id) if session.order_id is not None else None
            if order is None:
                await callback.answer("Invoice uchun buyurtma topilmadi.", show_alert=True)
                return
            await send_invoice_pdf(callback.message, order)
            await callback.answer("Invoice yuborildi.")
            return

        await send_payment_details(callback.message, session)
        await callback.answer()

    @dp.callback_query(F.data.startswith("admin:"))
    async def admin_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(callback.from_user.id):
            await callback.answer("Bu tugma faqat admin uchun.", show_alert=True)
            return

        parts = callback.data.split(":")
        if len(parts) not in (3, 4):
            await callback.answer()
            return

        action = parts[1]
        try:
            user_id = int(parts[2])
            order_id = int(parts[3]) if len(parts) == 4 and parts[3] != "None" else None
        except ValueError:
            await callback.answer("Mijoz yoki buyurtma ID noto'g'ri.", show_alert=True)
            return

        session = sessions.get(user_id)

        if action == "paid":
            update_order_status(order_id, "paid")
            update_order_metadata(order_id, pipeline_stage="in_progress")
            if session and session.order_id == order_id:
                session.stage = "completed"
            await bot.send_message(
                user_id,
                "To'lovingiz muvaffaqiyatli qabul qilindi! Barcha ma'lumotlar adminga yuborildi. "
                "Adminimiz siz bilan tez orada aloqaga chiqadi, iltimos javobni kuting.",
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.answer("Mijozga tasdiq xabari yuborildi.")
            return

        if action == "not_paid":
            update_order_status(order_id, "rejected")
            update_order_metadata(order_id, pipeline_stage="priced")
            if session and session.order_id == order_id:
                session.stage = "payment_confirmation"
            await bot.send_message(
                user_id,
                "Uzur, siz bizga soxta chek yubordingiz yoki bizning kartamizga to'lov amalga oshirilmadi. "
                "Iltimos, to'lovni qaytadan tekshirib ko'ring.",
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.answer("Mijozga rad javobi yuborildi.")
            return

        await callback.answer()

    @dp.message()
    async def text_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        text = (message.text or "").strip()

        if not text:
            await message.answer("Iltimos, xabarni matn ko'rinishida yuboring.")
            return

        if is_admin_user(message.from_user.id) and session.stage == "admin_note":
            if session.pending_note_order_id is None:
                session.stage = "choose_project"
                await message.answer("Izoh qo'shish uchun buyurtma ID topilmadi.", reply_markup=admin_panel_keyboard())
                return
            order_id = session.pending_note_order_id
            if not add_order_note(order_id, message.from_user.id, text):
                await message.answer("Buyurtma topilmadi.", reply_markup=admin_panel_keyboard())
            else:
                await message.answer(f"Buyurtma #{order_id} uchun izoh saqlandi.", reply_markup=admin_panel_keyboard())
            session.pending_note_order_id = None
            session.stage = "choose_project"
            return

        if is_admin_user(message.from_user.id) and session.stage == "admin_task":
            if session.pending_task_order_id is None:
                session.stage = "choose_project"
                await message.answer("Task qo'shish uchun buyurtma ID topilmadi.", reply_markup=admin_panel_keyboard())
                return
            order_id = session.pending_task_order_id
            if not add_order_task(order_id, text):
                await message.answer("Buyurtma topilmadi.", reply_markup=admin_panel_keyboard())
            else:
                await message.answer(f"Buyurtma #{order_id} uchun task saqlandi.", reply_markup=admin_panel_keyboard())
            session.pending_task_order_id = None
            session.stage = "choose_project"
            return

        if is_admin_user(message.from_user.id) and session.stage == "admin_search":
            orders = search_orders(text)
            await message.answer(
                f"Qidiruv natijalari: {text}" if orders else "Hech narsa topilmadi.",
                reply_markup=orders_keyboard(orders),
            )
            session.stage = "choose_project"
            return

        if is_admin_user(message.from_user.id) and session.stage == "admin_broadcast":
            session.pending_broadcast_text = text
            session.stage = "admin_broadcast_confirm"
            await message.answer(
                f"Broadcast matni:\n\n{text}\n\nYuborilsinmi?",
                reply_markup=broadcast_confirm_keyboard(),
            )
            return

        if text == MAIN_MENU_TEXT:
            reset_session(message.from_user.id, is_admin_test=False)
            if is_admin_user(message.from_user.id):
                await show_admin_panel(message)
            else:
                await show_main_menu(message, user_id=message.from_user.id)
            return

        if text == PRICE_TEXT:
            await show_prices(message)
            return

        if text == CANCEL_TEXT:
            reset_session(message.from_user.id, is_admin_test=False)
            await message.answer("Joriy buyurtma bekor qilindi.")
            if is_admin_user(message.from_user.id):
                await show_admin_panel(message)
            else:
                await show_main_menu(message, user_id=message.from_user.id)
            return

        if text == ADMIN_PANEL_TEXT:
            if is_admin_user(message.from_user.id):
                reset_session(message.from_user.id, is_admin_test=False)
                await show_admin_panel(message)
            else:
                await message.answer("Bu bo'lim faqat admin uchun.")
            return

        if text == START_ORDER_TEXT:
            if is_admin_user(message.from_user.id) and not session.is_admin_test:
                await message.answer(
                    "Siz adminsiz. Mijoz oqimini sinash uchun admin paneldagi "
                    "`Mijoz sifatida test` tugmasidan foydalaning.",
                    reply_markup=admin_panel_keyboard(),
                )
                return
            await show_project_menu(message, user_id=message.from_user.id, reset=True)
            return

        if is_admin_user(message.from_user.id) and not session.is_admin_test:
            await show_admin_panel(message)
            return

        if text == CALCULATE_TEXT:
            await finalize_estimate(message, message.from_user, session, bot=bot)
            return

        normalized_text = text.lower().replace("'", "").replace("`", "")
        if session.stage == "payment_confirmation":
            if normalized_text in ("ha", "xa", "yes", "roziman"):
                await send_payment_details(message, session)
                return
            if is_prepayment_refusal(normalized_text):
                update_order_status(session.order_id, "admin_contact")
                update_order_metadata(session.order_id, pipeline_stage="requirements")
                session.stage = "admin_contact"
                await message.answer(admin_contact_text())
                await notify_admins(
                    bot,
                    f"Mijoz predoplata bo'yicha admin bilan kelishmoqchi.\n"
                    f"Buyurtma #{session.order_id}\n"
                    f"Mijoz: {message.from_user.full_name} (@{message.from_user.username or 'username yoq'})",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="Buyurtmani ko'rish", callback_data=f"panel:order:{session.order_id}")]
                        ]
                    ),
                )
                return
            await message.answer(
                "To'lov qilishga rozimisiz?",
                reply_markup=payment_keyboard(),
            )
            return

        if session.stage == "awaiting_receipt":
            await message.answer("Iltimos, to'lov chekini rasm holatida yuboring.")
            return

        if session.stage in ("choose_project", "collect_requirements"):
            await message.answer("Xabaringiz AI orqali tekshirilyapti...")
            result = await guide_conversation_with_ai(session, text)

            if not result.relevant:
                session.off_topic_count += 1
                await message.answer(
                    result.reply,
                    reply_markup=requirements_keyboard(bool(session.requirements))
                    if session.stage == "collect_requirements"
                    else welcome_inline_keyboard(),
                )
                return

            for project_key in result.suggested_projects:
                session.selected_projects.add(project_key)

            if not session.selected_projects:
                await message.answer(
                    result.reply or "Qaysi loyiha turini tanlaysiz?",
                    reply_markup=project_keyboard(session.selected_projects),
                )
                return

            captured_requirements = result.captured_requirements or text
            add_requirements_text(session, captured_requirements)
            if has_online_payment_request(text):
                await message.answer(
                    "Loyihangiz ichidagi to'lov funksiyasi uchun Click, Payme, Paynet, karta va boshqa online to'lov integratsiyalariga ruxsat berilmaydi. "
                    "Bu funksiya faqat naqd to'lov siyosati bilan qabul qilinadi."
                )

            validation = await validate_requirements_with_ai(session)
            if not validation.enough:
                session.requirements_validated = False
                session.asked_questions += 1
                await message.answer(validation.reply, reply_markup=requirements_reply_keyboard())
                await message.answer(
                    f"Tanlangan yo'nalish: {selected_project_titles(session)}\n"
                    "Talablar hali yetarli emas. Yuqoridagi savollarga javob yozing.",
                    reply_markup=requirements_keyboard(has_requirements=False),
                )
                return

            session.requirements_validated = True
            await finalize_estimate(message, message.from_user, session, bot=bot)
            return

        await show_main_menu(message, user_id=message.from_user.id)

    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        if web_runner is not None:
            await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

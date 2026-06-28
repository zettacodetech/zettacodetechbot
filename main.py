import asyncio
import csv
import hashlib
import html
import hmac
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Set
from unicodedata import normalize
from urllib.parse import parse_qsl

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
    "delivered": "Loyiha topshirildi",
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
CALCULATOR_TEXT = "Kalkulyator"
RATE_LIMIT_WINDOW_SECONDS = 8
RATE_LIMIT_MAX_MESSAGES = 8
DEFAULT_REMINDER_AFTER_HOURS = 3
WEB_ADMIN_DEFAULT_PORT = 8088
APP_ROOT = Path(__file__).resolve().parent
WEBAPP_ROOT = APP_ROOT / "webapp"
WEBAPP_HTML_PATH = WEBAPP_ROOT / "index.html"
BOT_STARTED_AT = datetime.now(timezone.utc)
PROMO_CODES = {
    "ZETTA10": 10,
    "START5": 5,
}
CALCULATOR_QUESTIONS = [
    "Loyiha maqsadi nima: savdo, buyurtma, CRM, portfolio yoki ichki avtomatlashtirishmi?",
    "Foydalanuvchi nimalar qiladi? Masalan: ro'yxatdan o'tadi, katalog ko'radi, buyurtma beradi.",
    "Admin nimalar qiladi? Masalan: buyurtmalarni ko'radi, status o'zgartiradi, hisobot oladi.",
    "Qanday ma'lumotlar saqlanadi? Masalan: mijoz, mahsulot, buyurtma, to'lov, ombor.",
    "Bildirishnoma, SMS, API, fayl yuklash yoki boshqa integratsiya kerakmi?",
    "Loyiha ichidagi to'lov faqat naqd bo'ladi. Naqd to'lov jarayoni qanday ishlaydi?",
]
SALES_OBJECTION_KEYWORDS = {
    "expensive": ("qimmat", "arzon", "tushirib", "chegirma", "skidka", "narx baland"),
    "later": ("keyin", "ertaga", "o'ylab", "uylab", "kut", "hozir emas", "hali"),
    "prepayment": ("oldindan", "predoplata", "avans", "yarmini", "to'lamayman", "tolamayman"),
    "deadline": ("muddat", "qachon", "necha kun", "tez", "shoshilinch"),
}
SALES_OBJECTION_REPLIES = {
    "expensive": (
        "Narx loyiha funksiyalari va mas'uliyatidan kelib chiqib qo'yildi. Bu summaga faqat kod emas, "
        "talablarni tartibga solish, tizimni sozlash, test qilish va topshirilgandan keyingi boshlang'ich qo'llab-quvvatlash ham kiradi.\n\n"
        "Agar byudjetni kamaytirish kerak bo'lsa, funksiyalarni MVP ko'rinishida qisqartirib, qayta baholab beraman."
    ),
    "later": (
        "Tushunarli. Loyiha bo'yicha joy band qilinishi va ish rejasiga kiritilishi uchun predoplata kerak bo'ladi. "
        "Hozir boshlashga tayyor bo'lmasangiz, admin bilan kelishib vaqtni aniqlashtirishingiz mumkin."
    ),
    "prepayment": (
        "ZettaCode Tech ishni boshlashi uchun 50% predoplata talab qilinadi. Bu loyiha vaqtini band qilish va ishni rasmiy boshlash uchun kerak.\n\n"
        "Agar oldindan to'lov bo'yicha kelishmoqchi bo'lsangiz, admin bilan gaplashishingiz mumkin."
    ),
    "deadline": (
        "Taxminiy muddat talablar murakkabligiga qarab belgilanadi. Shoshilinch loyiha bo'lsa, funksiyalarni MVP qilib qisqartirish yoki "
        "admin bilan ustuvorlikni kelishish mumkin."
    ),
}
ADMIN_REPLY_TEMPLATES = {
    "price": "Narx loyiha murakkabligi, admin panel, test va boshlang'ich qo'llab-quvvatlashni hisobga olib berilgan.",
    "receipt": "Chekingiz admin tomonidan tekshirilmoqda. Iltimos, biroz kuting.",
    "deadline": "Muddat loyiha funksiyalari tasdiqlangandan keyin aniq belgilanadi. Hozirgi taxminiy muddat buyurtma tafsilotida ko'rsatilgan.",
    "requirements": "Aniq narx uchun loyiha maqsadi, user/admin amallari va asosiy funksiyalarni batafsil yozib bering.",
    "prepayment": "Ish boshlanishi uchun kelishilgan summaning 50% qismi plastik karta orqali predoplata qilinadi.",
}
TIMELINE_STEPS = [
    ("requirements", "Talab olindi"),
    ("priced", "Narx berildi"),
    ("prepayment", "Predoplata jarayoni"),
    ("in_progress", "Ish jarayoni"),
    ("done", "Topshirildi"),
]


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
    calculator_mode: bool = False


sessions: Dict[int, UserSession] = {}
rate_limits: Dict[int, list[float]] = {}


REDIS_URL = os.getenv("REDIS_URL", "").strip()
SESSION_TTL_SECONDS = 86400
_redis = None
_sentry = None
if REDIS_URL:
    try:
        import redis as _redis_lib  # noqa: E402

        _redis = _redis_lib.from_url(REDIS_URL, decode_responses=True)
        _redis.ping()
        logging.info("Redis ulandi: sessiya va rate-limit Redis'da saqlanadi")
    except Exception as _redis_exc:  # noqa: BLE001
        logging.warning("Redis ulanmadi, in-memory ishlatiladi: %s", _redis_exc)
        _redis = None


def _session_to_json(session: "UserSession") -> str:
    data = asdict(session)
    data["selected_projects"] = list(session.selected_projects)
    return json.dumps(data, ensure_ascii=False)


def _session_from_json(raw: str) -> "UserSession":
    data = json.loads(raw)
    data["selected_projects"] = set(data.get("selected_projects", []))
    return UserSession(**data)


def save_session(user_id: int) -> None:
    """Sessiyani Redis'ga saqlaydi (Redis bo'lmasa hech narsa qilmaydi)."""
    if _redis is None or user_id not in sessions:
        return
    try:
        _redis.set(
            f"session:{user_id}",
            _session_to_json(sessions[user_id]),
            ex=SESSION_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logging.warning("Redis sessiya saqlanmadi: %s", exc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> str:
    return os.getenv("DB_PATH", "orders.db")


# ============================ i18n (UZ/RU/EN) ============================
SUPPORTED_LANGUAGES = {"uz": "O'zbekcha 🇺🇿", "ru": "Русский 🇷🇺", "en": "English 🇬🇧"}
DEFAULT_LANGUAGE = "uz"
_lang_cache: dict[int, str] = {}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "choose_language": {
        "uz": "Tilni tanlang:",
        "ru": "Выберите язык:",
        "en": "Choose your language:",
    },
    "language_set": {
        "uz": "✅ Til o'zbek tiliga o'rnatildi.",
        "ru": "✅ Язык установлен на русский.",
        "en": "✅ Language set to English.",
    },
    "welcome": {
        "uz": (
            "Assalomu alaykum! ZettaCode Tech savdo botiga xush kelibsiz.\n\n"
            "Biz Telegram bot, veb-sayt, mobil ilova va CRM tizimlarini ishlab chiqamiz. "
            "Loyihangiz uchun taxminiy narx olish uchun «Buyurtma berish» tugmasini bosing."
        ),
        "ru": (
            "Здравствуйте! Добро пожаловать в бот ZettaCode Tech.\n\n"
            "Мы разрабатываем Telegram-боты, веб-сайты, мобильные приложения и CRM-системы. "
            "Чтобы получить примерную стоимость проекта, нажмите «Заказать»."
        ),
        "en": (
            "Hello! Welcome to the ZettaCode Tech bot.\n\n"
            "We build Telegram bots, websites, mobile apps and CRM systems. "
            "Press «Order» to get an estimate for your project."
        ),
    },
    "choose_action": {
        "uz": "Qaysi amalni bajaramiz?",
        "ru": "Что хотите сделать?",
        "en": "What would you like to do?",
    },
    "btn_order": {"uz": "Buyurtma berish", "ru": "Заказать", "en": "Order"},
    "btn_prices": {"uz": "Narxlar", "ru": "Цены", "en": "Prices"},
    "btn_portfolio": {"uz": "Portfolio", "ru": "Портфолио", "en": "Portfolio"},
    "btn_contact": {"uz": "Admin bilan aloqa", "ru": "Связь с админом", "en": "Contact admin"},
    "help": {
        "uz": "Buyruqlar: /start /new /prices /portfolio /contact /status /language /help",
        "ru": "Команды: /start /new /prices /portfolio /contact /status /language /help",
        "en": "Commands: /start /new /prices /portfolio /contact /status /language /help",
    },
}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """Tarjima qaytaradi. Topilmasa: tanlangan til → o'zbekcha → kalitning o'zi (hech qachon xato bermaydi)."""
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:  # noqa: BLE001
            pass
    return text


def get_user_language(user_id: int) -> str:
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    lang = DEFAULT_LANGUAGE
    try:
        with db_connect() as connection:
            row = connection.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row and row["language"] in SUPPORTED_LANGUAGES:
            lang = row["language"]
    except Exception:  # noqa: BLE001
        pass
    _lang_cache[user_id] = lang
    return lang


def is_language_chosen(user_id: int) -> bool:
    """Foydalanuvchi tilni tanlaganmi. Xato bo'lsa True (oqimni to'smaymiz)."""
    try:
        with db_connect() as connection:
            row = connection.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return bool(row and row["language"] in SUPPORTED_LANGUAGES)
    except Exception:  # noqa: BLE001
        return True


def set_user_language(user_id: int, lang: str) -> None:
    if lang not in SUPPORTED_LANGUAGES:
        return
    try:
        with db_connect() as connection:
            connection.execute(
                "UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id)
            )
    except Exception as exc:  # noqa: BLE001
        logging.warning("Til saqlanmadi: %s", exc)
    _lang_cache[user_id] = lang


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"setlang:{code}")]
            for code, title in SUPPORTED_LANGUAGES.items()
        ]
    )


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg  # noqa: E402


class _HybridRow(dict):
    """sqlite3.Row kabi — ustun nomi ham, butun indeks ham ishlaydi."""

    __slots__ = ("_values",)

    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _hybrid_row_factory(cursor):
    columns = [c.name for c in cursor.description] if cursor.description else []

    def make(values):
        return _HybridRow(columns, values)

    return make


def _to_pg_sql(sql: str) -> str:
    """SQLite SQL'ini PostgreSQL'ga moslaydi (DDL turlari + ? placeholder)."""
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql)
    sql = sql.replace("?", "%s")
    return sql


class _PgConnection:
    """sqlite3.Connection API'sini taqlid qiladi: execute/fetch/commit + with-context."""

    def __init__(self, url: str):
        self._conn = psycopg.connect(url, row_factory=_hybrid_row_factory)

    def execute(self, sql: str, params: Iterable = ()):
        cursor = self._conn.cursor()
        cursor.execute(_to_pg_sql(sql), tuple(params) if params else None)
        return cursor

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def db_connect():
    if IS_POSTGRES:
        return _PgConnection(DATABASE_URL)
    connection = sqlite3.connect(db_path())
    connection.row_factory = sqlite3.Row
    return connection


def db_insert(connection, sql: str, params: Iterable = ()) -> int:
    """INSERT bajarib yangi qator id'sini qaytaradi (sqlite lastrowid / pg RETURNING id)."""
    if IS_POSTGRES:
        cursor = connection.execute(sql + " RETURNING id", params)
        return int(cursor.fetchone()[0])
    cursor = connection.execute(sql, params)
    return int(cursor.lastrowid)


def ensure_column(connection, table: str, column: str, definition: str) -> None:
    if IS_POSTGRES:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}"
        )
        return
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
        ensure_column(connection, "users", "language", "TEXT NOT NULL DEFAULT ''")
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
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                admin_reply TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reminded_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_user_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL UNIQUE,
                code TEXT NOT NULL,
                rewarded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_roles (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                updated_by INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL DEFAULT 0,
                comment TEXT NOT NULL DEFAULT '',
                portfolio_permission INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def track_web_user(user_id: int, full_name: str, username: str = "") -> None:
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
            (user_id, full_name, username, now, now),
        )


def create_order(user: User, session: UserSession) -> int:
    username = user.username or ""
    now = utc_now()
    with db_connect() as connection:
        return db_insert(
            connection,
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


def create_web_order(
    user_id: int,
    full_name: str,
    username: str,
    project_key: str,
    requirements: str,
    analysis: EstimateResult | None = None,
) -> sqlite3.Row:
    project_key = normalize_project_key(project_key)
    if project_key not in PROJECT_PRICES:
        raise ValueError("Loyiha turi noto'g'ri.")

    clean_requirements = normalize_payment_policy_text(requirements.strip())
    session = UserSession(
        stage="payment_confirmation",
        selected_projects={project_key},
        requirements=clean_requirements,
        requirements_validated=True,
    )
    validation = local_requirement_validation(session)
    if len(requirements.strip()) < 40 or not validation.enough:
        raise ValueError(
            "Bu ma'lumot kam. Loyiha vazifalari, foydalanuvchi va admin amallarini batafsilroq yozing."
        )

    fallback_estimate = calculate_fallback_estimate(session)
    session.estimate = analysis.estimate if analysis is not None else fallback_estimate
    session.prepayment = session.estimate // 2
    session.ai_summary = (
        analysis.summary
        if analysis is not None
        else "Web App orqali yuborilgan talablar minimal narx va funksional murakkablik bo'yicha baholandi."
    )
    session.ai_features = (
        analysis.features
        if analysis is not None
        else ["Mijoz talablari", "Asosiy ishlab chiqish", "Boshlang'ich sozlash"]
    )
    session.ai_used = bool(analysis and analysis.ai_used)
    session.estimated_duration = estimate_duration_label(session, session.estimate)
    session.lead_score = lead_score_label(session, session.estimate)

    now = utc_now()
    with db_connect() as connection:
        order_id = db_insert(
            connection,
            """
            INSERT INTO orders (
                user_id, full_name, username, projects, requirements, estimate, prepayment,
                ai_summary, ai_features, ai_used, status, pipeline_stage, lead_score,
                estimated_duration, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'payment_confirmation', 'priced', ?, ?, ?, ?)
            """,
            (
                user_id,
                full_name,
                username,
                project_key,
                clean_requirements,
                session.estimate,
                session.prepayment,
                session.ai_summary,
                json.dumps(session.ai_features, ensure_ascii=False),
                1 if session.ai_used else 0,
                session.lead_score,
                session.estimated_duration,
                now,
                now,
            ),
        )
    order = get_order(order_id)
    if order is None:
        raise RuntimeError("Buyurtma yaratilmadi.")
    return order


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


def orders_for_user(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        )


def find_user(identifier: str) -> sqlite3.Row | None:
    clean = identifier.strip().lstrip("@")
    if not clean:
        return None
    with db_connect() as connection:
        if clean.isdigit():
            return connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (int(clean),),
            ).fetchone()
        return connection.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1",
            (clean,),
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


def save_order_feedback(
    order_id: int,
    user_id: int,
    *,
    rating: int | None = None,
    comment: str | None = None,
    portfolio_permission: bool | None = None,
) -> None:
    now = utc_now()
    existing = None
    with db_connect() as connection:
        existing = connection.execute(
            "SELECT id FROM order_feedback WHERE order_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (order_id, user_id),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO order_feedback (
                    order_id, user_id, rating, comment, portfolio_permission, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    user_id,
                    rating or 0,
                    (comment or "").strip(),
                    None if portfolio_permission is None else int(portfolio_permission),
                    now,
                    now,
                ),
            )
            return

        fields = ["updated_at = ?"]
        values: list[Any] = [now]
        if rating is not None:
            fields.append("rating = ?")
            values.append(rating)
        if comment is not None:
            fields.append("comment = ?")
            values.append(comment.strip())
        if portfolio_permission is not None:
            fields.append("portfolio_permission = ?")
            values.append(int(portfolio_permission))
        values.append(int(existing["id"]))
        connection.execute(
            f"UPDATE order_feedback SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def latest_feedback(limit: int = 20) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                """
                SELECT f.*, o.full_name, o.username, o.projects
                FROM order_feedback f
                JOIN orders o ON o.id = f.order_id
                ORDER BY f.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )


def feedback_stats() -> tuple[int, float]:
    with db_connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count, COALESCE(AVG(rating), 0) AS avg_rating FROM order_feedback WHERE rating > 0"
        ).fetchone()
        return int(row["count"]), float(row["avg_rating"])


def blacklist_reason_stats() -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(reason), ''), 'sababsiz') AS reason, COUNT(*) AS count
                FROM blocked_users
                GROUP BY COALESCE(NULLIF(TRIM(reason), ''), 'sababsiz')
                ORDER BY count DESC, reason ASC
                """
            ).fetchall()
        )


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


def save_project_file(
    user_id: int,
    file_id: str,
    file_type: str,
    file_name: str = "",
    order_id: int | None = None,
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO project_files (user_id, order_id, file_id, file_type, file_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, order_id, file_id, file_type, file_name, utc_now()),
        )


def attach_pending_files(user_id: int, order_id: int) -> None:
    with db_connect() as connection:
        connection.execute(
            "UPDATE project_files SET order_id = ? WHERE user_id = ? AND order_id IS NULL",
            (order_id, user_id),
        )


def order_files(order_id: int) -> list[sqlite3.Row]:
    with db_connect() as connection:
        return list(
            connection.execute(
                "SELECT * FROM project_files WHERE order_id = ? ORDER BY id DESC",
                (order_id,),
            ).fetchall()
        )


def log_audit(
    admin_id: int,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: str = "",
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (admin_id, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_id, action, entity_type, entity_id, details.strip(), utc_now()),
        )


def latest_audit_logs(order_id: int | None = None, limit: int = 30) -> list[sqlite3.Row]:
    with db_connect() as connection:
        if order_id is None:
            return list(
                connection.execute(
                    "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
        return list(
            connection.execute(
                """
                SELECT * FROM audit_logs
                WHERE entity_type = 'order' AND entity_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (order_id, limit),
            ).fetchall()
        )


def create_support_ticket(user: User, message: str) -> int:
    now = utc_now()
    with db_connect() as connection:
        return db_insert(
            connection,
            """
            INSERT INTO support_tickets (
                user_id, full_name, username, message, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'open', ?, ?)
            """,
            (user.id, user.full_name, user.username or "", message.strip(), now, now),
        )


def create_web_support_ticket(
    user_id: int,
    full_name: str,
    username: str,
    message: str,
) -> int:
    now = utc_now()
    with db_connect() as connection:
        return db_insert(
            connection,
            """
            INSERT INTO support_tickets (
                user_id, full_name, username, message, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'open', ?, ?)
            """,
            (user_id, full_name, username, message.strip(), now, now),
        )


def latest_support_tickets(status: str = "open", limit: int = 20) -> list[sqlite3.Row]:
    with db_connect() as connection:
        if status == "all":
            return list(
                connection.execute(
                    "SELECT * FROM support_tickets ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
        return list(
            connection.execute(
                "SELECT * FROM support_tickets WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        )


def get_support_ticket(ticket_id: int) -> sqlite3.Row | None:
    with db_connect() as connection:
        return connection.execute(
            "SELECT * FROM support_tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()


def reply_support_ticket(ticket_id: int, reply: str) -> sqlite3.Row | None:
    with db_connect() as connection:
        connection.execute(
            """
            UPDATE support_tickets
            SET admin_reply = ?, status = 'answered', updated_at = ?
            WHERE id = ?
            """,
            (reply.strip(), utc_now(), ticket_id),
        )
    return get_support_ticket(ticket_id)


def close_support_ticket(ticket_id: int) -> bool:
    with db_connect() as connection:
        cursor = connection.execute(
            "UPDATE support_tickets SET status = 'closed', updated_at = ? WHERE id = ?",
            (utc_now(), ticket_id),
        )
        return cursor.rowcount > 0


def create_appointment(user: User, scheduled_at: str) -> int:
    now = utc_now()
    with db_connect() as connection:
        return db_insert(
            connection,
            """
            INSERT INTO appointments (
                user_id, full_name, username, scheduled_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (user.id, user.full_name, user.username or "", scheduled_at, now, now),
        )


def latest_appointments(status: str = "pending", limit: int = 20) -> list[sqlite3.Row]:
    with db_connect() as connection:
        if status == "all":
            return list(
                connection.execute(
                    "SELECT * FROM appointments ORDER BY scheduled_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
        return list(
            connection.execute(
                "SELECT * FROM appointments WHERE status = ? ORDER BY scheduled_at ASC LIMIT ?",
                (status, limit),
            ).fetchall()
        )


def update_appointment_status(appointment_id: int, status: str) -> sqlite3.Row | None:
    with db_connect() as connection:
        connection.execute(
            "UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), appointment_id),
        )
        return connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()


def pending_appointment_reminders() -> list[sqlite3.Row]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=2)
    result = []
    for row in latest_appointments(status="confirmed", limit=100):
        if row["reminded_at"]:
            continue
        try:
            scheduled_at = datetime.fromisoformat(row["scheduled_at"])
        except ValueError:
            continue
        if now <= scheduled_at <= end:
            result.append(row)
    return result


def mark_appointment_reminded(appointment_id: int) -> None:
    with db_connect() as connection:
        connection.execute(
            "UPDATE appointments SET reminded_at = ?, updated_at = ? WHERE id = ?",
            (utc_now(), utc_now(), appointment_id),
        )


def referral_code_for_user(user_id: int) -> str:
    with db_connect() as connection:
        row = connection.execute(
            "SELECT code FROM referral_codes WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is not None:
            return str(row["code"])
        code = f"ZETTA{user_id}"
        connection.execute(
            "INSERT INTO referral_codes (user_id, code, created_at) VALUES (?, ?, ?)",
            (user_id, code, utc_now()),
        )
        return code


def apply_referral_code(referred_user_id: int, code: str) -> bool:
    code = code.strip().upper()
    with db_connect() as connection:
        owner = connection.execute(
            "SELECT user_id FROM referral_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if owner is None or int(owner["user_id"]) == referred_user_id:
            return False
        try:
            connection.execute(
                """
                INSERT INTO referrals (referrer_user_id, referred_user_id, code, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(owner["user_id"]), referred_user_id, code, utc_now()),
            )
        except sqlite3.IntegrityError:
            return False
    return True


def referral_stats(user_id: int) -> tuple[int, int]:
    with db_connect() as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ?",
            (user_id,),
        ).fetchone()[0]
        rewarded = connection.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ? AND rewarded = 1",
            (user_id,),
        ).fetchone()[0]
        return int(total), int(rewarded)


def reward_referral_for_user(referred_user_id: int) -> int | None:
    with db_connect() as connection:
        row = connection.execute(
            """
            SELECT id, referrer_user_id FROM referrals
            WHERE referred_user_id = ? AND rewarded = 0
            """,
            (referred_user_id,),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE referrals SET rewarded = 1 WHERE id = ?",
            (row["id"],),
        )
        return int(row["referrer_user_id"])


def configured_admin_roles() -> dict[int, str]:
    roles: dict[int, str] = {}
    for admin_id in admin_chat_ids():
        roles[admin_id] = "super_admin"
    raw_roles = os.getenv("ADMIN_ROLES", "")
    for item in raw_roles.split(","):
        if ":" not in item:
            continue
        user_id, role = item.split(":", 1)
        if user_id.strip().isdigit():
            roles[int(user_id.strip())] = role.strip()
    with db_connect() as connection:
        rows = connection.execute("SELECT user_id, role FROM admin_roles").fetchall()
    for row in rows:
        roles[int(row["user_id"])] = str(row["role"])
    return roles


def admin_role(user_id: int) -> str:
    return configured_admin_roles().get(user_id, "")


def set_admin_role(user_id: int, role: str, updated_by: int) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO admin_roles (user_id, role, updated_by, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                role = excluded.role,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (user_id, role, updated_by, utc_now()),
        )


def has_permission(user_id: int, permission: str) -> bool:
    role = admin_role(user_id)
    permissions = {
        "super_admin": {"all"},
        "sales": {"orders", "support", "meeting", "broadcast", "report"},
        "developer": {"orders", "task", "report"},
        "payment": {"orders", "payment"},
    }
    allowed = permissions.get(role, set())
    return "all" in allowed or permission in allowed


def admin_ids_for_permission(permission: str | None = None) -> list[int]:
    roles = configured_admin_roles()
    if permission is None:
        return list(roles.keys())
    routed = [user_id for user_id in roles if has_permission(user_id, permission)]
    return routed or list(roles.keys())


def get_system_state(key: str, default: str = "") -> str:
    with db_connect() as connection:
        row = connection.execute(
            "SELECT value FROM system_state WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row is not None else default


def set_system_state(key: str, value: str) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, utc_now()),
        )


def order_stats() -> tuple[int, int, list[sqlite3.Row]]:
    with db_connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        paid_sum = connection.execute(
            "SELECT COALESCE(SUM(estimate), 0) FROM orders WHERE status IN ('paid', 'delivered')"
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
        if _redis is not None:
            try:
                raw = _redis.get(f"session:{user_id}")
                if raw:
                    sessions[user_id] = _session_from_json(raw)
                    return sessions[user_id]
            except Exception as exc:  # noqa: BLE001
                logging.warning("Redis sessiya o'qilmadi: %s", exc)
        sessions[user_id] = UserSession()
    return sessions[user_id]


def reset_session(user_id: int, is_admin_test: bool = False) -> UserSession:
    sessions[user_id] = UserSession(is_admin_test=is_admin_test)
    save_session(user_id)
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
        "/calc - loyiha kalkulyatorini ochish\n"
        "/prices - xizmatlar narxlarini ko'rish\n"
        "/portfolio - portfolio havolasi\n"
        "/contact - admin bilan aloqa\n"
        "/status - oxirgi buyurtma holati\n"
        "/invoice - oxirgi buyurtma invoice PDF\n"
        "/contract - oxirgi buyurtma shartnoma PDF\n"
        "/timeline - oxirgi buyurtma timeline\n"
        "/support MATN - support murojaati\n"
        "/meeting YYYY-MM-DD HH:MM - uchrashuv so'rash\n"
        "/referral - referral kodingiz\n"
        "/ref KOD - referral kodni ishlatish\n"
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
        "/contract ID - shartnoma PDF\n"
        "/kanban - CRM Kanban ko'rinishi\n"
        "/dashboard - chuqur savdo dashboard\n"
        "/customer USER_ID|@username - mijoz kartasi\n"
        "/timeline ID - loyiha timeline\n"
        "/lead ID - lead scoring 2.0\n"
        "/risk ID - loyiha risk tahlili\n"
        "/templates [USER_ID] - quick reply shablonlari\n"
        "/sendtemplate USER_ID KEY - shablon yuborish\n"
        "/postdraft ID - portfolio/kanal post draft\n"
        "/blackliststats - blok sabablar statistikasi\n"
        "/feedbacks - oxirgi feedbacklar\n"
        "/stage ID BOSQICH - CRM bosqichini o'zgartirish\n"
        "/task ID matn - buyurtmaga vazifa qo'shish\n"
        "/tasks ID - vazifalar ro'yxati\n"
        "/files ID - loyiha fayllarini olish\n"
        "/done TASK_ID - vazifani yopish\n"
        "/deadline ID YYYY-MM-DD - deadline qo'yish\n"
        "/assign ID ism - mas'ul biriktirish\n"
        "/web - web admin panel havolasi\n"
        "/audit [ID] - audit log\n"
        "/tickets - support ticketlar\n"
        "/reply TICKET_ID matn - ticketga javob\n"
        "/closeticket ID - ticketni yopish\n"
        "/meetings - uchrashuvlar\n"
        "/confirmmeeting ID - uchrashuvni tasdiqlash\n"
        "/role USER_ID ROLE - admin rol berish\n"
        "/admins - admin rollari\n"
        "/aireport - AI savdo hisoboti\n"
        "/health - monitoring holati\n"
        "/export - buyurtmalarni CSV qilish\n"
        "/broadcast matn - hammaga xabar yuborish\n"
        "/block USER_ID sabab - foydalanuvchini bloklash\n"
        "/unblock USER_ID - blokdan chiqarish\n"
        "/backup - database backup faylini olish\n\n"
        "User commandlar ham ishlaydi: /start, /new, /calc, /prices, /portfolio, /contact, /status, /timeline, /invoice, /contract, /support, /meeting, /referral, /ref, /faq, /promo, /help, /cancel."
    )


def user_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="new", description="Yangi buyurtma boshlash"),
        BotCommand(command="calc", description="Loyiha kalkulyatori"),
        BotCommand(command="prices", description="Narxlarni ko'rish"),
        BotCommand(command="portfolio", description="Portfolioni ko'rish"),
        BotCommand(command="contact", description="Admin bilan aloqa"),
        BotCommand(command="status", description="Buyurtma holati"),
        BotCommand(command="timeline", description="Buyurtma timeline"),
        BotCommand(command="invoice", description="Invoice PDF"),
        BotCommand(command="contract", description="Shartnoma PDF"),
        BotCommand(command="support", description="Support murojaati"),
        BotCommand(command="meeting", description="Uchrashuv so'rash"),
        BotCommand(command="referral", description="Referral kod"),
        BotCommand(command="ref", description="Referral kod ishlatish"),
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
        BotCommand(command="contract", description="Shartnoma PDF"),
        BotCommand(command="kanban", description="CRM Kanban"),
        BotCommand(command="dashboard", description="Chuqur dashboard"),
        BotCommand(command="customer", description="Mijoz kartasi"),
        BotCommand(command="timeline", description="Loyiha timeline"),
        BotCommand(command="lead", description="Lead scoring"),
        BotCommand(command="risk", description="Risk tahlil"),
        BotCommand(command="templates", description="Reply shablonlar"),
        BotCommand(command="sendtemplate", description="Shablon yuborish"),
        BotCommand(command="postdraft", description="Kanal post draft"),
        BotCommand(command="blackliststats", description="Blacklist statistikasi"),
        BotCommand(command="feedbacks", description="Feedbacklar"),
        BotCommand(command="stage", description="CRM bosqich"),
        BotCommand(command="task", description="Vazifa qo'shish"),
        BotCommand(command="tasks", description="Vazifalar"),
        BotCommand(command="files", description="Loyiha fayllari"),
        BotCommand(command="done", description="Vazifani yopish"),
        BotCommand(command="deadline", description="Deadline"),
        BotCommand(command="assign", description="Mas'ul"),
        BotCommand(command="web", description="Web admin panel"),
        BotCommand(command="audit", description="Audit log"),
        BotCommand(command="tickets", description="Support ticketlar"),
        BotCommand(command="reply", description="Ticketga javob"),
        BotCommand(command="closeticket", description="Ticketni yopish"),
        BotCommand(command="meetings", description="Uchrashuvlar"),
        BotCommand(command="confirmmeeting", description="Uchrashuvni tasdiqlash"),
        BotCommand(command="role", description="Admin rol"),
        BotCommand(command="admins", description="Adminlar"),
        BotCommand(command="aireport", description="AI savdo hisoboti"),
        BotCommand(command="health", description="Monitoring"),
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
        for admin_id in configured_admin_roles():
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
        for admin_id in configured_admin_roles():
            await bot.set_chat_menu_button(chat_id=admin_id, menu_button=menu_button)
        logging.info("Telegram Menu Web App sozlandi: %s", url)
    except Exception as exc:
        logging.warning("Telegram Menu Web App sozlanmadi: %s", exc)


def is_admin_user(user_id: int) -> bool:
    return bool(admin_role(user_id))


def is_rate_limited(user_id: int) -> bool:
    if _redis is not None:
        try:
            key = f"rl:{user_id}"
            count = _redis.incr(key)
            if count == 1:
                _redis.expire(key, RATE_LIMIT_WINDOW_SECONDS)
            return count > RATE_LIMIT_MAX_MESSAGES
        except Exception:  # noqa: BLE001
            pass
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

        if not is_admin_user(user.id):
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

            if subscription_required():
                is_checksub = (
                    isinstance(event, CallbackQuery) and (event.data or "").startswith("checksub")
                )
                bot = data.get("bot")
                if bot is not None and not is_checksub and not await is_user_subscribed(bot, user.id):
                    await prompt_subscribe(event)
                    return None

        result = await handler(event, data)
        # Handler sessiyani o'zgartirgan bo'lishi mumkin — Redis'ga saqlaymiz.
        save_session(user.id)
        return result


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
    weak_phrases = ("bilmayman", "shunchaki", "keyin", "arzon", "tekinga", "test", "o'ylab", "uylab")
    serious_phrases = ("tayyorman", "boshlaymiz", "bugun", "ertaga", "tez", "shoshilinch", "admin panel", "crm")
    if len(session.requirements.strip()) < 80:
        score -= 2
    if len(session.requirements) >= 180:
        score += 2
    elif len(session.requirements) >= 90:
        score += 1
    if any(word in text for word in serious_phrases):
        score += 2
    if any(word in text for word in ("admin panel", "crm", "buyurtma", "katalog", "dostavka", "hisobot")):
        score += 1
    if estimate and estimate >= 600:
        score += 1
    if session.promo_code:
        score += 1
    if any(word in text for word in weak_phrases):
        score -= 1
    if session.off_topic_count >= 2:
        score -= 2

    if score >= 6:
        return "Juda issiq lead"
    if score >= 4:
        return "Issiq lead"
    if score >= 2:
        return "O'rta lead"
    if score >= 0:
        return "Vaqt oladi"
    return "Sifatsiz lead"


def portfolio_category_for_project_keys(keys: Iterable[str]) -> str:
    normalized_keys = set(ordered_project_keys(keys))
    if any(key in normalized_keys for key in ("telegram_bot_simple", "telegram_twa", "telegram_order_bot")):
        return "telegram"
    if any(key in normalized_keys for key in ("website_landing", "website_corporate", "website_store")):
        return "web"
    if any(key in normalized_keys for key in ("crm_system", "accounting_system")):
        return "crm"
    if "mobile_app" in normalized_keys:
        return "mobile"
    return "all"


def portfolio_category_for_session(session: UserSession) -> str:
    return portfolio_category_for_project_keys(session.selected_projects)


def portfolio_category_for_order(order: sqlite3.Row) -> str:
    return portfolio_category_for_project_keys(order["projects"].split(","))


def calculator_prompt_for_session(session: UserSession) -> str:
    project_hint = selected_project_titles(session) or "tanlangan loyiha"
    questions = "\n".join(f"{index}. {question}" for index, question in enumerate(CALCULATOR_QUESTIONS, start=1))
    return (
        f"{project_hint} uchun loyiha kalkulyatori.\n\n"
        "Quyidagi savollarga bitta xabarda javob yozing. Javob qancha aniq bo'lsa, narx ham shuncha aniq chiqadi:\n\n"
        f"{questions}"
    )


def requirements_example_text() -> str:
    return (
        "Talab namunasi:\n\n"
        "Menga restoran uchun Telegram buyurtma boti kerak. Mijoz menyudan taomlarni ko'radi, savatchaga qo'shadi, "
        "telefon raqami va manzilini yuboradi, to'lov naqd bo'ladi. Admin panelda buyurtmalarni ko'radi, statusini "
        "o'zgartiradi, kurerga uzatadi va kunlik hisobotni ko'radi. Menyu mahsulotlarini admin qo'sha olishi kerak."
    )


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


async def transcribe_voice(bot: Bot, file_id: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Ovozli xabar uchun GROQ_API_KEY sozlanmagan.")

    telegram_file = await bot.get_file(file_id)
    if not telegram_file.file_path:
        raise RuntimeError("Telegram ovoz fayli topilmadi.")

    buffer = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)
    buffer.seek(0)

    form = aiohttp.FormData()
    form.add_field(
        "file",
        buffer.getvalue(),
        filename="voice.ogg",
        content_type="audio/ogg",
    )
    form.add_field("model", os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"))
    form.add_field("language", "uz")
    form.add_field("response_format", "json")

    timeout = aiohttp.ClientTimeout(total=90)
    headers = {"Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession(timeout=timeout) as client:
        async with client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            data=form,
        ) as response:
            response_text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Ovoz tahlili xatosi {response.status}: {response_text[:160]}")

    data = json.loads(response_text)
    return str(data.get("text") or "").strip()


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
            [
                InlineKeyboardButton(text="Kalkulyator", callback_data="menu:calculator"),
                InlineKeyboardButton(text="Narxlarni ko'rish", callback_data="menu:prices"),
            ],
            [
                InlineKeyboardButton(text="Buyurtma holati", callback_data="menu:status"),
                InlineKeyboardButton(text="FAQ", callback_data="menu:faq"),
            ],
            [InlineKeyboardButton(text="Talab namunasi", callback_data="menu:example")],
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
        [InlineKeyboardButton(text="Talab namunasi", callback_data="requirements:example")],
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
        [KeyboardButton(text=START_ORDER_TEXT), KeyboardButton(text=CALCULATOR_TEXT)],
        [KeyboardButton(text=PRICE_TEXT), KeyboardButton(text=MAIN_MENU_TEXT)],
        [KeyboardButton(text=CANCEL_TEXT)],
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
            [
                InlineKeyboardButton(text="Mos portfolio", callback_data="payment:portfolio"),
                InlineKeyboardButton(text="Invoice PDF", callback_data="payment:invoice"),
            ],
            [InlineKeyboardButton(text="Shartnoma PDF", callback_data="payment:contract")],
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
            [InlineKeyboardButton(text="Kanban", callback_data="panel:kanban")],
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
            [
                InlineKeyboardButton(text="Dashboard", callback_data="panel:dashboard"),
                InlineKeyboardButton(text="Feedback", callback_data="panel:feedbacks"),
            ],
            [InlineKeyboardButton(text="Blacklist stats", callback_data="panel:blackliststats")],
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
            InlineKeyboardButton(text="Shartnoma PDF", callback_data=f"panel:contract:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Task qo'shish", callback_data=f"panel:task:{order['id']}"),
            InlineKeyboardButton(text="Mos portfolio", callback_data=f"panel:portfolio:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Timeline", callback_data=f"panel:timeline:{order['id']}"),
            InlineKeyboardButton(text="Risk tahlil", callback_data=f"panel:risk:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Mijoz kartasi", callback_data=f"panel:customer:{order['user_id']}"),
            InlineKeyboardButton(text="Reply shablon", callback_data=f"panel:templates:{order['id']}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="Post draft", callback_data=f"panel:postdraft:{order['id']}"),
            InlineKeyboardButton(text="Feedbacklar", callback_data="panel:feedbacks"),
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


def feedback_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(rating), callback_data=f"feedback:rate:{order_id}:{rating}")
                for rating in range(1, 6)
            ],
            [
                InlineKeyboardButton(text="Portfolio uchun ruxsat", callback_data=f"feedback:portfolio:{order_id}:yes"),
                InlineKeyboardButton(text="Ruxsat yo'q", callback_data=f"feedback:portfolio:{order_id}:no"),
            ],
        ]
    )


def template_keyboard(user_id: int, order_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for key in ADMIN_REPLY_TEMPLATES:
        suffix = f":{order_id}" if order_id is not None else ""
        rows.append(
            [InlineKeyboardButton(text=key, callback_data=f"template:send:{user_id}:{key}{suffix}")]
        )
    rows.append([InlineKeyboardButton(text="Admin panel", callback_data="panel:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Kanalga chiqarish", callback_data=f"post:send:{order_id}"),
                InlineKeyboardButton(text="Bekor qilish", callback_data=f"post:cancel:{order_id}"),
            ]
        ]
    )


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
    lang = get_user_language(user_id)
    await message.answer(
        t("welcome", lang),
        reply_markup=main_reply_keyboard(is_admin_user(user_id)),
    )
    await message.answer(
        t("choose_action", lang),
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
    calculator_mode: bool = False,
) -> None:
    session = reset_session(user_id, is_admin_test=is_admin_test) if reset else get_session(user_id)
    if calculator_mode:
        session.calculator_mode = True
    session.stage = "choose_project"
    title = "Test buyurtma rejimi.\n\n" if session.is_admin_test else ""
    mode_text = "Loyiha kalkulyatori.\n\n" if session.calculator_mode else ""
    await message.answer(
        f"{title}{mode_text}Assalomu alaykum! ZettaCode Tech'ga xush kelibsiz.\n\n"
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
    files = order_files(order["id"])
    files_text = (
        "\n".join(f"- {item['file_name'] or item['file_type']}" for item in files[:10])
        if files
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
        f"Biriktirilgan fayllar:\n{files_text}\n\n"
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


def format_kanban_text(limit_per_stage: int = 6) -> str:
    lines = ["CRM Kanban:"]
    for stage, title in PIPELINE_STAGES.items():
        orders = latest_orders_by_pipeline(stage, limit=limit_per_stage)
        lines.append("")
        lines.append(f"{title}:")
        if not orders:
            lines.append("- buyurtma yo'q")
            continue
        for order in orders:
            username = f"@{order['username']}" if order["username"] else "username yo'q"
            lines.append(
                f"- #{order['id']} | ${order['estimate']} | {order['lead_score'] or '-'} | "
                f"{order['full_name']} ({username})"
            )
    return "\n".join(lines)


def detect_sales_objection(text: str) -> str | None:
    normalized_text = text.lower()
    for key, keywords in SALES_OBJECTION_KEYWORDS.items():
        if any(keyword in normalized_text for keyword in keywords):
            return key
    return None


def format_customer_card(identifier: str) -> str:
    user = find_user(identifier)
    if user is None:
        return "Mijoz topilmadi."
    orders = orders_for_user(int(user["user_id"]), limit=10)
    total = sum(int(order["estimate"]) for order in orders)
    paid_total = sum(
        int(order["estimate"])
        for order in orders
        if order["status"] in {"paid", "delivered"}
    )
    latest = orders[0] if orders else None
    username = f"@{user['username']}" if user["username"] else "username yo'q"
    lines = [
        "Mijoz kartasi:",
        "",
        f"ID: {user['user_id']}",
        f"Ism: {user['full_name']} ({username})",
        f"Birinchi kirgan: {user['first_seen']}",
        f"Oxirgi aktiv: {user['last_seen']}",
        f"Buyurtmalar soni: {len(orders)}",
        f"Umumiy baholangan summa: ${total}",
        f"Tasdiqlangan summa: ${paid_total}",
    ]
    if latest is not None:
        lines.extend(
            [
                "",
                "Oxirgi buyurtma:",
                f"#{latest['id']} | {STATUS_LABELS.get(latest['status'], latest['status'])}",
                f"Loyiha: {projects_from_order(latest)}",
                f"Narx: ${latest['estimate']}",
                f"Lead: {latest['lead_score'] or '-'}",
            ]
        )
    return "\n".join(lines)


def format_order_timeline(order: sqlite3.Row) -> str:
    current_stage = order["pipeline_stage"]
    reached = True
    lines = [f"Buyurtma #{order['id']} timeline:"]
    for stage, title in TIMELINE_STEPS:
        marker = "[x]" if reached else "[ ]"
        if stage == current_stage:
            marker = "[>]"
            reached = False
        if order["status"] == "delivered" and stage == "done":
            marker = "[x]"
        lines.append(f"{marker} {title}")
    lines.extend(
        [
            "",
            f"Status: {STATUS_LABELS.get(order['status'], order['status'])}",
            f"CRM bosqich: {PIPELINE_STAGES.get(order['pipeline_stage'], order['pipeline_stage'])}",
            f"Yangilangan: {order['updated_at']}",
        ]
    )
    return "\n".join(lines)


def format_blacklist_stats() -> str:
    rows = blacklist_reason_stats()
    if not rows:
        return "Blacklist statistikasi: hozircha bloklangan foydalanuvchi yo'q."
    lines = ["Blacklist sabablar statistikasi:"]
    lines.extend(f"- {row['reason']}: {row['count']}" for row in rows)
    return "\n".join(lines)


def format_feedbacks_text(limit: int = 10) -> str:
    rows = latest_feedback(limit=limit)
    if not rows:
        return "Feedbacklar hali yo'q."
    lines = ["Oxirgi feedbacklar:"]
    for row in rows:
        permission = row["portfolio_permission"]
        permission_text = "portfolio: -" if permission is None else f"portfolio: {'ha' if permission else 'yoq'}"
        lines.append(
            f"#{row['order_id']} | {row['rating']}/5 | {row['full_name']} (@{row['username'] or 'username yoq'}) | {permission_text}\n"
            f"{row['comment'] or '-'}"
        )
    return "\n\n".join(lines)


def format_deep_dashboard() -> str:
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
    with db_connect() as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
        weekly = int(connection.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (week_ago,)).fetchone()[0])
        paid = int(connection.execute("SELECT COUNT(*) FROM orders WHERE status IN ('paid', 'delivered')").fetchone()[0])
        rejected = int(connection.execute("SELECT COUNT(*) FROM orders WHERE status = 'rejected'").fetchone()[0])
        avg_price = float(connection.execute("SELECT COALESCE(AVG(estimate), 0) FROM orders").fetchone()[0])
        waiting = int(
            connection.execute(
                "SELECT COUNT(*) FROM orders WHERE status IN ('payment_confirmation', 'awaiting_receipt', 'admin_contact')"
            ).fetchone()[0]
        )
    feedback_count, avg_rating = feedback_stats()
    conversion = round((paid / total) * 100, 1) if total else 0
    return (
        "Chuqur dashboard:\n\n"
        f"Jami leadlar: {total}\n"
        f"Oxirgi 7 kun leadlari: {weekly}\n"
        f"Tasdiqlangan buyurtmalar: {paid}\n"
        f"Rad etilganlar: {rejected}\n"
        f"To'lov/kelishuv kutilmoqda: {waiting}\n"
        f"Konversiya: {conversion}%\n"
        f"O'rtacha narx: ${round(avg_price)}\n"
        f"Feedbacklar: {feedback_count}\n"
        f"O'rtacha baho: {avg_rating:.1f}/5"
    )


def fallback_project_risk(order: sqlite3.Row) -> str:
    text = order["requirements"].lower()
    risks = []
    if len(order["requirements"]) < 180:
        risks.append("Talablar qisqa, texnik tafsilotlarni admin bilan aniqlashtirish kerak.")
    if any(keyword in text for keyword in ("tez", "shoshilinch", "bugun", "ertaga")):
        risks.append("Muddat bosimi bor, scope qisqartirilmasa kechikish xavfi yuqori.")
    if any(keyword in text for keyword in ("api", "integratsiya", "sms", "ai", "sun'iy")):
        risks.append("Integratsiya bor, tashqi servislar sababli qo'shimcha tekshiruv kerak.")
    if order["lead_score"] in {"Sifatsiz lead", "Vaqt oladi"}:
        risks.append("Lead sifati pastroq, savdo bosqichida qayta kvalifikatsiya kerak.")
    if not risks:
        risks.append("Katta xavf ko'rinmadi, lekin scope va muddat yozma tasdiqlansin.")
    return "Loyiha risk tahlili:\n\n" + "\n".join(f"- {risk}" for risk in risks)


async def ai_project_risk(order: sqlite3.Row) -> str:
    fallback = fallback_project_risk(order)
    if not os.getenv("GROQ_API_KEY"):
        return fallback
    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech uchun loyiha risk tahlilchisisan. O'zbek tilida qisqa yoz. "
                "Talab noaniqligi, muddat, narx, integratsiya va mijoz sifati bo'yicha xavflarni ayt. "
                "Javob faqat JSON: {\"risk\": string}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Buyurtma #{order['id']}\n"
                f"Loyiha: {projects_from_order(order)}\n"
                f"Narx: ${order['estimate']}\n"
                f"Lead: {order['lead_score']}\n"
                f"Talablar:\n{order['requirements']}"
            ),
        },
    ]
    try:
        parsed = await groq_json(messages, max_tokens=700, temperature=0.15)
        risk = str(parsed.get("risk") or "").strip()
        return risk or fallback
    except Exception as exc:
        logging.warning("Risk AI tahlili ishlamadi: %s", exc)
        return fallback


def fallback_portfolio_case(order: sqlite3.Row) -> str:
    return (
        f"ZettaCode Tech yangi loyiha case:\n\n"
        f"Loyiha turi: {projects_from_order(order)}\n"
        f"Vazifa: {order['ai_summary'] or 'Mijoz biznes jarayonini raqamlashtirish.'}\n"
        f"Yechim: {', '.join(json.loads(order['ai_features'] or '[]')[:4]) or 'Bot/sayt/CRM funksiyalari ishlab chiqildi.'}\n"
        "To'lov oqimi: loyiha ichida faqat naqd to'lov siyosati.\n\n"
        "ZettaCode Tech - biznesingizni avtomatlashtiramiz."
    )


async def ai_portfolio_case(order: sqlite3.Row) -> str:
    fallback = fallback_portfolio_case(order)
    if not os.getenv("GROQ_API_KEY"):
        return fallback
    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech uchun Telegram kanalga portfolio post draft yozasan. "
                "O'zbek tilida, qisqa, sotuvga mos, lekin mijoz maxfiy ma'lumotlarini ochmasdan yoz. "
                "Online to'lov integratsiyasini reklama qilma. Javob faqat JSON: {\"post\": string}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Loyiha: {projects_from_order(order)}\n"
                f"Tahlil: {order['ai_summary']}\n"
                f"Funksiyalar: {order['ai_features']}\n"
                f"Talablar:\n{order['requirements']}"
            ),
        },
    ]
    try:
        parsed = await groq_json(messages, max_tokens=700, temperature=0.25)
        post = str(parsed.get("post") or "").strip()
        return post or fallback
    except Exception as exc:
        logging.warning("Portfolio post AI orqali yaratilmadi: %s", exc)
        return fallback


def ai_status_text() -> str:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    status = "ulangan" if api_key else "ulanmagan"
    return f"AI holati: {status}\nModel: {model}"


def fallback_sales_report() -> str:
    total, paid_sum, statuses = order_stats()
    pipelines = pipeline_stats()
    with db_connect() as connection:
        leads = connection.execute(
            """
            SELECT lead_score, COUNT(*) AS count
            FROM orders
            GROUP BY lead_score
            ORDER BY count DESC
            """
        ).fetchall()
        recent_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM orders WHERE created_at >= ?",
                ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds"),),
            ).fetchone()[0]
        )

    status_text = ", ".join(
        f"{STATUS_LABELS.get(row['status'], row['status'])}: {row['count']}" for row in statuses
    ) or "ma'lumot yo'q"
    pipeline_text = ", ".join(
        f"{PIPELINE_STAGES.get(row['pipeline_stage'], row['pipeline_stage'])}: {row['count']}"
        for row in pipelines
    ) or "ma'lumot yo'q"
    lead_text = ", ".join(
        f"{row['lead_score'] or 'Aniqlanmagan'}: {row['count']}" for row in leads
    ) or "ma'lumot yo'q"
    return (
        "AI savdo hisoboti:\n\n"
        f"Jami buyurtma: {total}\n"
        f"Oxirgi 7 kun: {recent_count}\n"
        f"Tasdiqlangan loyihalar qiymati: ${paid_sum}\n"
        f"Holatlar: {status_text}\n"
        f"CRM pipeline: {pipeline_text}\n"
        f"Leadlar: {lead_text}\n\n"
        "Tavsiya: narx olgan, ammo predoplata qilmagan mijozlar bilan qayta bog'laning; "
        "issiq leadlarni birinchi navbatda ko'rib chiqing."
    )


async def ai_sales_report() -> str:
    fallback = fallback_sales_report()
    if not os.getenv("GROQ_API_KEY"):
        return fallback

    messages = [
        {
            "role": "system",
            "content": (
                "Sen ZettaCode Tech savdo analitigi bo'lib ishlaysan. Berilgan statistikani o'zbek tilida "
                "qisqa tahlil qil, muammolarni va 3 ta amaliy tavsiyani yoz. Hech qanday yangi raqam o'ylab topma. "
                "Javob faqat JSON bo'lsin: {\"report\": string}"
            ),
        },
        {"role": "user", "content": fallback},
    ]
    try:
        parsed = await groq_json(messages, max_tokens=700, temperature=0.15)
        report = str(parsed.get("report") or "").strip()
        return report or fallback
    except Exception as exc:
        logging.warning("AI savdo hisoboti yaratilmadi: %s", exc)
        return fallback


def health_text() -> str:
    database_status = "ishlayapti"
    try:
        with db_connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        database_status = f"xato: {exc}"

    uptime = datetime.now(timezone.utc) - BOT_STARTED_AT
    total_seconds = max(0, int(uptime.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    heartbeat = get_system_state("monitor_heartbeat", "hali yozilmagan")
    return (
        "Bot monitoring holati:\n\n"
        f"Bot: ishlayapti\n"
        f"Database: {database_status}\n"
        f"AI: {'ulangan' if os.getenv('GROQ_API_KEY') else 'ulanmagan'}\n"
        f"Uptime: {hours} soat {minutes} daqiqa {seconds} soniya\n"
        f"Oxirgi heartbeat: {heartbeat}"
    )


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


BACKUP_TABLES = [
    "orders", "users", "order_tasks", "project_files", "blocked_users",
    "order_notes", "order_feedback", "support_tickets", "appointments",
    "referral_codes", "referrals", "admin_roles", "audit_logs", "system_state",
]


def build_full_backup() -> tuple[bytes, str]:
    """Barcha jadvallarni JSON'ga yig'adi — SQLite ham, PostgreSQL ham ishlaydi."""
    dump: dict[str, list] = {}
    with db_connect() as connection:
        for table in BACKUP_TABLES:
            try:
                rows = connection.execute(f"SELECT * FROM {table}").fetchall()
                dump[table] = [dict(row) for row in rows]
            except Exception as exc:  # noqa: BLE001
                dump[table] = []
                logging.warning("Backup: '%s' jadvali o'qilmadi: %s", table, exc)
    payload = {
        "generated_at": utc_now(),
        "backend": "postgres" if IS_POSTGRES else "sqlite",
        "tables": dump,
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    name = f"zettacode_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return data, name


async def send_database_backup(message: Message) -> None:
    data, name = build_full_backup()
    await message.answer_document(
        BufferedInputFile(data, filename=name),
        caption=f"To'liq backup (JSON, barcha jadvallar): {name}",
    )


async def send_backup_to_admins(bot: Bot) -> None:
    """Avtomatik kunlik backup'ni barcha adminlarga yuboradi."""
    data, name = build_full_backup()
    for admin_id in admin_chat_ids():
        try:
            await bot.send_document(
                admin_id,
                BufferedInputFile(data, filename=name),
                caption=f"Avtomatik kunlik backup: {name}",
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("Backup admin'ga yuborilmadi (%s): %s", admin_id, exc)


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
    permission: str | None = None,
) -> None:
    for admin_id in admin_ids_for_permission(permission):
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


def contract_lines(order: sqlite3.Row) -> list[str]:
    features = json.loads(order["ai_features"] or "[]")
    feature_lines = features[:8] if features else ["Asosiy funksiyalar texnik topshiriq bosqichida aniqlashtiriladi"]
    return [
        f"Kelishuv loyihasi: ZettaCode Tech buyurtma #{order['id']}",
        f"Sana: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "Tomonlar:",
        "Ijrochi: ZettaCode Tech",
        f"Mijoz: {order['full_name']} (@{order['username'] or 'username yoq'})",
        "",
        "Loyiha:",
        f"Turi: {projects_from_order(order)}",
        f"Murakkablik: {complexity_label_for_order(order)}",
        f"Taxminiy muddat: {order['estimated_duration'] or '-'}",
        "",
        "Asosiy ishlar:",
        *[f"- {line}" for line in feature_lines],
        "",
        "Narx va tolov:",
        f"Umumiy taxminiy narx: ${order['estimate']}",
        f"Ish boshlash uchun 50% predoplata: ${order['prepayment']}",
        "Predoplata plastik karta orqali qabul qilinadi.",
        "Loyiha ichidagi tolov funksiyasi faqat naqd tolov sifatida korib chiqiladi.",
        "",
        "Izoh:",
        "Ushbu hujjat dastlabki kelishuv drafti. Yakuniy shartlar admin bilan tasdiqlanadi.",
        "",
        "Talablar:",
        *(order["requirements"].splitlines()[:12] or ["-"]),
    ]


async def send_contract_pdf(message: Message, order: sqlite3.Row) -> None:
    data = simple_pdf_bytes(f"ZettaCode Tech Contract #{order['id']}", contract_lines(order))
    await message.answer_document(
        BufferedInputFile(data, filename=f"zettacode_contract_{order['id']}.pdf"),
        caption=f"Buyurtma #{order['id']} uchun shartnoma draft PDF.",
    )


def project_channel_target() -> str:
    target = (
        os.getenv("PROJECT_CHANNEL_ID", "").strip()
        or os.getenv("PROJECT_CHANNEL_USERNAME", "").strip()
        or os.getenv("CHANNEL_USERNAME", "").strip()
    )
    if target and not target.startswith("@") and not target.lstrip("-").isdigit():
        return f"@{target}"
    return target


_sub_cache: dict[int, float] = {}


def subscription_required() -> bool:
    return os.getenv("REQUIRE_SUBSCRIPTION", "0").strip() in {"1", "true", "True", "ha"}


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    """Foydalanuvchi majburiy kanalga obuna bo'lganmi. Xato/kanal yo'q bo'lsa — ruxsat (fail-open)."""
    channel = project_channel_target()
    if not channel:
        return True
    now = time.time()
    if _redis is not None:
        try:
            if _redis.get(f"sub:{user_id}") == "1":
                return True
        except Exception:  # noqa: BLE001
            pass
    elif _sub_cache.get(user_id, 0) > now:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        subscribed = member.status in {"creator", "administrator", "member"}
    except Exception as exc:  # noqa: BLE001
        logging.warning("Obuna tekshiruvi xatosi (%s): %s", channel, exc)
        return True
    if subscribed:
        if _redis is not None:
            try:
                _redis.set(f"sub:{user_id}", "1", ex=600)
            except Exception:  # noqa: BLE001
                pass
        else:
            _sub_cache[user_id] = now + 600
    return subscribed


def subscribe_prompt_keyboard() -> InlineKeyboardMarkup:
    channel = project_channel_target()
    rows = []
    if channel.startswith("@"):
        rows.append(
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{channel.lstrip('@')}")]
        )
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="checksub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def prompt_subscribe(event: Any) -> None:
    text = (
        "Botdan to'liq foydalanish uchun avval rasmiy kanalimizga obuna bo'ling, "
        "so'ng \"✅ Tekshirish\" tugmasini bosing."
    )
    keyboard = subscribe_prompt_keyboard()
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.answer(text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def send_delivery_flow(bot: Bot, order: sqlite3.Row) -> None:
    await bot.send_message(
        order["user_id"],
        f"Buyurtma #{order['id']} bo'yicha loyiha topshirildi deb belgilandi.\n\n"
        "Iltimos, xizmatimizni 1 dan 5 gacha baholang va portfolio uchun ruxsatni belgilang.",
        reply_markup=feedback_keyboard(order["id"]),
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
                    permission="orders",
                )
            except Exception as exc:
                logging.warning("Reminder yuborilmadi: %s", exc)

        for appointment in pending_appointment_reminders():
            local_time = datetime.fromisoformat(appointment["scheduled_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            try:
                await bot.send_message(
                    appointment["user_id"],
                    f"Eslatma: uchrashuvingiz #{appointment['id']} yaqinlashmoqda.\nVaqt: {local_time}",
                )
                await notify_admins(
                    bot,
                    f"Uchrashuv eslatmasi #{appointment['id']}\n"
                    f"Mijoz: {appointment['full_name']}\nVaqt: {local_time}",
                    permission="meeting",
                )
                mark_appointment_reminded(appointment["id"])
            except Exception as exc:
                logging.warning("Uchrashuv eslatmasi yuborilmadi: %s", exc)

        await asyncio.sleep(3600)


async def monitoring_loop(bot: Bot) -> None:
    await asyncio.sleep(5)
    while True:
        try:
            with db_connect() as connection:
                connection.execute("SELECT 1").fetchone()
            set_system_state("monitor_heartbeat", utc_now())

            try:
                report_hour = int(os.getenv("DAILY_REPORT_HOUR", "20"))
            except ValueError:
                report_hour = 20
            report_hour = min(23, max(0, report_hour))
            local_now = datetime.now().astimezone()
            last_report_date = get_system_state("daily_report_date")
            if local_now.hour >= report_hour and last_report_date != local_now.date().isoformat():
                await notify_admins(bot, await ai_sales_report(), permission="report")
                set_system_state("daily_report_date", local_now.date().isoformat())

            # Avtomatik kunlik backup (kuniga bir marta, hisobot vaqtida)
            last_backup_date = get_system_state("daily_backup_date")
            if local_now.hour >= report_hour and last_backup_date != local_now.date().isoformat():
                await send_backup_to_admins(bot)
                set_system_state("daily_backup_date", local_now.date().isoformat())
        except Exception as exc:
            logging.exception("Monitoring tekshiruvi xatosi: %s", exc)
            last_error = get_system_state("monitor_last_error")
            error_key = f"{datetime.now(timezone.utc).date().isoformat()}:{type(exc).__name__}"
            if last_error != error_key:
                await notify_admins(bot, f"Bot monitoring xatosi: {type(exc).__name__}: {exc}")
                set_system_state("monitor_last_error", error_key)

        await asyncio.sleep(300)


def web_admin_url() -> str:
    token = os.getenv("WEB_ADMIN_TOKEN", "").strip()
    suffix = f"?token={token}" if token else ""
    # Railway (yoki boshqa public domen) bo'lsa, localhost emas, public URL qaytariladi.
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip() or os.getenv("PUBLIC_DOMAIN", "").strip()
    if public_domain:
        return f"https://{public_domain}/admin{suffix}"
    host = os.getenv("WEB_ADMIN_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_ADMIN_PORT", str(WEB_ADMIN_DEFAULT_PORT)))
    return f"http://{host}:{port}/admin{suffix}"


def web_authorized(request: web.Request) -> bool:
    token = os.getenv("WEB_ADMIN_TOKEN", "").strip()
    if not token:
        return request.remote in {"127.0.0.1", "::1", "localhost"}
    return request.query.get("token") == token


def validate_telegram_init_data(init_data: str) -> dict[str, Any] | None:
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token or not init_data:
        return None

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError:
        return None
    try:
        max_age = int(os.getenv("WEBAPP_AUTH_MAX_AGE", "86400"))
    except ValueError:
        max_age = 86400
    if auth_date <= 0 or abs(int(time.time()) - auth_date) > max_age:
        return None

    try:
        user_data = json.loads(values.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    return user_data if isinstance(user_data, dict) and user_data.get("id") else None


def webapp_identity(payload: dict[str, Any], request: web.Request) -> tuple[int, str, str] | None:
    user_data = validate_telegram_init_data(str(payload.get("init_data") or ""))
    local_test_allowed = (
        not os.getenv("PORT")
        and os.getenv("WEBAPP_ALLOW_LOCAL_TEST", "1").strip().lower() not in {"0", "false", "yoq"}
    )
    if (
        user_data is None
        and local_test_allowed
        and request.remote in {"127.0.0.1", "::1", "localhost"}
    ):
        fallback = payload.get("user")
        if isinstance(fallback, dict) and fallback.get("id"):
            user_data = fallback
    if user_data is None:
        return None

    try:
        user_id = int(user_data["id"])
    except (KeyError, TypeError, ValueError):
        return None
    first_name = str(user_data.get("first_name") or "").strip()
    last_name = str(user_data.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part) or f"User {user_id}"
    username = str(user_data.get("username") or "").strip().lstrip("@")
    return user_id, full_name, username


async def webapp_json(request: web.Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, web.HTTPBadRequest):
        return None
    return payload if isinstance(payload, dict) else None


def portfolio_cases() -> list[dict[str, str]]:
    return [
        {
            "title": "Restoran buyurtma boti",
            "description": "Menyu, savatcha, naqd to'lov, filial va kurerga buyurtma uzatish oqimi.",
        },
        {
            "title": "Kurer boshqaruv tizimi",
            "description": "Buyurtmalarni kurerlarga biriktirish, statuslar va admin nazorati.",
        },
        {
            "title": "Korporativ veb-sayt",
            "description": "Xizmatlar katalogi, murojaat formasi, yangiliklar va boshqaruv paneli.",
        },
        {
            "title": "Savdo CRM",
            "description": "Mijozlar bazasi, lead pipeline, vazifalar, hisobot va xodim rollari.",
        },
        {
            "title": "Mobil xizmat MVP",
            "description": "Android/iOS mijoz profili, xizmat buyurtmasi, bildirishnomalar va API.",
        },
    ]


async def webapp_order_api(request: web.Request) -> web.Response:
    payload = await webapp_json(request)
    if payload is None:
        return web.json_response({"error": "Noto'g'ri JSON so'rov."}, status=400)
    identity = webapp_identity(payload, request)
    if identity is None:
        return web.json_response({"error": "Telegram foydalanuvchisi tasdiqlanmadi."}, status=401)

    project = str(payload.get("project") or "").strip()
    requirements = str(payload.get("requirements") or "").strip()
    user_id, full_name, username = identity
    if is_blocked_user(user_id):
        return web.json_response({"error": "Profilingiz vaqtincha bloklangan."}, status=403)

    try:
        project_key = normalize_project_key(project)
        if project_key not in PROJECT_PRICES:
            raise ValueError("Loyiha turi noto'g'ri.")
        analysis_session = UserSession(
            selected_projects={project_key},
            requirements=normalize_payment_policy_text(requirements),
        )
        validation = await validate_requirements_with_ai(analysis_session)
        if not validation.enough:
            raise ValueError(validation.reply)
        analysis = await estimate_with_ai(analysis_session)
        track_web_user(user_id, full_name, username)
        order = create_web_order(
            user_id,
            full_name,
            username,
            project_key,
            requirements,
            analysis=analysis,
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    bot: Bot = request.app["bot"]
    session = reset_session(user_id)
    session.stage = "payment_confirmation"
    session.selected_projects = {project_key}
    session.requirements = order["requirements"]
    session.estimate = int(order["estimate"])
    session.prepayment = int(order["prepayment"])
    session.order_id = int(order["id"])
    session.ai_summary = str(order["ai_summary"])
    session.ai_features = json.loads(order["ai_features"] or "[]")
    session.ai_used = bool(order["ai_used"])
    session.estimated_duration = str(order["estimated_duration"])
    session.lead_score = str(order["lead_score"])
    try:
        await bot.send_message(
            user_id,
            f"Web App buyurtmangiz #{order['id']} qabul qilindi.\n"
            f"Loyiha: {projects_from_order(order)}\n"
            f"Taxminiy narx: ${order['estimate']}\n"
            f"Boshlash uchun 50% predoplata: ${order['prepayment']}\n\n"
            "Loyiha boshlanishi uchun kelishilgan summaning yarmi (50% predoplata) "
            "plastik karta orqali qabul qilinadi. To'lov qilishga rozimisiz?",
            reply_markup=payment_keyboard(),
        )
    except Exception as exc:
        logging.warning("Web App buyurtma xabari mijozga yuborilmadi: %s", exc)
    await notify_admins(
        bot,
        f"Web App orqali yangi buyurtma #{order['id']}\n"
        f"Mijoz: {full_name} (@{username or 'username yoq'})\n"
        f"Loyiha: {projects_from_order(order)}\n"
        f"Narx: ${order['estimate']}, predoplata: ${order['prepayment']}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Buyurtmani ko'rish", callback_data=f"panel:order:{order['id']}")]
            ]
        ),
        permission="orders",
    )
    return web.json_response(
        {
            "order_id": order["id"],
            "estimate": order["estimate"],
            "prepayment": order["prepayment"],
            "duration": order["estimated_duration"],
        }
    )


async def webapp_status_api(request: web.Request) -> web.Response:
    payload = await webapp_json(request)
    if payload is None:
        return web.json_response({"error": "Noto'g'ri JSON so'rov."}, status=400)
    identity = webapp_identity(payload, request)
    if identity is None:
        return web.json_response({"error": "Telegram foydalanuvchisi tasdiqlanmadi."}, status=401)
    order = latest_order_for_user(identity[0])
    if order is None:
        return web.json_response({"order": None})
    return web.json_response(
        {
            "order": {
                "id": order["id"],
                "project": projects_from_order(order),
                "status": STATUS_LABELS.get(order["status"], order["status"]),
                "pipeline": PIPELINE_STAGES.get(order["pipeline_stage"], order["pipeline_stage"]),
                "estimate": order["estimate"],
                "prepayment": order["prepayment"],
                "duration": order["estimated_duration"],
            }
        }
    )


async def webapp_portfolio_api(request: web.Request) -> web.Response:
    return web.json_response({"items": portfolio_cases()})


async def webapp_support_api(request: web.Request) -> web.Response:
    payload = await webapp_json(request)
    if payload is None:
        return web.json_response({"error": "Noto'g'ri JSON so'rov."}, status=400)
    identity = webapp_identity(payload, request)
    if identity is None:
        return web.json_response({"error": "Telegram foydalanuvchisi tasdiqlanmadi."}, status=401)
    message = str(payload.get("message") or "").strip()
    if len(message) < 10:
        return web.json_response({"error": "Murojaatni batafsilroq yozing."}, status=400)

    user_id, full_name, username = identity
    track_web_user(user_id, full_name, username)
    ticket_id = create_web_support_ticket(user_id, full_name, username, message)
    await notify_admins(
        request.app["bot"],
        f"Web App support ticket #{ticket_id}\n"
        f"Mijoz: {full_name} (@{username or 'username yoq'})\n"
        f"Xabar: {message}",
        permission="support",
    )
    return web.json_response({"ticket_id": ticket_id})


def web_layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;background:#f6f7f9;color:#111}"
        "table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ddd;padding:8px;text-align:left}"
        "a{color:#0b66c3}.card{background:white;padding:16px;border:1px solid #ddd;margin:12px 0}"
        ".kanban{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:12px 0}"
        ".lane{background:white;border:1px solid #ddd;padding:10px}.lane h2{font-size:15px;margin:0 0 8px}"
        ".deal{display:block;border-top:1px solid #eee;padding:8px 0;font-size:13px}</style>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


async def web_app_page(request: web.Request) -> web.StreamResponse:
    if WEBAPP_HTML_PATH.exists():
        return web.FileResponse(WEBAPP_HTML_PATH)
    return web.Response(text="Web app sahifasi topilmadi", status=404)


async def webapp_static(request: web.Request) -> web.StreamResponse:
    filename = request.match_info["filename"]
    if filename not in {"styles.css", "app.js"}:
        return web.Response(text="Not found", status=404)
    path = WEBAPP_ROOT / filename
    if not path.exists():
        return web.Response(text="Not found", status=404)
    return web.FileResponse(path)


async def web_index(request: web.Request) -> web.Response:
    if not web_authorized(request):
        return web.Response(text="Unauthorized", status=401)
    token_param = f"?token={html.escape(request.query.get('token', ''))}" if request.query.get("token") else ""
    rows = latest_orders(limit=50)
    stats = html.escape(format_stats_text()).replace("\n", "<br>")
    kanban_columns = []
    for stage, title in PIPELINE_STAGES.items():
        cards = []
        for order in latest_orders_by_pipeline(stage, limit=5):
            cards.append(
                "<a class='deal' "
                f"href='/admin/order/{order['id']}{token_param}'>"
                f"#{order['id']} - {html.escape(order['full_name'])}<br>"
                f"${order['estimate']} - {html.escape(order['lead_score'] or '-')}"
                "</a>"
            )
        if not cards:
            cards.append("<span class='deal'>buyurtma yo'q</span>")
        kanban_columns.append(
            f"<section class='lane'><h2>{html.escape(title)}</h2>{''.join(cards)}</section>"
        )
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
        f"<div class='kanban'>{''.join(kanban_columns)}</div>"
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


async def web_healthz(request: web.Request) -> web.Response:
    """Railway/monitoring uchun health endpoint — DB va Redis holatini tekshiradi."""
    try:
        with db_connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return web.json_response(
            {
                "status": "ok",
                "backend": "postgres" if IS_POSTGRES else "sqlite",
                "redis": _redis is not None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"status": "error", "detail": str(exc)}, status=503)


async def start_web_admin(
    bot: Bot,
    dp: Dispatcher | None = None,
    webhook_path: str | None = None,
    webhook_secret: str | None = None,
) -> web.AppRunner | None:
    railway_port = os.getenv("PORT")
    admin_enabled = os.getenv("WEB_ADMIN_ENABLED", "1").strip() not in {"0", "false", "False", "yoq"}
    # Webhook rejimida web server doim kerak (Telegram update'larini qabul qiladi).
    if not railway_port and not admin_enabled and not webhook_path:
        return None
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/healthz", web_healthz)
    # Webhook rejimi yoqilgan bo'lsa, Telegram update handler'ini ro'yxatdan o'tkazamiz.
    if webhook_path and dp is not None:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler

        SimpleRequestHandler(
            dispatcher=dp, bot=bot, secret_token=webhook_secret
        ).register(app, path=webhook_path)
        logging.info("Webhook handler ro'yxatdan o'tdi: %s", webhook_path)
    app.router.add_get("/", web_app_page)
    app.router.add_get("/app", web_app_page)
    app.router.add_get("/app/{filename}", webapp_static)
    app.router.add_post("/api/webapp/order", webapp_order_api)
    app.router.add_post("/api/webapp/status", webapp_status_api)
    app.router.add_get("/api/webapp/portfolio", webapp_portfolio_api)
    app.router.add_post("/api/webapp/support", webapp_support_api)
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
    # Railway public domeni mavjud bo'lsa, log'da o'sha ko'rsatiladi (localhost emas).
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if public_domain:
        base_url = f"https://{public_domain}"
    else:
        base_url = f"http://{host}:{port}"
    logging.info("Web server ishga tushdi: %s/ (web app)", base_url)
    if admin_enabled:
        admin_token = os.getenv("WEB_ADMIN_TOKEN", "").strip()
        admin_suffix = f"?token={admin_token}" if admin_token else ""
        logging.info("Web admin panel: %s/admin%s", base_url, admin_suffix)
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
        attach_pending_files(user.id, session.order_id)
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
            permission="orders",
        )


async def process_customer_project_text(
    message: Message,
    text: str,
    session: UserSession,
    bot: Bot,
) -> None:
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

    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=sentry_dsn,
                traces_sample_rate=0.0,
                environment=os.getenv("SENTRY_ENV", "production"),
            )
            globals()["_sentry"] = sentry_sdk
            logging.info("Sentry xato kuzatuvi yoqildi")
        except Exception as exc:  # noqa: BLE001
            logging.warning("Sentry yoqilmadi: %s", exc)

    init_db()

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan.")

    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # Webhook konfiguratsiyasi (ixtiyoriy — default polling).
    use_webhook = os.getenv("USE_WEBHOOK", "0").strip() in {"1", "true", "True", "ha"}
    webhook_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip() or os.getenv("PUBLIC_DOMAIN", "").strip()
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip() or hashlib.sha256(bot_token.encode()).hexdigest()[:40]
    webhook_active = bool(use_webhook and webhook_domain)
    webhook_path = f"/webhook/{webhook_secret}"
    if use_webhook and not webhook_domain:
        logging.warning("USE_WEBHOOK=1, lekin public domen yo'q — polling rejimida ishlaymiz")

    @dp.errors()
    async def on_error(event: Any) -> bool:
        exc = getattr(event, "exception", None)
        logging.exception("Handler xatosi: %s", exc)
        sentry = globals().get("_sentry")
        if sentry is not None and exc is not None:
            sentry.capture_exception(exc)
        return True

    security_middleware = SecurityMiddleware()
    dp.message.middleware(security_middleware)
    dp.callback_query.middleware(security_middleware)
    await setup_bot_commands(bot)
    await setup_menu_button(bot)
    web_runner = await start_web_admin(
        bot,
        dp=dp if webhook_active else None,
        webhook_path=webhook_path if webhook_active else None,
        webhook_secret=webhook_secret if webhook_active else None,
    )
    reminder_task = asyncio.create_task(reminder_loop(bot))
    monitor_task = asyncio.create_task(monitoring_loop(bot))
    await notify_admins(bot, "ZettaCode Tech bot ishga tushdi.\n\n" + health_text())

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if is_admin_user(message.from_user.id):
            await show_admin_panel(message)
            return
        session = reset_session(message.from_user.id)
        start_args = command_args(message)
        if start_args.startswith("ref_") and apply_referral_code(message.from_user.id, start_args[4:]):
            set_session_promo(session, "START5")
            await message.answer("Referral havola qabul qilindi. 5% promo faollashdi.")
        # Birinchi marta — til tanlash (onboarding). Tanlangach menyu ko'rsatiladi.
        if not is_language_chosen(message.from_user.id):
            await message.answer(
                "🌐 " + " / ".join(t("choose_language", code) for code in SUPPORTED_LANGUAGES),
                reply_markup=language_keyboard(),
            )
            return
        await show_main_menu(message, user_id=message.from_user.id)

    @dp.message(Command("language"))
    async def language_handler(message: Message) -> None:
        await message.answer(
            "🌐 " + " / ".join(t("choose_language", code) for code in SUPPORTED_LANGUAGES),
            reply_markup=language_keyboard(),
        )

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

    @dp.message(Command("calc"))
    async def calculator_handler(message: Message) -> None:
        if is_admin_user(message.from_user.id):
            await message.answer(
                "Siz adminsiz. Kalkulyatorni mijoz sifatida sinash uchun admin paneldagi "
                "`Mijoz sifatida test` tugmasidan foydalaning.",
                reply_markup=admin_panel_keyboard(),
            )
            return
        await show_project_menu(
            message,
            user_id=message.from_user.id,
            reset=True,
            calculator_mode=True,
        )

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

    @dp.message(Command("timeline"))
    async def timeline_handler(message: Message) -> None:
        args = command_args(message)
        if is_admin_user(message.from_user.id) and args:
            if not args.isdigit():
                await message.answer("Timeline olish: /timeline BUYURTMA_ID")
                return
            order = get_order(int(args))
        else:
            order = latest_order_for_user(message.from_user.id)
        if order is None:
            await message.answer("Timeline uchun buyurtma topilmadi.")
            return
        await message.answer(format_order_timeline(order))

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

    @dp.message(Command("contract"))
    async def contract_handler(message: Message) -> None:
        args = command_args(message)
        if is_admin_user(message.from_user.id) and args:
            if not args.isdigit():
                await message.answer("Shartnoma olish: /contract BUYURTMA_ID")
                return
            order = get_order(int(args))
        else:
            order = latest_order_for_user(message.from_user.id)
        if order is None:
            await message.answer("Shartnoma uchun buyurtma topilmadi.")
            return
        await send_contract_pdf(message, order)

    @dp.message(Command("support"))
    async def support_handler(message: Message) -> None:
        text = command_args(message)
        if not text:
            session = get_session(message.from_user.id)
            session.stage = "support_message"
            await message.answer("Support murojaatingizni batafsil yozing.")
            return
        ticket_id = create_support_ticket(message.from_user, text)
        await message.answer(f"Support murojaatingiz qabul qilindi. Ticket #{ticket_id}.")
        await notify_admins(
            bot,
            f"Yangi support ticket #{ticket_id}\n"
            f"Mijoz: {message.from_user.full_name} (@{message.from_user.username or 'username yoq'})\n"
            f"Xabar: {text}",
            permission="support",
        )

    @dp.message(Command("meeting"))
    async def meeting_handler(message: Message) -> None:
        value = command_args(message)
        try:
            local_datetime = datetime.strptime(value, "%Y-%m-%d %H:%M")
            local_timezone = datetime.now().astimezone().tzinfo
            scheduled = local_datetime.replace(tzinfo=local_timezone).astimezone(timezone.utc)
        except ValueError:
            await message.answer("Uchrashuv formati: /meeting YYYY-MM-DD HH:MM")
            return
        if scheduled <= datetime.now(timezone.utc):
            await message.answer("Uchrashuv vaqti kelajakda bo'lishi kerak.")
            return
        appointment_id = create_appointment(message.from_user, scheduled.isoformat())
        await message.answer(
            f"Uchrashuv so'rovi qabul qilindi: #{appointment_id}\n"
            f"Vaqt: {value}\nAdmin tasdiqlashini kuting."
        )
        await notify_admins(
            bot,
            f"Yangi uchrashuv so'rovi #{appointment_id}\n"
            f"Mijoz: {message.from_user.full_name} (@{message.from_user.username or 'username yoq'})\n"
            f"Vaqt: {value}",
            permission="meeting",
        )

    @dp.message(Command("referral"))
    async def referral_handler(message: Message) -> None:
        code = referral_code_for_user(message.from_user.id)
        total, rewarded = referral_stats(message.from_user.id)
        me = await bot.get_me()
        await message.answer(
            f"Referral kodingiz: {code}\n"
            f"Havola: https://t.me/{me.username}?start=ref_{code}\n"
            f"Taklif qilinganlar: {total}\n"
            f"Mukofotlanganlar: {rewarded}"
        )

    @dp.message(Command("ref"))
    async def ref_handler(message: Message) -> None:
        code = command_args(message)
        if not code:
            await message.answer("Referral kodni shunday yuboring: /ref ZETTA123")
            return
        if not apply_referral_code(message.from_user.id, code):
            await message.answer("Referral kod noto'g'ri, o'zingizniki yoki avval ishlatilgan.")
            return
        session = get_session(message.from_user.id)
        set_session_promo(session, "START5")
        await message.answer("Referral kod qabul qilindi. Keyingi hisoblash uchun 5% promo faollashdi.")

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

    @dp.message(Command("dashboard"))
    async def dashboard_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "report"):
            await message.answer("Bu command uchun hisobot ruxsati kerak.")
            return
        await message.answer(format_deep_dashboard(), reply_markup=admin_panel_keyboard())

    @dp.message(Command("kanban"))
    async def kanban_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await send_long_message(message, format_kanban_text())

    @dp.message(Command("customer"))
    async def customer_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        identifier = command_args(message)
        if not identifier:
            await message.answer("Mijoz kartasi: /customer USER_ID yoki /customer @username")
            return
        await message.answer(format_customer_card(identifier))

    @dp.message(Command("lead"))
    async def lead_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("Lead scoring: /lead BUYURTMA_ID")
            return
        order = get_order(int(order_id_text))
        if order is None:
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer(
            f"Buyurtma #{order['id']} lead scoring 2.0:\n\n"
            f"Daraja: {order['lead_score'] or '-'}\n"
            f"Narx: ${order['estimate']}\n"
            f"Status: {STATUS_LABELS.get(order['status'], order['status'])}\n"
            f"CRM: {PIPELINE_STAGES.get(order['pipeline_stage'], order['pipeline_stage'])}"
        )

    @dp.message(Command("risk"))
    async def risk_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("Risk tahlil: /risk BUYURTMA_ID")
            return
        order = get_order(int(order_id_text))
        if order is None:
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer("Risk tahlil tayyorlanyapti...")
        await send_long_message(message, await ai_project_risk(order))

    @dp.message(Command("feedbacks"))
    async def feedbacks_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await send_long_message(message, format_feedbacks_text())

    @dp.message(Command("blackliststats"))
    async def blacklist_stats_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(format_blacklist_stats())

    @dp.message(Command("ai"))
    async def ai_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(ai_status_text(), reply_markup=admin_panel_keyboard())

    @dp.message(Command("aireport"))
    async def ai_report_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "report"):
            await message.answer("Bu command uchun hisobot ruxsati kerak.")
            return
        await message.answer("AI savdo hisoboti tayyorlanyapti...")
        await send_long_message(message, await ai_sales_report())

    @dp.message(Command("health"))
    async def health_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(health_text(), reply_markup=admin_panel_keyboard())

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
        log_audit(message.from_user.id, "note_add", "order", order_id, note)
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
        if args[1] == "done":
            update_order_status(order_id, "delivered")
        log_audit(message.from_user.id, "pipeline_change", "order", order_id, args[1])
        if args[1] == "done":
            order = get_order(order_id)
            if order is not None:
                try:
                    await send_delivery_flow(bot, order)
                except Exception as exc:
                    logging.warning("Delivery flow yuborilmadi: %s", exc)
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
        log_audit(message.from_user.id, "task_add", "order", order_id, args[1])
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

    @dp.message(Command("files"))
    async def files_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("Fayllar: /files BUYURTMA_ID")
            return
        files = order_files(int(order_id_text))
        if not files:
            await message.answer("Bu buyurtmada fayllar yo'q.")
            return
        for item in files:
            if item["file_type"] == "photo":
                await message.answer_photo(item["file_id"], caption=item["file_name"] or "Loyiha rasmi")
            else:
                await message.answer_document(item["file_id"], caption=item["file_name"] or "Loyiha fayli")

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
        log_audit(message.from_user.id, "task_done", "task", int(task_id_text))
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
        log_audit(message.from_user.id, "deadline_set", "order", order_id, args[1])
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
        log_audit(message.from_user.id, "assignee_set", "order", order_id, args[1])
        await message.answer(f"Buyurtma #{order_id} mas'ul: {args[1]}")

    @dp.message(Command("templates"))
    async def templates_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        target = command_args(message)
        lines = ["Quick reply shablonlari:"]
        lines.extend(f"- {key}: {value}" for key, value in ADMIN_REPLY_TEMPLATES.items())
        if target and target.lstrip("@").isdigit():
            await message.answer(
                "\n".join(lines) + "\n\nShablonni yuborish uchun tugmani bosing.",
                reply_markup=template_keyboard(int(target.lstrip("@"))),
            )
            return
        await message.answer("\n".join(lines) + "\n\nYuborish: /sendtemplate USER_ID KEY")

    @dp.message(Command("sendtemplate"))
    async def send_template_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit() or args[1] not in ADMIN_REPLY_TEMPLATES:
            await message.answer("Shablon yuborish: /sendtemplate USER_ID price|receipt|deadline|requirements|prepayment")
            return
        user_id = int(args[0])
        template_key = args[1]
        await bot.send_message(user_id, ADMIN_REPLY_TEMPLATES[template_key])
        log_audit(message.from_user.id, "template_send", "user", user_id, template_key)
        await message.answer(f"Shablon yuborildi: {template_key}")

    @dp.message(Command("postdraft"))
    async def post_draft_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        if not order_id_text.isdigit():
            await message.answer("Post draft: /postdraft BUYURTMA_ID")
            return
        order = get_order(int(order_id_text))
        if order is None:
            await message.answer("Buyurtma topilmadi.")
            return
        await message.answer("Portfolio post draft tayyorlanyapti...")
        post = await ai_portfolio_case(order)
        await send_long_message(message, post)
        await message.answer("Kanalga chiqarilsinmi?", reply_markup=post_confirm_keyboard(order["id"]))

    @dp.message(Command("web"))
    async def web_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        await message.answer(f"Web admin panel:\n{web_admin_url()}")

    @dp.message(Command("audit"))
    async def audit_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        order_id_text = command_args(message)
        order_id = int(order_id_text) if order_id_text.isdigit() else None
        rows = latest_audit_logs(order_id=order_id)
        if not rows:
            await message.answer("Audit yozuvlari topilmadi.")
            return
        lines = ["Audit log:"]
        lines.extend(
            f"#{row['id']} | admin {row['admin_id']} | {row['action']} | "
            f"{row['entity_type']}:{row['entity_id'] or '-'} | {row['details']}"
            for row in rows
        )
        await send_long_message(message, "\n".join(lines))

    @dp.message(Command("tickets"))
    async def tickets_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "support"):
            await message.answer("Bu command uchun support ruxsati kerak.")
            return
        rows = latest_support_tickets(command_args(message) or "open")
        if not rows:
            await message.answer("Support ticketlar topilmadi.")
            return
        lines = ["Support ticketlar:"]
        lines.extend(
            f"#{row['id']} | {row['status']} | {row['full_name']} (@{row['username'] or 'username yoq'})\n"
            f"{row['message'][:180]}"
            for row in rows
        )
        await send_long_message(message, "\n\n".join(lines))

    @dp.message(Command("reply"))
    async def reply_ticket_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "support"):
            await message.answer("Bu command uchun support ruxsati kerak.")
            return
        args = command_args(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await message.answer("Ticketga javob: /reply TICKET_ID javob matni")
            return
        ticket = reply_support_ticket(int(args[0]), args[1])
        if ticket is None:
            await message.answer("Ticket topilmadi.")
            return
        await bot.send_message(
            ticket["user_id"],
            f"Support ticket #{ticket['id']} javobi:\n\n{args[1]}",
        )
        log_audit(message.from_user.id, "ticket_reply", "ticket", ticket["id"], args[1])
        await message.answer(f"Ticket #{ticket['id']}ga javob yuborildi.")

    @dp.message(Command("closeticket"))
    async def close_ticket_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "support"):
            await message.answer("Bu command uchun support ruxsati kerak.")
            return
        ticket_id_text = command_args(message)
        if not ticket_id_text.isdigit() or not close_support_ticket(int(ticket_id_text)):
            await message.answer("Ticket topilmadi.")
            return
        log_audit(message.from_user.id, "ticket_close", "ticket", int(ticket_id_text))
        await message.answer(f"Ticket #{ticket_id_text} yopildi.")

    @dp.message(Command("meetings"))
    async def meetings_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "meeting"):
            await message.answer("Bu command uchun meeting ruxsati kerak.")
            return
        rows = latest_appointments(command_args(message) or "pending")
        if not rows:
            await message.answer("Uchrashuvlar topilmadi.")
            return
        lines = ["Uchrashuvlar:"]
        for row in rows:
            local_time = datetime.fromisoformat(row["scheduled_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"#{row['id']} | {row['status']} | {local_time} | "
                f"{row['full_name']} (@{row['username'] or 'username yoq'})"
            )
        await message.answer("\n".join(lines))

    @dp.message(Command("confirmmeeting"))
    async def confirm_meeting_handler(message: Message) -> None:
        if not has_permission(message.from_user.id, "meeting"):
            await message.answer("Bu command uchun meeting ruxsati kerak.")
            return
        appointment_id_text = command_args(message)
        if not appointment_id_text.isdigit():
            await message.answer("Tasdiqlash: /confirmmeeting ID")
            return
        appointment = update_appointment_status(int(appointment_id_text), "confirmed")
        if appointment is None:
            await message.answer("Uchrashuv topilmadi.")
            return
        local_time = datetime.fromisoformat(appointment["scheduled_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
        await bot.send_message(
            appointment["user_id"],
            f"Uchrashuv #{appointment['id']} tasdiqlandi.\nVaqt: {local_time}",
        )
        log_audit(message.from_user.id, "meeting_confirm", "appointment", appointment["id"])
        await message.answer(f"Uchrashuv #{appointment['id']} tasdiqlandi.")

    @dp.message(Command("role"))
    async def role_handler(message: Message) -> None:
        if admin_role(message.from_user.id) != "super_admin":
            await message.answer("Faqat super admin rol bera oladi.")
            return
        args = command_args(message).split(maxsplit=1)
        allowed_roles = {"super_admin", "sales", "developer", "payment"}
        if len(args) != 2 or not args[0].isdigit() or args[1] not in allowed_roles:
            await message.answer("Rol berish: /role USER_ID super_admin|sales|developer|payment")
            return
        set_admin_role(int(args[0]), args[1], message.from_user.id)
        log_audit(message.from_user.id, "role_set", "admin", int(args[0]), args[1])
        await setup_bot_commands(bot)
        await message.answer(f"User {args[0]} uchun rol: {args[1]}")

    @dp.message(Command("admins"))
    async def admins_handler(message: Message) -> None:
        if not is_admin_user(message.from_user.id):
            await message.answer("Bu command faqat admin uchun.")
            return
        roles = configured_admin_roles()
        lines = ["Admin rollari:"]
        lines.extend(f"- {user_id}: {role}" for user_id, role in roles.items())
        await message.answer("\n".join(lines))

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
        log_audit(message.from_user.id, "user_block", "user", user_id, parts[1] if len(parts) == 2 else "")
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
        log_audit(message.from_user.id, "user_unblock", "user", int(user_id_text))
        await message.answer(f"User {user_id_text} blokdan chiqarildi.")

    @dp.callback_query(F.data.startswith("setlang:"))
    async def setlang_callback(callback: CallbackQuery) -> None:
        lang = callback.data.split(":", 1)[1]
        set_user_language(callback.from_user.id, lang)
        await callback.answer()
        if callback.message:
            try:
                await callback.message.delete()
            except Exception:  # noqa: BLE001
                pass
            await callback.message.answer(t("language_set", lang))
            await show_main_menu(callback.message, user_id=callback.from_user.id)

    @dp.callback_query(F.data == "checksub")
    async def checksub_callback(callback: CallbackQuery) -> None:
        if await is_user_subscribed(callback.bot, callback.from_user.id):
            await callback.answer("Rahmat! Endi botdan foydalanishingiz mumkin.", show_alert=True)
            try:
                if callback.message:
                    await callback.message.delete()
            except Exception:  # noqa: BLE001
                pass
            if callback.message:
                await callback.message.answer("Asosiy menyu uchun /start ni bosing.")
        else:
            await callback.answer(
                "Hali obuna bo'lmadingiz. Kanalga obuna bo'lib, qayta bosing.",
                show_alert=True,
            )

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

        if action == "calculator":
            if is_admin_user(callback.from_user.id):
                await callback.message.answer(
                    "Siz adminsiz. Kalkulyatorni mijoz sifatida sinash uchun admin paneldagi "
                    "`Mijoz sifatida test` tugmasidan foydalaning.",
                    reply_markup=admin_panel_keyboard(),
                )
                await callback.answer()
                return
            await show_project_menu(
                callback.message,
                user_id=callback.from_user.id,
                reset=True,
                calculator_mode=True,
            )
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

        if action == "example":
            await callback.message.answer(requirements_example_text())
            await callback.answer("Namuna yuborildi.")
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
        session.calculator_mode = current_session.calculator_mode
        session.selected_projects.add(project_key)
        await ask_for_more_requirements(
            callback.message,
            session,
            calculator_prompt_for_session(session)
            if session.calculator_mode
            else f"{PROJECT_PRICES[project_key][0]} tanlandi. Endi loyiha nima vazifalarni bajarishini batafsil yozing.",
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

        if action == "kanban":
            await safe_edit_or_answer(
                callback,
                format_kanban_text(),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "dashboard":
            await safe_edit_or_answer(
                callback,
                format_deep_dashboard(),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "feedbacks":
            await safe_edit_or_answer(
                callback,
                format_feedbacks_text(),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "blackliststats":
            await safe_edit_or_answer(
                callback,
                format_blacklist_stats(),
                reply_markup=admin_panel_keyboard(),
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
            if stage == "done":
                update_order_status(order_id, "delivered")
            log_audit(callback.from_user.id, "pipeline_change", "order", order_id, stage)
            order = get_order(order_id)
            if stage == "done" and order is not None:
                try:
                    await send_delivery_flow(bot, order)
                except Exception as exc:
                    logging.warning("Delivery flow yuborilmadi: %s", exc)
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

        if action == "contract" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await send_contract_pdf(callback.message, order)
            await callback.answer("Shartnoma yuborildi.")
            return

        if action == "portfolio" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer(
                portfolio_text(portfolio_category_for_order(order)),
                reply_markup=portfolio_keyboard(),
            )
            await callback.answer("Mos portfolio yuborildi.")
            return

        if action == "timeline" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer(format_order_timeline(order))
            await callback.answer("Timeline yuborildi.")
            return

        if action == "risk" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer("Risk tahlil tayyorlanyapti...")
            await send_long_message(callback.message, await ai_project_risk(order))
            await callback.answer("Risk tahlil yuborildi.")
            return

        if action == "customer" and len(parts) == 3:
            await callback.message.answer(format_customer_card(parts[2]))
            await callback.answer("Mijoz kartasi yuborildi.")
            return

        if action == "templates" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer(
                "Mijozga qaysi reply shablon yuborilsin?",
                reply_markup=template_keyboard(order["user_id"], order["id"]),
            )
            await callback.answer()
            return

        if action == "postdraft" and len(parts) == 3:
            try:
                order_id = int(parts[2])
            except ValueError:
                await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
                return
            order = get_order(order_id)
            if order is None:
                await callback.answer("Buyurtma topilmadi.", show_alert=True)
                return
            await callback.message.answer("Portfolio post draft tayyorlanyapti...")
            post = await ai_portfolio_case(order)
            await send_long_message(callback.message, post)
            await callback.message.answer("Kanalga chiqarilsinmi?", reply_markup=post_confirm_keyboard(order["id"]))
            await callback.answer("Post draft yuborildi.")
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
            log_audit(callback.from_user.id, "broadcast_send", "broadcast", None, text[:200])
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
                calculator_prompt_for_session(session)
                if session.calculator_mode
                else "Loyihangiz to'liq qanday ishlashi va nima vazifalarni bajarishi kerakligini batafsil yozib bering.",
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

        if action == "example":
            await callback.message.answer(requirements_example_text())
            await callback.answer("Namuna yuborildi.")
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

    @dp.message(F.voice)
    async def voice_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        if is_admin_user(message.from_user.id) and not session.is_admin_test:
            await show_admin_panel(message)
            return
        if session.stage not in ("choose_project", "collect_requirements"):
            await message.answer("Ovozli talab yuborish uchun avval /new orqali buyurtma boshlang.")
            return
        await message.answer("Ovozli xabaringiz matnga aylantirilyapti...")
        try:
            text = await transcribe_voice(bot, message.voice.file_id)
        except Exception as exc:
            logging.warning("Ovozli xabar tahlil qilinmadi: %s", exc)
            await message.answer("Ovozli xabarni tushunib bo'lmadi. Iltimos, qayta yuboring yoki matn yozing.")
            return
        if not text:
            await message.answer("Ovozli xabarda matn topilmadi.")
            return
        await message.answer(f"Ovozdan olingan matn:\n{text}")
        await process_customer_project_text(message, text, session, bot)

    @dp.message(F.document)
    async def document_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        if is_admin_user(message.from_user.id) and not session.is_admin_test:
            await show_admin_panel(message)
            return
        if session.stage == "awaiting_receipt":
            await message.answer("To'lov chekini hujjat emas, rasm holatida yuboring.")
            return
        if session.stage not in ("choose_project", "collect_requirements"):
            await message.answer("Fayl yuborish uchun avval /new orqali buyurtma boshlang.")
            return
        document = message.document
        save_project_file(
            message.from_user.id,
            document.file_id,
            "document",
            document.file_name or "document",
            session.order_id,
        )
        await message.answer(
            f"Fayl qabul qilindi: {document.file_name or 'document'}\n"
            "Endi loyiha nima qilishi kerakligini matn yoki ovoz bilan tushuntiring."
        )

    @dp.message(F.photo)
    async def photo_handler(message: Message) -> None:
        session = get_session(message.from_user.id)
        if session.stage == "checking":
            await message.answer(
                "To'lov chekingiz adminga yuborilgan. Iltimos, admin javobini kuting."
            )
            return

        if session.stage in ("choose_project", "collect_requirements"):
            save_project_file(
                message.from_user.id,
                message.photo[-1].file_id,
                "photo",
                "project_photo.jpg",
                session.order_id,
            )
            await message.answer(
                "Loyiha rasmi qabul qilindi. Endi rasm nimani anglatishi va loyiha qanday ishlashini yozing."
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

        admin_ids = admin_ids_for_permission("payment")
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
                permission="orders",
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

        if action == "contract":
            order = get_order(session.order_id) if session.order_id is not None else None
            if order is None:
                await callback.answer("Shartnoma uchun buyurtma topilmadi.", show_alert=True)
                return
            await send_contract_pdf(callback.message, order)
            await callback.answer("Shartnoma yuborildi.")
            return

        if action == "portfolio":
            await callback.message.answer(
                portfolio_text(portfolio_category_for_session(session)),
                reply_markup=portfolio_keyboard(),
            )
            await callback.answer("Mos portfolio yuborildi.")
            return

        await send_payment_details(callback.message, session)
        await callback.answer()

    @dp.callback_query(F.data.startswith("admin:"))
    async def admin_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(callback.from_user.id):
            await callback.answer("Bu tugma faqat admin uchun.", show_alert=True)
            return
        if not has_permission(callback.from_user.id, "payment"):
            await callback.answer("Sizda to'lovni tekshirish ruxsati yo'q.", show_alert=True)
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
            log_audit(callback.from_user.id, "payment_paid", "order", order_id)
            if session and session.order_id == order_id:
                session.stage = "completed"
            await bot.send_message(
                user_id,
                "To'lovingiz muvaffaqiyatli qabul qilindi! Barcha ma'lumotlar adminga yuborildi. "
                "Adminimiz siz bilan tez orada aloqaga chiqadi, iltimos javobni kuting.",
            )
            referrer_user_id = reward_referral_for_user(user_id)
            if referrer_user_id is not None:
                try:
                    await bot.send_message(
                        referrer_user_id,
                        "Referral orqali taklif qilgan mijozingiz buyurtma boshladi. Referral mukofotingiz qayd etildi.",
                    )
                except Exception:
                    pass
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.answer("Mijozga tasdiq xabari yuborildi.")
            return

        if action == "not_paid":
            update_order_status(order_id, "rejected")
            update_order_metadata(order_id, pipeline_stage="priced")
            log_audit(callback.from_user.id, "payment_rejected", "order", order_id)
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

    @dp.callback_query(F.data.startswith("feedback:"))
    async def feedback_callback(callback: CallbackQuery) -> None:
        parts = callback.data.split(":")
        if len(parts) < 4:
            await callback.answer()
            return
        action = parts[1]
        try:
            order_id = int(parts[2])
        except ValueError:
            await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
            return
        order = get_order(order_id)
        if order is None or int(order["user_id"]) != callback.from_user.id:
            await callback.answer("Bu feedback sizning buyurtmangiz uchun emas.", show_alert=True)
            return
        if action == "rate":
            try:
                rating = int(parts[3])
            except ValueError:
                await callback.answer("Baho noto'g'ri.", show_alert=True)
                return
            rating = min(5, max(1, rating))
            save_order_feedback(order_id, callback.from_user.id, rating=rating)
            await callback.message.answer(
                f"Rahmat, bahoyingiz qabul qilindi: {rating}/5.\n"
                "Qo'shimcha fikringiz bo'lsa, support orqali yozishingiz mumkin."
            )
            await notify_admins(
                bot,
                f"Feedback keldi: buyurtma #{order_id}\n"
                f"Mijoz: {callback.from_user.full_name} (@{callback.from_user.username or 'username yoq'})\n"
                f"Baho: {rating}/5",
                permission="report",
            )
            await callback.answer("Baho saqlandi.")
            return
        if action == "portfolio":
            permission = parts[3] == "yes"
            save_order_feedback(order_id, callback.from_user.id, portfolio_permission=permission)
            await callback.message.answer(
                "Portfolio ruxsatingiz saqlandi. Rahmat."
                if permission
                else "Portfolio uchun ruxsat berilmadi deb saqlandi."
            )
            await notify_admins(
                bot,
                f"Portfolio ruxsati: buyurtma #{order_id} - {'ha' if permission else 'yoq'}",
                permission="report",
            )
            await callback.answer("Ruxsat saqlandi.")
            return
        await callback.answer()

    @dp.callback_query(F.data.startswith("template:"))
    async def template_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(callback.from_user.id):
            await callback.answer("Bu tugma faqat admin uchun.", show_alert=True)
            return
        parts = callback.data.split(":")
        if len(parts) not in (4, 5) or parts[1] != "send":
            await callback.answer()
            return
        try:
            user_id = int(parts[2])
        except ValueError:
            await callback.answer("User ID noto'g'ri.", show_alert=True)
            return
        key = parts[3]
        if key not in ADMIN_REPLY_TEMPLATES:
            await callback.answer("Shablon topilmadi.", show_alert=True)
            return
        await bot.send_message(user_id, ADMIN_REPLY_TEMPLATES[key])
        entity_id = int(parts[4]) if len(parts) == 5 and parts[4].isdigit() else user_id
        log_audit(callback.from_user.id, "template_send", "order" if len(parts) == 5 else "user", entity_id, key)
        await callback.answer("Shablon yuborildi.")

    @dp.callback_query(F.data.startswith("post:"))
    async def post_callback(callback: CallbackQuery) -> None:
        if not is_admin_user(callback.from_user.id):
            await callback.answer("Bu tugma faqat admin uchun.", show_alert=True)
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer()
            return
        action = parts[1]
        try:
            order_id = int(parts[2])
        except ValueError:
            await callback.answer("Buyurtma ID noto'g'ri.", show_alert=True)
            return
        if action == "cancel":
            await callback.answer("Bekor qilindi.")
            return
        if action != "send":
            await callback.answer()
            return
        target = project_channel_target()
        if not target:
            await callback.answer("CHANNEL_USERNAME yoki PROJECT_CHANNEL_ID sozlanmagan.", show_alert=True)
            return
        order = get_order(order_id)
        if order is None:
            await callback.answer("Buyurtma topilmadi.", show_alert=True)
            return
        post = await ai_portfolio_case(order)
        await bot.send_message(target, post)
        log_audit(callback.from_user.id, "channel_post_send", "order", order_id)
        await callback.answer("Kanalga yuborildi.")

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
                log_audit(message.from_user.id, "note_add", "order", order_id, text)
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
                log_audit(message.from_user.id, "task_add", "order", order_id, text)
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

        if not is_admin_user(message.from_user.id) and session.stage == "support_message":
            ticket_id = create_support_ticket(message.from_user, text)
            session.stage = "choose_project"
            await message.answer(f"Support murojaatingiz qabul qilindi. Ticket #{ticket_id}.")
            await notify_admins(
                bot,
                f"Yangi support ticket #{ticket_id}\n"
                f"Mijoz: {message.from_user.full_name} (@{message.from_user.username or 'username yoq'})\n"
                f"Xabar: {text}",
                permission="support",
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

        if text == CALCULATOR_TEXT:
            if is_admin_user(message.from_user.id) and not session.is_admin_test:
                await message.answer(
                    "Siz adminsiz. Kalkulyatorni mijoz sifatida sinash uchun admin paneldagi "
                    "`Mijoz sifatida test` tugmasidan foydalaning.",
                    reply_markup=admin_panel_keyboard(),
                )
                return
            await show_project_menu(
                message,
                user_id=message.from_user.id,
                reset=True,
                calculator_mode=True,
            )
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
                    permission="orders",
                )
                return
            objection = detect_sales_objection(text)
            if objection is not None:
                await message.answer(
                    SALES_OBJECTION_REPLIES[objection] + "\n\nTo'lov qilishga rozimisiz?",
                    reply_markup=payment_keyboard(),
                )
                if session.order_id is not None:
                    log_audit(0, f"customer_objection_{objection}", "order", session.order_id, text[:200])
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
            await process_customer_project_text(message, text, session, bot)
            return

        await show_main_menu(message, user_id=message.from_user.id)

    try:
        started_webhook = False
        if webhook_active:
            try:
                webhook_url = f"https://{webhook_domain}{webhook_path}"
                await bot.set_webhook(
                    webhook_url,
                    secret_token=webhook_secret,
                    drop_pending_updates=False,
                )
                logging.info("Webhook rejimida ishlamoqda: %s", webhook_url)
                started_webhook = True
                await asyncio.Event().wait()  # web server update'larni qabul qiladi
            except Exception as exc:  # noqa: BLE001
                logging.error("Webhook o'rnatilmadi, polling'ga qaytamiz: %s", exc)
                started_webhook = False
        if not started_webhook:
            # Polling rejimi (default) — avval webhook bo'lsa o'chiramiz (konflikt bo'lmasin).
            try:
                await bot.delete_webhook(drop_pending_updates=False)
            except Exception:  # noqa: BLE001
                pass
            await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        monitor_task.cancel()
        await asyncio.gather(reminder_task, monitor_task, return_exceptions=True)
        if web_runner is not None:
            await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

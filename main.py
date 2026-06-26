import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Set

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    User,
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
    is_admin_test: bool = False
    asked_questions: int = 0
    off_topic_count: int = 0
    requirements_validated: bool = False


sessions: Dict[int, UserSession] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> str:
    return os.getenv("DB_PATH", "orders.db")


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(db_path())
    connection.row_factory = sqlite3.Row
    return connection


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


def create_order(user: User, session: UserSession) -> int:
    username = user.username or ""
    now = utc_now()
    with db_connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO orders (
                user_id, full_name, username, projects, requirements, estimate, prepayment,
                ai_summary, ai_features, ai_used, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def is_admin_user(user_id: int) -> bool:
    admin_id = admin_chat_id()
    return admin_id is not None and user_id == admin_id


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


def requirements_keyboard(has_requirements: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Yana talab qo'shish", callback_data="requirements:more")],
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
            ]
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
            [InlineKeyboardButton(text="Statistika", callback_data="panel:stats")],
            [InlineKeyboardButton(text="AI holati", callback_data="panel:ai_status")],
            [InlineKeyboardButton(text="Mijoz sifatida test", callback_data="panel:test_order")],
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
    features = json.loads(order["ai_features"] or "[]")
    feature_text = format_features(features) if features else "-"
    username = f"@{order['username']}" if order["username"] else "username yo'q"
    ai_label = "AI tahlil" if order["ai_used"] else "Tahlil"
    return (
        f"Buyurtma #{order['id']}\n\n"
        f"Holat: {status}\n"
        f"Mijoz ID: {order['user_id']}\n"
        f"Mijoz: {order['full_name']} ({username})\n"
        f"Loyiha turi: {projects_from_order(order)}\n"
        f"Taxminiy narx: ${order['estimate']}\n"
        f"50% predoplata: ${order['prepayment']}\n\n"
        f"{ai_label}: {order['ai_summary']}\n"
        f"Asosiy bandlar:\n{feature_text}\n\n"
        f"Talablar:\n{order['requirements']}"
    )


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


async def finalize_estimate(message: Message, user: User, session: UserSession) -> None:
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
    session.estimate = result.estimate
    session.prepayment = session.estimate // 2
    session.ai_summary = result.summary
    session.ai_features = result.features
    session.ai_used = result.ai_used
    if session.order_id is None:
        session.order_id = create_order(user, session)
    session.stage = "payment_confirmation"

    ai_label = "AI tahlil" if session.ai_used else "Tahlil"
    await message.answer(
        f"Tanlangan yo'nalish: {selected_project_titles(session)}\n"
        f"{ai_label}: {session.ai_summary}\n\n"
        f"Asosiy bandlar:\n{format_features(session.ai_features)}\n\n"
        f"Talablaringiz asosida taxminiy narx: ${session.estimate}\n"
        f"Boshlash uchun 50% predoplata: ${session.prepayment}\n\n"
        "Loyiha boshlanishi uchun kelishilgan summaning yarmi (50% predoplata) "
        "plastik karta orqali qabul qilinadi. To'lov qilishga rozimisiz?",
        reply_markup=payment_keyboard(),
    )


async def send_payment_details(message: Message, session: UserSession) -> None:
    card_number = os.getenv("CARD_NUMBER", "[Karta raqami]")
    card_holder = os.getenv("CARD_HOLDER", "TOSHMIRZA YUSUPOV")
    session.stage = "awaiting_receipt"
    update_order_status(session.order_id, "awaiting_receipt")
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

        if action == "home":
            if is_admin_user(callback.from_user.id):
                await show_admin_panel(callback.message)
            else:
                await show_main_menu(callback.message, user_id=callback.from_user.id)
            await callback.answer()
            return

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
            orders = latest_orders()
            if not orders:
                await safe_edit_or_answer(
                    callback,
                    "Hozircha buyurtmalar yo'q.",
                    reply_markup=orders_keyboard([]),
                )
            else:
                await safe_edit_or_answer(
                    callback,
                    "Oxirgi buyurtmalar:",
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

        if action == "stats":
            total, paid_sum, statuses = order_stats()
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
            await safe_edit_or_answer(
                callback,
                "\n".join(lines),
                reply_markup=admin_panel_keyboard(),
            )
            await callback.answer()
            return

        if action == "ai_status":
            api_key = os.getenv("GROQ_API_KEY")
            model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            status = "ulangan" if api_key else "ulanmagan"
            await safe_edit_or_answer(
                callback,
                f"AI holati: {status}\nModel: {model}",
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
            await finalize_estimate(callback.message, callback.from_user, session)
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

        admin_id = admin_chat_id()
        if admin_id is None:
            logging.warning("ADMIN_CHAT_ID sozlanmagan, chek adminga yuborilmadi.")
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
            session.stage = "admin_contact"
            await callback.message.answer(admin_contact_text())
            await callback.answer()
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
            await finalize_estimate(message, message.from_user, session)
            return

        normalized_text = text.lower().replace("'", "").replace("`", "")
        if session.stage == "payment_confirmation":
            if normalized_text in ("ha", "xa", "yes", "roziman"):
                await send_payment_details(message, session)
                return
            if is_prepayment_refusal(normalized_text):
                update_order_status(session.order_id, "admin_contact")
                session.stage = "admin_contact"
                await message.answer(admin_contact_text())
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
            await finalize_estimate(message, message.from_user, session)
            return

        await show_main_menu(message, user_id=message.from_user.id)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

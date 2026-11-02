
import asyncio
import json
import logging
import os
import re
import secrets
import sqlite3

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


# CONFIG
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "database.db"
LINKS_FILE = Path(__file__).resolve().parent / "exam_links.json"
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://127.0.0.1:5000").rstrip("/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())


# EXAM CONFIGURATION
GRADES = [str(grade) for grade in range(2, 10)]
GROUPS_PER_GRADE = 8

EXAM_TYPES = ["Exam", "Mini Exam"]
LANGUAGES = ["Rus", "Uzb"]


# JSON LINKS
def create_default_links():
    """Barcha sinf va guruhlar uchun bo'sh link shablonini yaratadi."""

    links = {}

    for exam_type in EXAM_TYPES:
        links[exam_type] = {}

        for language in LANGUAGES:
            links[exam_type][language] = {}

            for grade in GRADES:
                for number in range(1, GROUPS_PER_GRADE + 1):
                    group = f"{grade}.{number}"
                    links[exam_type][language][group] = ""

    return links


def init_links_file():
    """JSON fayli mavjud bo'lmasa, avtomatik yaratadi."""

    if not LINKS_FILE.exists():
        links = create_default_links()

        with LINKS_FILE.open("w", encoding="utf-8") as file:
            json.dump(
                links,
                file,
                ensure_ascii=False,
                indent=4,
            )

        logger.info("exam_links.json yaratildi!")


def get_exam_link(exam_type: str, language: str, group: str):
    """JSON fayldan kerakli imtihon havolasini o'qiydi."""

    try:
        with LINKS_FILE.open("r", encoding="utf-8") as file:
            links = json.load(file)

        link = (
            links
            .get(exam_type, {})
            .get(language, {})
            .get(group, "")
        )

        if not isinstance(link, str):
            logger.error(
                "Noto'g'ri link formati: %s / %s / %s",
                exam_type,
                language,
                group,
            )
            return None

        link = link.strip()

        if not link:
            return None

        if not link.startswith(("https://", "http://")):
            logger.warning("Google Forms link noto'g'ri formatda: %s", link)
            return None

        return link

    except FileNotFoundError:
        logger.error("exam_links.json topilmadi!")
        return None

    except json.JSONDecodeError:
        logger.exception("exam_links.json ichidagi JSON formati noto'g'ri!")
        return None

    except OSError:
        logger.exception("exam_links.json faylini o'qishda xatolik!")
        return None


# DATABASE
def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    with closing(get_connection()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                class_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS exam_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                exam_type TEXT NOT NULL,
                language TEXT NOT NULL,
                class_group TEXT NOT NULL,
                created_at TEXT NOT NULL,
                token TEXT,
                status TEXT DEFAULT 'pending',
                opened_at TEXT,
                device TEXT,
                target_url TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_tg ON exam_entries(telegram_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_class ON exam_entries(class_group)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_created ON exam_entries(created_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_entries_token ON exam_entries(token)")

        conn.commit()


def get_student(telegram_id: int):
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()

        return dict(row) if row else None


def save_student(telegram_id: int, full_name: str, phone: str):
    now = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as conn:
        conn.execute("""
            INSERT INTO students (
                telegram_id,
                full_name,
                phone,
                class_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, NULL, ?, ?)

            ON CONFLICT(telegram_id) DO UPDATE SET
                full_name = excluded.full_name,
                phone = excluded.phone,
                updated_at = excluded.updated_at
        """, (telegram_id, full_name, phone, now, now))

        conn.commit()


def update_student_class(telegram_id: int, class_name: str):
    now = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as conn:
        conn.execute("""
            UPDATE students
            SET class_name = ?, updated_at = ?
            WHERE telegram_id = ?
        """, (class_name, now, telegram_id))

        conn.commit()


def log_exam_entry(telegram_id: int, exam_type: str, language: str, class_group: str, token: str, target_url: str):
    now = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as conn:
        conn.execute("""
            INSERT INTO exam_entries (
                telegram_id,
                exam_type,
                language,
                class_group,
                created_at,
                token,
                status,
                target_url
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (telegram_id, exam_type, language, class_group, now, token, target_url))

        conn.commit()


# STATES
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()


class ExamSelection(StatesGroup):
    waiting_for_language = State()
    waiting_for_grade = State()
    waiting_for_group = State()


# KEYBOARDS
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Exam"),
                KeyboardButton(text="Mini Exam"),
            ]
        ],
        resize_keyboard=True,
    )


def language_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Rus"),
                KeyboardButton(text="Uzb"),
            ]
        ],
        resize_keyboard=True,
    )


def grades_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="2"),
                KeyboardButton(text="3"),
                KeyboardButton(text="4"),
                KeyboardButton(text="5"),
            ],
            [
                KeyboardButton(text="6"),
                KeyboardButton(text="7"),
                KeyboardButton(text="8"),
                KeyboardButton(text="9"),
            ],
        ],
        resize_keyboard=True,
    )


def groups_keyboard(grade: str):
    groups = [
        f"{grade}.{number}"
        for number in range(1, GROUPS_PER_GRADE + 1)
    ]

    keyboard = []

    for i in range(0, len(groups), 2):
        keyboard.append([
            KeyboardButton(text=groups[i]),
            KeyboardButton(text=groups[i + 1]),
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Telefon raqamni yuborish",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# PHONE HELPERS
def normalize_phone(phone: str):
    digits = re.sub(r"\D", "", phone)

    if len(digits) == 9:
        digits = "998" + digits

    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits

    return None


# REGISTRATION FINISH
async def finish_registration(
    message: Message,
    state: FSMContext,
    phone: str,
):
    data = await state.get_data()
    full_name = data["full_name"]

    try:
        await asyncio.to_thread(
            save_student,
            message.from_user.id,
            full_name,
            phone,
        )

    except sqlite3.Error:
        logger.exception("Student database save error")

        await message.answer(
            "❌ Ma'lumotlarni saqlashda xatolik yuz berdi. "
            "Iltimos, qaytadan urinib ko'ring."
        )
        return

    await state.clear()

    await message.answer(
        "✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!\n\n"
        "Kerakli imtihon turini tanlang:",
        reply_markup=main_menu_keyboard(),
    )


# START
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    try:
        student = await asyncio.to_thread(
            get_student,
            message.from_user.id,
        )

    except sqlite3.Error:
        logger.exception("Student database read error")

        await message.answer(
            "❌ Hozircha ma'lumotlaringizni tekshira olmadim. "
            "Birozdan keyin qayta urinib ko'ring."
        )
        return

    if student:
        await message.answer(
            f"Assalomu alaykum, {student['full_name']}!\n\n"
            "Kerakli imtihon turini tanlang:",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "Assalomu alaykum!\n"
        "Math Temur imtihon botiga xush kelibsiz.\n\n"
        "Ism va familiyangizni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.set_state(Registration.waiting_for_name)


# NAME
@dp.message(Registration.waiting_for_name)
async def get_name(message: Message, state: FSMContext):
    full_name = (message.text or "").strip()

    if len(full_name.split()) < 2:
        await message.answer(
            "Iltimos, ism va familiyangizni to‘liq kiriting."
        )
        return

    await state.update_data(full_name=full_name)

    await message.answer(
        "Endi telefon raqamingizni yuboring.\n\n"
        "📱 Tugmani bosishingiz yoki raqamni qo‘lda yozishingiz mumkin:",
        reply_markup=phone_keyboard(),
    )

    await state.set_state(Registration.waiting_for_phone)


# PHONE - CONTACT
@dp.message(Registration.waiting_for_phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    contact = message.contact

    if contact.user_id != message.from_user.id:
        await message.answer(
            "Iltimos, o‘zingizning telefon raqamingizni yuboring.",
            reply_markup=phone_keyboard(),
        )
        return

    phone = normalize_phone(contact.phone_number)

    if not phone:
        await message.answer(
            "Telefon raqami noto‘g‘ri formatda. Qaytadan yuboring.",
            reply_markup=phone_keyboard(),
        )
        return

    await finish_registration(message, state, phone)


# PHONE - MANUAL TEXT
@dp.message(Registration.waiting_for_phone, F.text)
async def get_phone_text(message: Message, state: FSMContext):
    phone = normalize_phone(message.text or "")

    if not phone:
        await message.answer(
            "❌ Telefon raqami noto‘g‘ri formatda.\n\n"
            "Masalan:\n"
            "+998901234567\n"
            "998901234567\n"
            "90 123 45 67\n\n"
            "Yoki pastdagi tugma orqali raqamingizni yuboring.",
            reply_markup=phone_keyboard(),
        )
        return

    await finish_registration(message, state, phone)


# PHONE - OTHER MESSAGE
@dp.message(Registration.waiting_for_phone)
async def phone_required(message: Message):
    await message.answer(
        "Telefon raqamingizni yozing yoki tugma orqali yuboring.",
        reply_markup=phone_keyboard(),
    )


# EXAM TYPE
@dp.message(F.text.in_({"Exam", "Mini Exam"}))
async def select_exam_type(message: Message, state: FSMContext):
    try:
        student = await asyncio.to_thread(
            get_student,
            message.from_user.id,
        )

    except sqlite3.Error:
        logger.exception("Student database read error")
        await message.answer(
            "❌ Xatolik yuz berdi. Qayta urinib ko‘ring."
        )
        return

    if not student:
        await message.answer(
            "Avval /start orqali ro‘yxatdan o‘ting.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    await state.update_data(exam_type=message.text)

    await message.answer(
        f"📚 Imtihon turi: {message.text}\n\n"
        "Tilni tanlang:",
        reply_markup=language_keyboard(),
    )

    await state.set_state(
        ExamSelection.waiting_for_language
    )


# LANGUAGE SELECTION
@dp.message(
    ExamSelection.waiting_for_language,
    F.text.in_({"Rus", "Uzb"}),
)
async def select_language(message: Message, state: FSMContext):
    await state.update_data(language=message.text)

    data = await state.get_data()

    await message.answer(
        f"📚 Imtihon: {data['exam_type']}\n"
        f"🌐 Til: {data['language']}\n\n"
        "Sinfingizni tanlang:",
        reply_markup=grades_keyboard(),
    )

    await state.set_state(
        ExamSelection.waiting_for_grade
    )


# INVALID LANGUAGE
@dp.message(ExamSelection.waiting_for_language)
async def invalid_language(message: Message):
    await message.answer(
        "Iltimos, Rus yoki Uzb tilidan birini tanlang:",
        reply_markup=language_keyboard(),
    )


# GRADE SELECTION
@dp.message(
    ExamSelection.waiting_for_grade,
    F.text.in_(GRADES),
)
async def select_grade(message: Message, state: FSMContext):
    grade = message.text

    await state.update_data(grade=grade)

    await message.answer(
        f"📚 Tanlangan sinf: {grade}\n\n"
        "Guruhingizni tanlang:",
        reply_markup=groups_keyboard(grade),
    )

    await state.set_state(
        ExamSelection.waiting_for_group
    )


# INVALID GRADE
@dp.message(ExamSelection.waiting_for_grade)
async def invalid_grade(message: Message):
    await message.answer(
        "Iltimos, 2 dan 9 gacha bo‘lgan sinflardan birini tanlang:",
        reply_markup=grades_keyboard(),
    )


# GROUP SELECTION
@dp.message(ExamSelection.waiting_for_group)
async def select_group(message: Message, state: FSMContext):
    data = await state.get_data()

    grade = data.get("grade")
    group = (message.text or "").strip()

    valid_groups = {
        f"{grade}.{number}"
        for number in range(1, GROUPS_PER_GRADE + 1)
    }

    if group not in valid_groups:
        await message.answer(
            "Iltimos, o‘zingizning guruhingizni tanlang:",
            reply_markup=groups_keyboard(grade),
        )
        return

    exam_type = data.get("exam_type") or "Exam"
    language = data.get("language") or "Uzb"

    # JSON fayldan havolani olish
    link = await asyncio.to_thread(
        get_exam_link,
        exam_type,
        language,
        group,
    )

    token = secrets.token_urlsafe(8)

    try:
        await asyncio.to_thread(
            update_student_class,
            message.from_user.id,
            group,
        )
        await asyncio.to_thread(
            log_exam_entry,
            message.from_user.id,
            exam_type,
            language,
            group,
            token,
            link or "",
        )

    except sqlite3.Error:
        logger.exception("Student class update error")

        await message.answer(
            "❌ Guruh ma'lumotini saqlashda xatolik yuz berdi. "
            "Qayta urinib ko'ring."
        )
        return

    if link:
        tracking_link = f"{WEB_BASE_URL}/exam/go/{token}"
        await message.answer(
            "✅ Ma'lumotlaringiz qabul qilindi!\n\n"
            f"📚 Imtihon: {exam_type}\n"
            f"🌐 Til: {language}\n"
            f"🎓 Guruh: {group}\n\n"
            "⚠️ <b>Diqqat:</b> Imtihonni boshlash uchun quyidagi shaxsiy havolangiz ustiga bosing:\n"
            f"👉 {tracking_link}\n\n"
            "🎉 Imtihonga omad!",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    else:
        await message.answer(
            "📚 Ma'lumotlaringiz qabul qilindi!\n\n"
            f"Imtihon: {exam_type}\n"
            f"Til: {language}\n"
            f"Guruh: {group}\n\n"
            "⏳ Ushbu guruh uchun imtihon havolasi "
            "hali tayyor emas.\n\n"
            "Iltimos, o‘qituvchingizga murojaat qiling.",
            reply_markup=main_menu_keyboard(),
        )

    await state.clear()


# UNKNOWN MESSAGE
@dp.message()
async def unknown_message(message: Message):
    try:
        student = await asyncio.to_thread(
            get_student,
            message.from_user.id,
        )

    except sqlite3.Error:
        logger.exception("Student database read error")
        await message.answer(
            "❌ Xatolik yuz berdi. Qayta urinib ko'ring."
        )
        return

    if student:
        await message.answer(
            "Iltimos, kerakli imtihon turini tanlang:",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "Botdan foydalanish uchun /start buyrug‘ini yuboring."
        )


# MAIN
async def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi. .env faylini tekshiring."
        )

    await asyncio.to_thread(init_db)
    await asyncio.to_thread(init_links_file)

    bot = Bot(token=TOKEN)

    try:
        logger.info("Math Temur bot ishga tushdi!")
        await dp.start_polling(bot)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())


import asyncio
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "database.db"

dp = Dispatcher()

EXAMS = {
    "5.1": "https://docs.google.com/forms/d/e/1FAIpQLSdeP2-2vQL_DMrlu3R22xHeND0zS8nYZ2xKPnc6xE_3UmVqmw/viewform?usp=dialog",
    "6.4": "https://docs.google.com/forms/",
}


# =========================
# DATABASE
# =========================

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
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
        conn.commit()


def get_student(telegram_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM students WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None


def save_student(telegram_id: int, full_name: str, phone: str):
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            INSERT INTO students (
                telegram_id, full_name, phone,
                class_name, created_at, updated_at
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

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            UPDATE students
            SET class_name = ?, updated_at = ?
            WHERE telegram_id = ?
        """, (class_name, now, telegram_id))
        conn.commit()


# =========================
# REGISTRATION STATES
# =========================

class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()


# =========================
# KEYBOARDS
# =========================

def classes_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5.1"), KeyboardButton(text="6.4")]
        ],
        resize_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📱 Telefon raqamni yuborish",
                request_contact=True,
            )]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    student = get_student(message.from_user.id)

    if student:
        await message.answer(
            f"Assalomu alaykum, {student['full_name']}!\n"
            "Kerakli sinfni tanlang:",
            reply_markup=classes_keyboard(),
        )
        return

    await message.answer(
        "Assalomu alaykum!\n"
        "Fast Education imtihon botiga xush kelibsiz.\n\n"
        "Ism va familiyangizni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_for_name)


# =========================
# NAME
# =========================

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
        "Endi telefon raqamingizni tugma orqali yuboring:",
        reply_markup=phone_keyboard(),
    )
    await state.set_state(Registration.waiting_for_phone)


# =========================
# PHONE
# =========================

@dp.message(Registration.waiting_for_phone, F.contact)
async def get_phone(message: Message, state: FSMContext):
    contact = message.contact

    if contact.user_id != message.from_user.id:
        await message.answer(
            "Iltimos, o‘zingizning telefon raqamingizni yuboring."
        )
        return

    data = await state.get_data()
    full_name = data["full_name"]
    phone = contact.phone_number

    save_student(
        telegram_id=message.from_user.id,
        full_name=full_name,
        phone=phone,
    )

    await state.clear()

    await message.answer(
        "✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!\n\n"
        "Endi sinfingizni tanlang:",
        reply_markup=classes_keyboard(),
    )


@dp.message(Registration.waiting_for_phone)
async def phone_required(message: Message):
    await message.answer(
        "Telefon raqamingizni pastdagi tugma orqali yuboring.",
        reply_markup=phone_keyboard(),
    )


# =========================
# EXAM CLASS
# =========================

@dp.message(F.text.in_(list(EXAMS.keys())))
async def select_exam(message: Message):
    student = get_student(message.from_user.id)

    if not student:
        await message.answer(
            "Avval /start orqali ro‘yxatdan o‘ting.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    class_name = message.text
    update_student_class(message.from_user.id, class_name)

    await message.answer(
        f"📚 Tanlangan sinf: {class_name}\n"
        "Testni quyidagi havola orqali topshiring:\n"
        f"{EXAMS[class_name]}"
    )


# =========================
# UNKNOWN MESSAGE
# =========================

@dp.message()
async def unknown_message(message: Message):
    student = get_student(message.from_user.id)

    if student:
        await message.answer(
            "Iltimos, mavjud sinflardan birini tanlang:",
            reply_markup=classes_keyboard(),
        )
    else:
        await message.answer(
            "Botdan foydalanish uchun /start buyrug‘ini yuboring."
        )


# =========================
# MAIN
# =========================

async def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi. .env faylini tekshiring."
        )

    init_db()

    bot = Bot(token=TOKEN)

    try:
        print("Fast Education bot ishga tushdi!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

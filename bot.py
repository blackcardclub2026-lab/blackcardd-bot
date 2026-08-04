import asyncio
import json
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    WebAppInfo,
)
import gspread
from google.oauth2.service_account import Credentials

# ==== НАСТРОЙКИ ====
BOT_TOKEN = os.getenv("BOT_TOKEN", "8917448855:AAHV-39g9yGxhBXtMScNXPTf6phYVp_nZMg")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://blackcardclub2026-lab.github.io/blackcard/")

# Google Sheets
CREDENTIALS_FILE = "credentials.json"
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # содержимое credentials.json, если задано через переменную окружения
SPREADSHEET_ID = "1j2kgbvDJ56QSTulWeOLt583hz-csYMuqQTTsw4e4Qfo"
SHEET_NAME = "Лист 1"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class Form(StatesGroup):
    waiting_for_phone = State()


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

if GOOGLE_CREDENTIALS_JSON:
    _creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)
    _creds = Credentials.from_service_account_info(_creds_info, scopes=SCOPES)
else:
    _creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
_gc = gspread.authorize(_creds)
_spreadsheet = _gc.open_by_key(SPREADSHEET_ID)


def get_worksheet():
    try:
        return _spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        return _spreadsheet.sheet1


def ensure_headers():
    ws = get_worksheet()
    first_row = ws.row_values(1)
    if not first_row:
        ws.append_row(["Дата", "Имя", "Телефон", "Username", "Telegram ID"])


def save_to_sheet(name: str, phone: str, username: str, user_id):
    ws = get_worksheet()
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        name,
        phone,
        f"@{username}" if username else "—",
        str(user_id),
    ])


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="🂡 Подать заявку в Black Card",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ]],
        resize_keyboard=True,
    )
    await message.answer(
        "Добро пожаловать в <b>Black Card</b> 🂡\n\n"
        "Нажмите кнопку ниже, чтобы оставить заявку на вступление.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@dp.message(F.web_app_data)
async def process_webapp_data(message: Message, state: FSMContext):
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        await message.answer("Не удалось обработать данные, попробуйте ещё раз.")
        return

    name = (data.get("name") or "").strip()
    username = data.get("username") or message.from_user.username or ""
    user_id = data.get("tg_id") or message.from_user.id

    if not name:
        await message.answer("Не удалось получить имя, попробуйте отправить форму ещё раз.")
        return

    await state.update_data(name=name, username=username, user_id=user_id)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        f"Спасибо, {name}! Осталось подтвердить номер телефона — нажмите кнопку ниже.",
        reply_markup=kb,
    )
    await state.set_state(Form.waiting_for_phone)


@dp.message(Form.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте свой собственный номер телефона через кнопку.")
        return

    data = await state.get_data()
    name = data.get("name")
    username = data.get("username") or message.from_user.username or ""
    user_id = data.get("user_id") or message.from_user.id
    phone = message.contact.phone_number

    try:
        save_to_sheet(name, phone, username, user_id)
    except Exception:
        logging.exception("Ошибка записи в Google Sheets")
        await message.answer(
            "Произошла ошибка при сохранении заявки. Попробуйте ещё раз чуть позже.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    await message.answer(
        "Спасибо! Ваша заявка в <b>Black Card</b> принята ✅\n"
        "Администратор клуба свяжется с вами лично.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
    await state.clear()


@dp.message(Form.waiting_for_phone)
async def process_phone_invalid(message: Message):
    await message.answer("Пожалуйста, воспользуйтесь кнопкой «Отправить номер телефона» ниже.")


async def main():
    ensure_headers()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
from datetime import datetime
from contextlib import asynccontextmanager

import gspread
import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from google.oauth2.service_account import Credentials
from fastapi import FastAPI

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("BOT_TOKEN", "8895793194:AAFzdanR2z2-18-FVjGtxbH_xCo3qWOr7QM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1447682472"))
CHANNEL_LINK = "https://t.me/atlantalogistics"

SHEET_NAME = os.getenv("SHEET_NAME", "Заявки Атланта")
WORKSHEET_NAME = "Заявки"
CREDENTIALS_FILE = "credentials.json"

# ==================== GOOGLE SHEETS ====================
def init_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Если есть переменная окружения — создаём файл из неё
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_env:
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            f.write(creds_env)
    
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
    
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="10")
        headers = ["ID", "Дата", "Имя", "Телефон", "Город", "Категория", "Детали", "Статус", "Username", "User ID"]
        worksheet.append_row(headers)
    
    return worksheet

sheet = init_sheet()

def save_to_sheet(order: dict):
    row = [
        order.get("id", ""),
        order.get("date", ""),
        order.get("name", ""),
        order.get("phone", ""),
        order.get("city", ""),
        order.get("category", ""),
        order.get("product", ""),
        order.get("status", "Новая"),
        order.get("username", ""),
        str(order.get("user_id", ""))
    ]
    sheet.append_row(row)

# ==================== БОТ ====================
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderState(StatesGroup):
    product = State()
    name = State()
    phone = State()
    city = State()
    confirm = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Отправить груз", callback_data="cat_cargo")],
        [InlineKeyboardButton(text="📋 Мои заявки", callback_data="my_orders")],
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"tg://user?id={ADMIN_ID}")]
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Всё верно, отправить", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Заполнить заново", callback_data="confirm_no")]
    ])

def back_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_menu")]
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        f"👋 <b>Добро пожаловать в Атланту!</b>\n\n"
        f"🚂 Грузоперевозки по России вагонами\n"
        f"🏍 Мопеды и запчасти из Владивостока\n\n"
        f"Выберите действие:"
    )
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"👋 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cat_cargo")
async def category_cargo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category="📦 Грузоперевозка")
    await state.set_state(OrderState.product)
    await callback.message.edit_text(
        "📦 <b>Грузоперевозка</b>\n\n"
        "Опишите ваш груз:\n"
        "• Что везём\n"
        "• Вес и габариты (примерно)\n"
        "• Откуда → Куда\n\n"
        "Пример: <i>Мопед Suzuki, 80 кг, Владивосток → Москва</i>",
        reply_markup=back_menu_kb(),
        parse_mode="HTML"
    )

@dp.message(OrderState.product)
async def get_product(message: Message, state: FSMContext):
    await state.update_data(product=message.text)
    await state.set_state(OrderState.name)
    await message.answer("✍️ <b>Ваше имя?</b>\n\nНапример: Иван", parse_mode="HTML")

@dp.message(OrderState.name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(OrderState.phone)
    await message.answer(
        "📞 <b>Ваш телефон или ник в Telegram?</b>\n\n"
        "Например: +7 999 123-45-67 или @ivan",
        parse_mode="HTML"
    )

@dp.message(OrderState.phone)
async def get_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderState.city)
    await message.answer(
        "🌍 <b>Ваш город или направление доставки?</b>\n\n"
        "Например: Москва, СПб, Новосибирск",
        parse_mode="HTML"
    )

@dp.message(OrderState.city)
async def get_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    data = await state.get_data()
    
    summary = (
        f"📋 <b>Проверьте вашу заявку:</b>\n\n"
        f"📌 <b>Категория:</b> {data['category']}\n"
        f"📦 <b>Детали:</b> {data['product']}\n"
        f"👤 <b>Имя:</b> {data['name']}\n"
        f"📞 <b>Телефон:</b> {data['phone']}\n"
        f"🌍 <b>Город:</b> {data['city']}\n\n"
        f"Если всё верно — жмите <b>«Отправить»</b>"
    )
    
    await state.set_state(OrderState.confirm)
    await message.answer(summary, reply_markup=confirm_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "confirm_yes", OrderState.confirm)
async def confirm_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user
    
    order_id = int(datetime.now().timestamp())
    
    order = {
        "id": order_id,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "user_id": user.id,
        "username": user.username or "нет ника",
        "category": data.get("category"),
        "product": data.get("product"),
        "name": data.get("name"),
        "phone": data.get("phone"),
        "city": data.get("city"),
        "status": "Новая"
    }
    
    try:
        save_to_sheet(order)
    except Exception as e:
        print(f"Ошибка записи в таблицу: {e}")
    
    admin_text = (
        f"🚨 <b>НОВАЯ ЗАЯВКА #{order_id}</b>\n\n"
        f"👤 <b>Клиент:</b> {data['name']}\n"
        f"📞 <b>Телефон:</b> {data['phone']}\n"
        f"🌍 <b>Город:</b> {data['city']}\n"
        f"📌 <b>Категория:</b> {data['category']}\n"
        f"📦 <b>Детали:</b> {data['product']}\n\n"
        f"🔗 <b>Профиль:</b> @{user.username or 'нет ника'}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>"
    )
    await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
    
    await callback.message.edit_text(
        f"✅ <b>Заявка #{order_id} принята!</b>\n\n"
        f"Менеджер свяжется с вами в ближайшее время.\n"
        f"Обычно отвечаем в течение 1–2 часов.\n\n"
        f"📢 <b>Наш канал:</b> {CHANNEL_LINK}\n\n"
        f"Что-то ещё нужно?",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data == "confirm_no")
async def confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🔄 <b>Хорошо, начнём заново!</b>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery):
    await callback.answer("История заявок в разработке 😉", show_alert=True)

# ==================== FASTAPI (для Render + UptimeRobot) ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot))
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "bot": "Atlanta Logistics"}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

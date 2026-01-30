import io
import re
import os
import easyocr
import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web

# 1. SOZLAMALAR
TOKEN = "8493482356:AAEM7VuQ30NhNTZBKE7HDt4SkyShv7rkwh0"
logging.basicConfig(level=logging.INFO)

# Ma'lumotlar bazasi
conn = sqlite3.connect('imei_base.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS imeis 
                  (imei TEXT PRIMARY KEY, user TEXT, branch TEXT)''')
conn.commit()

# 2. BOT OBYEKTLARI
session = AiohttpSession()
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()
reader = easyocr.Reader(['en'], gpu=False)

# 3. FSM (Holatlar)
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_branch = State()
    waiting_for_photo = State()

# 4. TUGMALAR
def get_branch_keyboard():
    branches = [
        [KeyboardButton(text="Texnomakon"), KeyboardButton(text="Salom nasiya")],
        [KeyboardButton(text="Sar tex"), KeyboardButton(text="Uzun")],
        [KeyboardButton(text="Crocus"), KeyboardButton(text="Mobile")],
        [KeyboardButton(text="Termiz"), KeyboardButton(text="Amir xolding")]
    ]
    return ReplyKeyboardMarkup(keyboard=branches, resize_keyboard=True, one_time_keyboard=True)

# 5. DUBKLIKATNI TEKSHIRISH
def check_and_save_imei(imei_list, user_name, branch_name):
    results = []
    for imei in imei_list:
        cursor.execute("SELECT user, branch FROM imeis WHERE imei=?", (imei,))
        row = cursor.fetchone()
        if row:
            results.append(f"⚠️ `{imei}` - **BAZADA BOR!**\n(Yuborgan: {row[0]}, Filial: {row[1]})")
        else:
            cursor.execute("INSERT INTO imeis (imei, user, branch) VALUES (?, ?, ?)", 
                           (imei, user_name, branch_name))
            conn.commit()
            results.append(f"✅ `{imei}` - **YANGI (Saqlandi)**")
    return results

# 6. HANDLERLAR
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await message.answer("Xush kelibsiz! Ism-familiyangizni kiriting:")
    await state.set_state(Registration.waiting_for_name)

@dp.message(Registration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(user_name=message.text)
    await message.answer(f"Rahmat, {message.text}! Filialni tanlang:", reply_markup=get_branch_keyboard())
    await state.set_state(Registration.waiting_for_branch)

@dp.message(Registration.waiting_for_branch)
async def process_branch(message: types.Message, state: FSMContext):
    await state.update_data(branch_name=message.text)
    await message.answer("Endi IMEI kodli rasmni yuboring:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Registration.waiting_for_photo)

@dp.message(Registration.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    msg = await message.answer("Skanerlanmoqda... 🔍")
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        
        ocr_results = reader.readtext(file_bytes.read())
        full_text = " ".join([res[1] for res in ocr_results])
        imei_list = re.findall(r'\d{15}', full_text)
        
        if imei_list:
            status_list = check_and_save_imei(imei_list, data['user_name'], data['branch_name'])
            response = f"👤 **Xodim:** {data['user_name']}\n📍 **Filial:** {data['branch_name']}\n\n" + "\n\n".join(status_list)
            await msg.edit_text(response, parse_mode="Markdown")
        else:
            await msg.edit_text("❌ Rasmda 15 xonali IMEI topilmadi.")
    except Exception as e:
        await msg.edit_text(f"⚠️ Xatolik: {str(e)}")

# 7. RENDER UCHUN PORT (WEB SERVER)
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    # Render uchun vaqtinchalik HTTP server (o'chib qolmaslik uchun)
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    
    # Botni ishga tushirish
    loop = asyncio.get_event_loop()
    loop.create_task(site.start())
    print("Bot va Port ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
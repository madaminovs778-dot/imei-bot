import os
import re
import io
import httpx
import asyncio
import socket
from datetime import datetime
import pytz
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# --- SOZLAMALAR (GitHub-da ochiq ko'rinmaydi) ---
API_TOKEN = os.getenv('8493482356:AAEM7VuQ3ONhNTZBKE7HDt4SkyShv7rkwh0')
STEIN_API_URL = os.getenv('https://api.steinhq.com/v1/storages/697d2b1caffba40a6243f4b9')
OCR_API_KEY = os.getenv('K86744407688957')

# DNS muammosini tekshirish
try:
    print(f"Internet tekshiruvi (DNS): {socket.gethostbyname('api.telegram.org')}")
except Exception as e:
    print(f"⚠️ Tarmoq xatoligi: {e}")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class BotStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_branch = State()

BRANCHES = ["Texnomakon", "Salom nasiy", "Sar tex", "Uzun", "Corocus", "Mobile", "Termiz", "Amir xolding"]

async def check_imei_exists(imei):
    """Stein orqali bazada IMEI borligini tekshirish"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            search_query = f'{{"IMEI1":"{imei}"}}'
            response = await client.get(f"{STEIN_API_URL}?search={search_query}")
            data = response.json()
            return len(data) > 0
        except Exception as e:
            print(f"Qidiruv xatosi: {e}")
            return False

def get_branch_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for branch in BRANCHES:
        keyboard.add(branch)
    return keyboard

@dp.message_handler(commands=['start'], state='*')
async def start_cmd(message: types.Message):
    await message.answer("Xush kelibsiz! Iltimos, smartfon qutisidagi IMEI rasmini yuboring.")
    await BotStates.waiting_for_photo.set()

@dp.message_handler(content_types=['photo'], state=BotStates.waiting_for_photo)
async def handle_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"

    await message.answer("⌛ Rasm skanerlanmoqda...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {'apikey': OCR_API_KEY, 'url': file_url, 'language': 'eng', 'OCREngine': 2}
        try:
            res = await client.post("https://api.ocr.space/parse/image", data=payload)
            result = res.json()
            
            if result.get("ParsedResults"):
                text = result["ParsedResults"][0]["ParsedText"]
                imeis = re.findall(r'\b\d{15}\b', text)
                
                if imeis:
                    imei1 = imeis[0]
                    if await check_imei_exists(imei1):
                        await message.answer(f"❌ Xatolik: {imei1} bazada allaqachon mavjud!")
                        return

                    await state.update_data(imei1=imei1, imei2=imeis[1] if len(imeis) > 1 else "Yo'q")
                    await message.answer(f"✅ Skanerlandi:\nIMEI 1: {imei1}\n\nFilialni tanlang:", reply_markup=get_branch_keyboard())
                    await BotStates.waiting_for_branch.set()
                else:
                    await message.answer("Rasmda IMEI topilmadi. Iltimos, aniqroq rasm yuboring.")
            else:
                await message.answer("Skanerlashda xatolik yuz berdi.")
        except Exception:
            await message.answer("OCR xizmati bilan bog'lanishda xatolik.")

@dp.message_handler(state=BotStates.waiting_for_branch)
async def handle_branch(message: types.Message, state: FSMContext):
    if message.text not in BRANCHES:
        await message.answer("Tugmalardan birini tanlang.")
        return

    user_data = await state.get_data()
    now = datetime.now(pytz.timezone('Asia/Tashkent'))
    full_datetime = now.strftime("%d.%m.%Y %H:%M:%S")

    row = [{
        "Sana_Vaqt": full_datetime,
        "IMEI1": user_data['imei1'],
        "IMEI2": user_data['imei2'],
        "Filial": message.text,
        "UserID": str(message.from_user.id),
        "Ism": message.from_user.full_name
    }]

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(STEIN_API_URL, json=row)
            if response.status_code == 200:
                await message.answer(f"✅ Saqlandi!\nSana: {full_datetime}\nFilial: {message.text}", reply_markup=types.ReplyKeyboardRemove())
                await BotStates.waiting_for_photo.set()
            else:
                await message.answer("Jadvalga saqlashda xatolik.")
        except:
            await message.answer("Stein API xatosi.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

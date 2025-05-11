import logging
import asyncio
import json
from collections import defaultdict
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.filters import Command
from config import *
from aiogram.client.session.aiohttp import AiohttpSession
session = AiohttpSession(proxy='http://proxy.server:3128')

# --- НАСТРОЙКИ ---
TASKS_FILE = Path("tasks.json")

# --- ЛОГГИРОВАНИЕ ---
logging.basicConfig(level=logging.INFO)

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

# --- ЗАГРУЗКА ЗАДАНИЙ ---
def load_tasks():
    if TASKS_FILE.exists():
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tasks():
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(TASKS, f, ensure_ascii=False, indent=2)

TASKS = load_tasks()

# --- СОСТОЯНИЯ ---
class Submission(StatesGroup):
    choosing_task = State()

class AdminStates(StatesGroup):
    waiting_for_task_text = State()

# --- ДОБАВЛЕНИЕ ЗАДАНИЯ (только для администратора) ---
@dp.message(Command("add_task"))
async def add_task_command(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    await message.answer("✏️ Введите текст нового задания:")
    await state.set_state(AdminStates.waiting_for_task_text)

@dp.message(AdminStates.waiting_for_task_text)
async def receive_task_text(message: Message, state: FSMContext):
    new_task_text = message.text.strip()
    new_id = str(int(max(TASKS.keys(), default="0")) + 1)
    TASKS[new_id] = new_task_text
    save_tasks()
    await bot.send_message(chat_id=CHANNEL_ID, text=f"Новое задание! 🧳\n День {new_id}\n\n{new_task_text}")
    await message.answer(f"✅ Задание добавлено!\nID: {new_id}\nТекст: {new_task_text}")
    await state.clear()

# --- ХРАНИЛИЩЕ для media_group ---
media_groups = defaultdict(list)
task_choices = {}

# --- ОБРАБОТЧИКИ ---
@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: Message, state: FSMContext):
    task_list = "\n".join([f"{k}: {v}" for k, v in TASKS.items()])
    await message.answer(f"Привет! Выбери задание, отправив его номер:\n\n{task_list}")
    await state.set_state(Submission.choosing_task)

@dp.message(Submission.choosing_task)
async def task_chosen(message: Message, state: FSMContext):
    task_id = message.text.strip()
    if task_id not in TASKS:
        await message.answer("Неверный номер задания. Попробуй снова.")
        return
    task_choices[message.from_user.id] = task_id
    await state.clear()
    await message.answer("Теперь отправь все фото одним сообщением (альбомом). Можно добавить какой-то комментарий к работе.")

@dp.message(F.media_group_id, F.photo)
async def handle_album(message: Message):
    key = (message.chat.id, message.media_group_id)
    media_groups[key].append(message)

    await asyncio.sleep(1)  # дать время на сбор группы

    if key in media_groups:
        group = sorted(media_groups.pop(key), key=lambda m: m.message_id)
        photos = [InputMediaPhoto(media=m.photo[-1].file_id) for m in group]

        caption = next((m.caption for m in group if m.caption), "(без комментариев)")
        task_id = task_choices.get(message.from_user.id, "?")

        full_caption = (
            f"📝 <b>Задание {task_id}:</b> {TASKS.get(task_id, 'Неизвестное задание')}\n"
            f"👤 <b>Отправил:</b> @{message.from_user.username or message.from_user.full_name}\n\n"
            f"📍 <b>Комментарий:</b> {caption}"
        )

        photos[0].caption = full_caption
        photos[0].parse_mode = ParseMode.HTML

        await bot.send_media_group(chat_id=CHANNEL_ID, media=photos)
        await message.answer("✅ Фото успешно отправлены в канал.")

# --- ЗАПУСК ---
if __name__ == "__main__":
    async def main():
        await dp.start_polling(bot)
    asyncio.run(main())

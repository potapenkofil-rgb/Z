import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

# ─────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────

os.makedirs('sessions', exist_ok=True)

BOT_TOKEN      = '8624033791:AAH00Vf6yNORQ56W-baJ52fw7d2IOmene2M'
PROXY          = ('socks5', '127.0.0.1', 10808)
SESSIONS_META  = 'sessions/meta.json'
ADMINS_FILE    = 'sessions/admins.json'
SUPER_ADMIN_ID = 7835543351
BOT_USER_ID    = int(BOT_TOKEN.split(':')[0])

aio_session = AiohttpSession(proxy='socks5://127.0.0.1:10808')
bot = Bot(BOT_TOKEN, session=aio_session)
dp  = Dispatcher(storage=MemoryStorage())

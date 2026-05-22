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
SUBS_DB        = 'sessions/subs.db'
SUPER_ADMIN_ID = 7835543351
BOT_USER_ID    = int(BOT_TOKEN.split(':')[0])
BOT_USERNAME: str = ''  # filled at startup in main.py

# CryptoBot API — перегенерируй в @CryptoBot → My Apps если токен утёк
CRYPTOBOT_TOKEN = os.environ.get('CRYPTOBOT_TOKEN', '585675:AArQXR1y4cgjjVuv5377jscqGAHWJT6bATJ')
SUB_PRICE_USDT  = 2.0
SUB_DURATION_S  = 30 * 24 * 3600     # 30 дней
WATERMARK_TEXT  = 'Лучший бот для рассыла: @rassyl_W_robot'

# Тарифы: ключ → (цена USDT, дней)
SUB_TIERS: dict[str, tuple[float, int]] = {
    '1m':  (2.0,  30),
    '3m':  (6.0,  90),
    '6m':  (12.0, 180),
    '12m': (24.0, 365),
}

aio_session = AiohttpSession(proxy='socks5://127.0.0.1:10808')
bot = Bot(BOT_TOKEN, session=aio_session)
dp  = Dispatcher(storage=MemoryStorage())

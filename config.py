import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

os.makedirs('sessions', exist_ok=True)

# ─── Secrets ──────────────────────────────────────────────────────

BOT_TOKEN       = os.environ['BOT_TOKEN']
CRYPTOBOT_TOKEN = os.environ['CRYPTOBOT_TOKEN']

# ─── Proxy ────────────────────────────────────────────────────────

_use_proxy = os.environ.get('USE_PROXY', 'false').strip().lower() == 'true'

if _use_proxy:
    PROXY_HOST = os.environ.get('PROXY_HOST', '127.0.0.1')
    PROXY_PORT = int(os.environ.get('PROXY_PORT', '10808'))
    PROXY      = ('socks5', PROXY_HOST, PROXY_PORT)
    _proxy_url = f'socks5://{PROXY_HOST}:{PROXY_PORT}'
else:
    PROXY      = None
    _proxy_url = None

# ─── Paths & IDs ──────────────────────────────────────────────────

SESSIONS_META  = 'sessions/meta.json'
ADMINS_FILE    = 'sessions/admins.json'
SUBS_DB        = 'sessions/subs.db'
SUPER_ADMIN_ID = 7835543351
BOT_USER_ID    = int(BOT_TOKEN.split(':')[0])
BOT_USERNAME: str = ''  # заполняется при старте в main.py

# ─── Subscription tiers ───────────────────────────────────────────

SUB_PRICE_USDT = 2.0
SUB_DURATION_S = 30 * 24 * 3600

SUB_TIERS: dict[str, tuple[float, int]] = {
    '1m':  (2.0,  30),
    '3m':  (6.0,  90),
    '6m':  (12.0, 180),
    '12m': (24.0, 365),
}

WATERMARK_TEXT = 'Лучший бот для рассыла: @rassyl_W_robot'

# ─── Bot & Dispatcher ─────────────────────────────────────────────

aio_session = AiohttpSession(proxy=_proxy_url) if _proxy_url else AiohttpSession()
bot = Bot(BOT_TOKEN, session=aio_session)
dp  = Dispatcher(storage=MemoryStorage())

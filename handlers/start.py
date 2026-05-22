import asyncio

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from sessions import is_admin, load_meta, save_meta
from state import userbot_refs
from userbot import connect_and_run

router = Router()

# ─────────────────────────────────────────────────────────────────
# UI text / keyboard helpers (импортируются и из auth.py)
# ─────────────────────────────────────────────────────────────────

def _welcome_text() -> str:
    return (
        '👋 <b>Привет!</b>\n\n'
        'Это инструмент для массовой рассылки сообщений в Telegram.\n\n'
        '📨 <b>Что умеет:</b>\n'
        '• <code>/flood</code> — рассылка в одном чате N раз с задержкой\n'
        '• <code>/gflood</code> — рассылка сразу по всем чатам в папке\n'
        '• Управление задачами: пауза, остановка, прогресс\n\n'
        '━━━━━━━━━━━━━━━━━━━\n'
        '🔑 <b>Для работы нужно подключить аккаунт Telegram.</b>\n\n'
        'Понадобятся два ключа — получить на '
        '<code>my.telegram.org</code> → API development:\n\n'
        'API ID    →  <code>12345678</code>\n'
        'API HASH  →  <code>a1b2c3d4e5f6789012345678abcdef01</code>'
    )


def _welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔑 Подключить аккаунт', callback_data='auth')],
    ])


def _main_menu_text() -> str:
    return '🏠 <b>Главное меню</b>'


def _main_menu_kb(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text='📊 Мои задачи',  callback_data='tl_0'),
            InlineKeyboardButton(text='📱 Мой аккаунт', callback_data='menu_account'),
        ],
        [
            InlineKeyboardButton(text='📖 Команды', callback_data='guide_main'),
        ],
    ]
    if is_admin(uid):
        rows[-1].append(
            InlineKeyboardButton(text='🔐 Админ', callback_data='adm_panel')
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == '/start')
async def cmd_start(message: Message):
    meta = load_meta()
    uid  = message.from_user.id

    if str(uid) in meta:
        # Если тред ещё не запущен — запускаем в фоне
        if uid not in userbot_refs:
            asyncio.create_task(connect_and_run(
                uid,
                meta[str(uid)]['api_id'],
                meta[str(uid)]['api_hash'],
                message.chat.id,
            ))
        await message.answer(
            _main_menu_text(), parse_mode='HTML',
            reply_markup=_main_menu_kb(uid),
        )
    else:
        await message.answer(_welcome_text(), parse_mode='HTML', reply_markup=_welcome_kb())


# ─────────────────────────────────────────────────────────────────
# Главное меню (callback — редактирует текущее сообщение)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_main')
async def cb_menu_main(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(
        _main_menu_text(), parse_mode='HTML',
        reply_markup=_main_menu_kb(uid),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Карточка аккаунта
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_account')
async def cb_menu_account(callback: CallbackQuery):
    uid  = callback.from_user.id
    meta = load_meta()
    info = meta.get(str(uid))

    if not info:
        # Сессии нет — показываем экран приветствия
        await callback.message.edit_text(_welcome_text(), parse_mode='HTML',
                                         reply_markup=_welcome_kb())
        await callback.answer()
        return

    phone  = info.get('phone', 'неизвестен')
    online = uid in userbot_refs
    status = '🟢 Онлайн' if online else '🔴 Оффлайн'

    text = (
        f'📱 <b>Мой аккаунт</b>\n\n'
        f'📞 Номер: <code>{phone}</code>\n'
        f'🔌 Статус: {status}'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отключить аккаунт', callback_data='menu_disconnect')],
        [InlineKeyboardButton(text='◀️ Меню',              callback_data='menu_main')],
    ])
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=kb)
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Отключение аккаунта
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_disconnect')
async def cb_menu_disconnect(callback: CallbackQuery):
    uid  = callback.from_user.id
    meta = load_meta()
    meta.pop(str(uid), None)
    save_meta(meta)

    ref = userbot_refs.pop(uid, None)
    if ref:
        try:
            asyncio.run_coroutine_threadsafe(ref['client'].disconnect(), ref['loop'])
        except Exception:
            pass

    await callback.message.edit_text(_welcome_text(), parse_mode='HTML',
                                     reply_markup=_welcome_kb())
    await callback.answer('✅ Аккаунт отключён')

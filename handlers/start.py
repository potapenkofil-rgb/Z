import asyncio
import time

from aiogram import F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from sessions import is_admin, load_meta, save_meta
from state import userbot_refs
from subscriptions import add_referral, get_expiry, has_active_sub
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
        '<a href="https://my.telegram.org">my.telegram.org</a> → API development:\n\n'
        'API ID    →  <code>12345678</code>\n'
        'API HASH  →  <code>a1b2c3d4e5f6789012345678abcdef01</code>'
    )


def _welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔑 Подключить аккаунт', callback_data='auth')],
    ])


def _main_menu_text(uid: int = 0) -> str:
    lines = ['🏠 <b>Главное меню</b>\n']
    if uid:
        # Статус аккаунта
        if uid in userbot_refs:
            lines.append('🔌 Аккаунт: 🟢 подключён')
        else:
            lines.append('🔌 Аккаунт: 🔴 не подключён')
        # Статус подписки
        if has_active_sub(uid):
            days = max(0, (get_expiry(uid) - int(time.time())) // 86400)
            lines.append(f'💎 Подписка: активна · {days} дн.')
        else:
            lines.append('💎 Подписка: не активна')
    return '\n'.join(lines)


def _main_menu_kb(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text='📊 Мои задачи',  callback_data='tl_0'),
            InlineKeyboardButton(text='📱 Мой аккаунт', callback_data='menu_account'),
        ],
        [
            InlineKeyboardButton(text='📋 Шаблоны',      callback_data='tmpl_list'),
            InlineKeyboardButton(text='🚫 Черный список', callback_data='bl_list'),
        ],
        [
            InlineKeyboardButton(text='💎 Подписка',  callback_data='sub_menu'),
            InlineKeyboardButton(text='📖 Команды',   callback_data='guide_main'),
        ],
    ]
    if is_admin(uid):
        rows.append([
            InlineKeyboardButton(text='🔐 Админ', callback_data='adm_panel'),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    meta = load_meta()
    uid  = message.from_user.id

    ref_param = command.args
    if ref_param and ref_param.startswith('ref_'):
        try:
            inviter_id = int(ref_param[4:])
            if inviter_id != uid:
                add_referral(inviter_id, uid)
        except (ValueError, Exception):
            pass

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
            _main_menu_text(uid), parse_mode='HTML',
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
        _main_menu_text(uid), parse_mode='HTML',
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
        await callback.message.edit_text(_welcome_text(), parse_mode='HTML',
                                         reply_markup=_welcome_kb())
        await callback.answer()
        return

    phone  = info.get('phone', 'неизвестен')
    online = uid in userbot_refs
    status = '🟢 Онлайн' if online else '🔴 Оффлайн'

    # Пытаемся достать живые данные из Telethon
    name    = '—'
    user_id_str = '—'
    premium = '—'
    username_str = '—'

    ref = userbot_refs.get(uid)
    if ref:
        try:
            me = await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(ref['client'].get_me(), ref['loop'])
            )
            first = getattr(me, 'first_name', '') or ''
            last  = getattr(me, 'last_name',  '') or ''
            name  = (first + ' ' + last).strip() or '—'
            user_id_str  = str(me.id)
            premium = '✅ Есть' if getattr(me, 'premium', False) else '❌ Нет'
            uname = getattr(me, 'username', None)
            username_str = f'@{uname}' if uname else '—'
        except Exception:
            pass

    # Статус подписки
    if has_active_sub(uid):
        days = max(0, (get_expiry(uid) - int(time.time())) // 86400)
        sub_line = f'💎 <b>Подписка:</b> активна, {days} дн.'
    else:
        sub_line = '💎 <b>Подписка:</b> не активна (с водяным знаком)'

    text = (
        f'📱 <b>Мой аккаунт</b>\n\n'
        f'👤 <b>Имя:</b> {name}\n'
        f'🔗 <b>Username:</b> {username_str}\n'
        f'🆔 <b>ID:</b> <code>{user_id_str}</code>\n'
        f'📞 <b>Номер:</b> <code>{phone}</code>\n'
        f'⭐ <b>Premium:</b> {premium}\n'
        f'🔌 <b>Статус:</b> {status}\n'
        f'{sub_line}'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💎 Подписка',          callback_data='sub_menu')],
        [InlineKeyboardButton(text='🔌 Прокси',            callback_data='proxy_menu')],
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

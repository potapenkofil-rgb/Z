import asyncio
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

from config import PROXY, SUPER_ADMIN_ID
from sessions import (
    add_admin,
    is_admin,
    load_admins,
    load_meta,
    remove_admin,
    save_meta,
)
from state import active, userbot_refs
from subscriptions import (
    ban_user, count_active_subs, count_banned,
    extend_sub, get_expiry, has_active_sub,
    is_banned, revoke_sub, unban_user,
)
from userbot import launch_checker

router = Router()

# ─────────────────────────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────────────────────────

class AdminAuth(StatesGroup):
    api_id   = State()
    api_hash = State()
    phone    = State()
    code     = State()
    password = State()


class AddAdmin(StatesGroup):
    uid = State()


class ManageSub(StatesGroup):
    username = State()


class Broadcast(StatesGroup):
    audience = State()
    text     = State()


# ─────────────────────────────────────────────────────────────────
# Admin panel UI helpers
# ─────────────────────────────────────────────────────────────────

def _admin_panel_text() -> str:
    admins  = load_admins()
    meta    = load_meta()
    checker = meta.get('admin_checker')
    cs      = f"✅ {checker.get('phone', '?')}" if checker else '❌ не подключён'
    return (
        f'🔐 <b>Панель администратора</b>\n\n'
        f'📱 Ловец чеков: {cs}\n'
        f'👥 Обычных админов: {len(admins)}'
    )


def _admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📱 Аккаунт ловца чеков', callback_data='adm_account')],
        [InlineKeyboardButton(text='👥 Управление админами', callback_data='adm_admins')],
        [InlineKeyboardButton(text='💎 Подписки',            callback_data='adm_subs')],
        [InlineKeyboardButton(text='📊 Статистика',          callback_data='adm_stats')],
        [InlineKeyboardButton(text='📣 Рассылка',            callback_data='adm_broadcast')],
        [InlineKeyboardButton(text='◀️ Меню',                callback_data='menu_main')],
    ])


def _admins_text() -> str:
    admins = load_admins()
    lines  = '\n'.join(f'  • <code>{a}</code>' for a in admins) or '  (нет)'
    return (
        f'👥 <b>Администраторы</b>\n\n'
        f'🌟 Супер-админ: <code>{SUPER_ADMIN_ID}</code>\n\n'
        f'Обычные:\n{lines}'
    )


def _admins_kb(is_super: bool) -> InlineKeyboardMarkup:
    admins = load_admins()
    rows   = []
    if is_super:
        for a in admins:
            rows.append([InlineKeyboardButton(text=f'❌ Удалить {a}', callback_data=f'adm_rm_{a}')])
        rows.append([InlineKeyboardButton(text='➕ Добавить', callback_data='adm_add')])
    rows.append([InlineKeyboardButton(text='◀️ Назад', callback_data='adm_back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────────────────────────
# /admin command
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'adm_panel')
async def cb_adm_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    await callback.message.edit_text(
        _admin_panel_text(), parse_mode='HTML', reply_markup=_admin_panel_kb())
    await callback.answer()


@router.message(F.text == '/admin')
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(_admin_panel_text(), parse_mode='HTML', reply_markup=_admin_panel_kb())


# ─────────────────────────────────────────────────────────────────
# Admin panel callbacks
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'adm_back')
async def cb_adm_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        _admin_panel_text(), parse_mode='HTML', reply_markup=_admin_panel_kb())
    await callback.answer()


@router.callback_query(F.data == 'adm_account')
async def cb_adm_account(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    checker = load_meta().get('admin_checker')
    if checker:
        text = f"📱 <b>Аккаунт ловца подключён</b>\nТел: <code>{checker.get('phone', '?')}</code>"
        kb   = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔄 Переподключить', callback_data='adm_auth'),
             InlineKeyboardButton(text='❌ Отключить',      callback_data='adm_disc')],
            [InlineKeyboardButton(text='◀️ Назад',          callback_data='adm_back')],
        ])
    else:
        text = '📱 <b>Аккаунт ловца не подключён</b>'
        kb   = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='➕ Подключить', callback_data='adm_auth')],
            [InlineKeyboardButton(text='◀️ Назад',     callback_data='adm_back')],
        ])
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == 'adm_disc')
async def cb_adm_disc(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    meta = load_meta()
    meta.pop('admin_checker', None)
    save_meta(meta)
    userbot_refs.pop(-1, None)
    await callback.message.edit_text('✅ Аккаунт ловца отключён')
    await callback.answer()


@router.callback_query(F.data == 'adm_admins')
async def cb_adm_admins(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        _admins_text(), parse_mode='HTML',
        reply_markup=_admins_kb(callback.from_user.id == SUPER_ADMIN_ID),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('adm_rm_'))
async def cb_adm_rm(callback: CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer('Только супер-админ')
        return
    target = int(callback.data[7:])
    remove_admin(target)
    await callback.message.edit_text(
        _admins_text(), parse_mode='HTML',
        reply_markup=_admins_kb(True),
    )
    await callback.answer(f'✅ {target} удалён')


@router.callback_query(F.data == 'adm_add')
async def cb_adm_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer('Только супер-админ')
        return
    await state.set_state(AddAdmin.uid)
    await callback.message.answer('Введите Telegram ID нового администратора:')
    await callback.answer()


@router.message(AddAdmin.uid)
async def step_add_admin(message: Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    try:
        new_id = int(message.text.strip())
    except ValueError:
        await message.answer('Неверный ID, введите число:')
        return
    add_admin(new_id)
    await state.clear()
    await message.answer(f'✅ Администратор <code>{new_id}</code> добавлен', parse_mode='HTML')


# ─────────────────────────────────────────────────────────────────
# Admin checker auth FSM
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'adm_auth')
async def cb_adm_auth(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    await state.set_state(AdminAuth.api_id)
    await callback.message.answer('Введите API ID аккаунта-ловца (с my.telegram.org):')
    await callback.answer()


@router.message(AdminAuth.api_id)
async def adm_step_api_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.strip().isdigit():
        await message.answer('API ID — число:')
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(AdminAuth.api_hash)
    await message.answer('Введите API HASH:')


@router.message(AdminAuth.api_hash)
async def adm_step_api_hash(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(AdminAuth.phone)
    await message.answer('Введите номер телефона:')


@router.message(AdminAuth.phone)
async def adm_step_phone(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    phone = message.text.strip()
    data  = await state.get_data()
    cl    = TelegramClient('sessions/admin_checker', data['api_id'], data['api_hash'], proxy=PROXY)
    try:
        await cl.connect()
        sent = await cl.send_code_request(phone)
    except Exception as e:
        await cl.disconnect()
        await state.clear()
        await message.answer(f'❌ {e}')
        return
    await state.update_data(phone=phone, phone_code_hash=sent.phone_code_hash)
    active[f'adm_{message.from_user.id}'] = {'client': cl}
    await state.set_state(AdminAuth.code)
    await message.answer(
        '📲 Код отправлен.\n\n'
        'Введите код + 1 (если код <b>12345</b> → введите <b>12346</b>).',
        parse_mode='HTML',
    )


@router.message(AdminAuth.code)
async def adm_step_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        code = str(int(message.text.strip()) - 1)
    except ValueError:
        await message.answer('Введите числовой код:')
        return
    data  = await state.get_data()
    key   = f'adm_{message.from_user.id}'
    entry = active.get(key)
    if not entry:
        await state.clear()
        await message.answer('❌ Сессия истекла. Начните заново.')
        return
    cl: TelegramClient = entry['client']
    try:
        await cl.sign_in(data['phone'], code, phone_code_hash=data['phone_code_hash'])
    except PhoneCodeInvalidError:
        await message.answer('❌ Неверный код:')
        return
    except SessionPasswordNeededError:
        await state.set_state(AdminAuth.password)
        await message.answer('🔐 Введите облачный пароль:')
        return
    except Exception as e:
        await message.answer(f'❌ {e}')
        return
    await _finish_adm_auth(message, state, cl, data)


@router.message(AdminAuth.password)
async def adm_step_password(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    entry = active.get(f'adm_{message.from_user.id}')
    if not entry:
        await state.clear()
        await message.answer('❌ Сессия истекла. Начните заново.')
        return
    cl: TelegramClient = entry['client']
    data = await state.get_data()
    try:
        await cl.sign_in(password=message.text)
    except Exception:
        await message.answer('❌ Неверный пароль:')
        return
    await _finish_adm_auth(message, state, cl, data)


async def _finish_adm_auth(message: Message, state: FSMContext,
                            cl: TelegramClient, data: dict):
    active.pop(f'adm_{message.from_user.id}', None)
    await cl.disconnect()
    await state.clear()

    meta = load_meta()
    meta['admin_checker'] = {
        'api_id':   data['api_id'],
        'api_hash': data['api_hash'],
        'phone':    data['phone'],
        'chat_id':  message.chat.id,
    }
    save_meta(meta)

    # Останавливаем старый ловец-аккаунт если был
    old = userbot_refs.pop(-1, None)
    if old:
        try:
            asyncio.run_coroutine_threadsafe(old['client'].disconnect(), old['loop'])
        except Exception:
            pass

    launch_checker(-1, data['api_id'], data['api_hash'],
                   message.chat.id, session_file='sessions/admin_checker')
    await message.answer('✅ Аккаунт ловца чеков подключён!')


# ─────────────────────────────────────────────────────────────────
# Управление подписками
# ─────────────────────────────────────────────────────────────────

def _sub_card_text(target_id: int, name: str) -> str:
    if has_active_sub(target_id):
        expiry = get_expiry(target_id)
        days   = max(0, (expiry - int(time.time())) // 86400)
        status = f'✅ Активна, {days} дн.'
    else:
        status = '❌ Не активна'
    return (
        f'💎 <b>Подписка пользователя</b>\n\n'
        f'👤 {name}\n'
        f'🆔 <code>{target_id}</code>\n'
        f'📌 Статус: {status}'
    )


def _sub_card_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='➕ Выдать 30д',   callback_data=f'adm_sg_{target_id}'),
            InlineKeyboardButton(text='🔄 +30 дней',     callback_data=f'adm_se_{target_id}'),
        ],
        [InlineKeyboardButton(text='❌ Забрать',          callback_data=f'adm_sr_{target_id}')],
        [InlineKeyboardButton(text='◀️ Назад',            callback_data='adm_subs')],
    ])


@router.callback_query(F.data == 'adm_subs')
async def cb_adm_subs(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    await state.set_state(ManageSub.username)
    await callback.message.edit_text(
        '💎 <b>Управление подписками</b>\n\n'
        'Введите @username или числовой ID пользователя:',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='◀️ Отмена', callback_data='adm_back')],
        ]),
    )
    await callback.answer()


@router.message(ManageSub.username)
async def step_manage_sub(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    query = message.text.strip()

    # Числовой ID — не нужен Telethon
    if query.lstrip('-').isdigit():
        target_id = int(query)
        name = f'ID {target_id}'
        await message.answer(
            _sub_card_text(target_id, name), parse_mode='HTML',
            reply_markup=_sub_card_kb(target_id),
        )
        return

    # Username — резолвим через любой доступный userbot
    username = query.lstrip('@')
    ref = next(
        (r for uid, r in userbot_refs.items() if uid != -1),
        userbot_refs.get(-1),
    )
    if not ref:
        await message.answer('❌ Нет подключённых аккаунтов для поиска. Введи числовой ID.')
        return

    try:
        entity = await asyncio.wait_for(
            asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(
                    ref['client'].get_entity(username),
                    ref['loop'],
                )
            ),
            timeout=15,
        )
        target_id = entity.id
        first = getattr(entity, 'first_name', '') or ''
        last  = getattr(entity, 'last_name',  '') or ''
        uname = getattr(entity, 'username',   None)
        name  = (first + ' ' + last).strip()
        if uname:
            name += f' (@{uname})'
    except asyncio.TimeoutError:
        await message.answer('❌ Таймаут: не удалось получить данные за 15 сек')
        return
    except Exception as e:
        await message.answer(f'❌ Не удалось найти пользователя: {e}')
        return

    await message.answer(
        _sub_card_text(target_id, name), parse_mode='HTML',
        reply_markup=_sub_card_kb(target_id),
    )


@router.callback_query(F.data.startswith('adm_sg_'))
async def cb_sub_give(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    target_id = int(callback.data[7:])
    extend_sub(target_id)
    await callback.answer('✅ Выдано 30 дней')
    await callback.message.edit_text(
        _sub_card_text(target_id, f'ID {target_id}'), parse_mode='HTML',
        reply_markup=_sub_card_kb(target_id),
    )


@router.callback_query(F.data.startswith('adm_se_'))
async def cb_sub_extend(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    target_id = int(callback.data[7:])
    extend_sub(target_id)
    await callback.answer('✅ Продлено на 30 дней')
    await callback.message.edit_text(
        _sub_card_text(target_id, f'ID {target_id}'), parse_mode='HTML',
        reply_markup=_sub_card_kb(target_id),
    )


@router.callback_query(F.data.startswith('adm_sr_'))
async def cb_sub_revoke(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    target_id = int(callback.data[7:])
    revoke_sub(target_id)
    await callback.answer('✅ Подписка забрана')
    await callback.message.edit_text(
        _sub_card_text(target_id, f'ID {target_id}'), parse_mode='HTML',
        reply_markup=_sub_card_kb(target_id),
    )


# ─────────────────────────────────────────────────────────────────
# Статистика
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'adm_stats')
async def cb_adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    meta        = load_meta()
    total_users = len([k for k in meta if k != 'admin_checker'])
    active_subs = count_active_subs()
    banned      = count_banned()
    text = (
        '📊 <b>Статистика</b>\n\n'
        f'👥 Пользователей: <b>{total_users}</b>\n'
        f'💎 Активных подписок: <b>{active_subs}</b>\n'
        f'🚫 Заблокировано: <b>{banned}</b>'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔍 Найти пользователя', callback_data='adm_find_user')],
        [InlineKeyboardButton(text='◀️ Назад',              callback_data='adm_back')],
    ])
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=kb)
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Поиск и карточка пользователя
# ─────────────────────────────────────────────────────────────────

class FindUser(StatesGroup):
    query = State()


def _user_card_text(target_id: int, name: str) -> str:
    sub_status = '✅ Активна' if has_active_sub(target_id) else '❌ Нет'
    if has_active_sub(target_id):
        days = max(0, (get_expiry(target_id) - int(time.time())) // 86400)
        sub_status += f', {days} дн.'
    ban_status = '🚫 Заблокирован' if is_banned(target_id) else '✅ Активен'
    return (
        f'👤 <b>Пользователь</b>\n\n'
        f'📛 {name}\n'
        f'🆔 <code>{target_id}</code>\n'
        f'💎 Подписка: {sub_status}\n'
        f'🔌 Статус: {ban_status}'
    )


def _user_card_kb(target_id: int) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text='✅ Разбанить', callback_data=f'adm_unban_{target_id}')
        if is_banned(target_id)
        else InlineKeyboardButton(text='🚫 Заблокировать', callback_data=f'adm_ban_{target_id}')
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='➕ Подписка 30д', callback_data=f'adm_sg_{target_id}'),
            InlineKeyboardButton(text='❌ Забрать',       callback_data=f'adm_sr_{target_id}'),
        ],
        [ban_btn],
        [InlineKeyboardButton(text='◀️ Назад', callback_data='adm_stats')],
    ])


@router.callback_query(F.data == 'adm_find_user')
async def cb_adm_find_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    await state.set_state(FindUser.query)
    await callback.message.edit_text(
        '🔍 Введите @username или числовой ID пользователя:',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='◀️ Отмена', callback_data='adm_stats')],
        ]),
    )
    await callback.answer()


@router.message(FindUser.query)
async def step_find_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    query = message.text.strip()

    if query.lstrip('-').isdigit():
        target_id = int(query)
        name = f'ID {target_id}'
        await message.answer(
            _user_card_text(target_id, name), parse_mode='HTML',
            reply_markup=_user_card_kb(target_id),
        )
        return

    username = query.lstrip('@')
    ref = next(
        (r for uid, r in userbot_refs.items() if uid != -1),
        userbot_refs.get(-1),
    )
    if not ref:
        await message.answer('❌ Нет подключённых аккаунтов. Введи числовой ID.')
        return
    try:
        entity = await asyncio.wait_for(
            asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(
                    ref['client'].get_entity(username), ref['loop']
                )
            ),
            timeout=15,
        )
        target_id = entity.id
        first = getattr(entity, 'first_name', '') or ''
        last  = getattr(entity, 'last_name',  '') or ''
        uname = getattr(entity, 'username',   None)
        name  = (first + ' ' + last).strip()
        if uname:
            name += f' (@{uname})'
    except asyncio.TimeoutError:
        await message.answer('❌ Таймаут: не удалось получить данные за 15 сек')
        return
    except Exception as e:
        await message.answer(f'❌ Не удалось найти пользователя: {e}')
        return

    await message.answer(
        _user_card_text(target_id, name), parse_mode='HTML',
        reply_markup=_user_card_kb(target_id),
    )


@router.callback_query(F.data.startswith('adm_ban_'))
async def cb_adm_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    target_id = int(callback.data[8:])
    ban_user(target_id)
    await callback.answer('🚫 Пользователь заблокирован')
    await callback.message.edit_text(
        _user_card_text(target_id, f'ID {target_id}'), parse_mode='HTML',
        reply_markup=_user_card_kb(target_id),
    )


@router.callback_query(F.data.startswith('adm_unban_'))
async def cb_adm_unban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    target_id = int(callback.data[10:])
    unban_user(target_id)
    await callback.answer('✅ Пользователь разбанен')
    await callback.message.edit_text(
        _user_card_text(target_id, f'ID {target_id}'), parse_mode='HTML',
        reply_markup=_user_card_kb(target_id),
    )


# ─────────────────────────────────────────────────────────────────
# Рассылка
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'adm_broadcast')
async def cb_adm_broadcast(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👥 Всем',             callback_data='adm_bc_all')],
        [InlineKeyboardButton(text='💎 С подпиской',      callback_data='adm_bc_sub')],
        [InlineKeyboardButton(text='🆓 Без подписки',     callback_data='adm_bc_nosub')],
        [InlineKeyboardButton(text='◀️ Назад',            callback_data='adm_back')],
    ])
    await callback.message.edit_text(
        '📣 <b>Рассылка</b>\n\nВыберите аудиторию:', parse_mode='HTML', reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith('adm_bc_'))
async def cb_adm_bc_audience(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer('Нет доступа')
        return
    audience = callback.data[7:]  # 'all', 'sub', 'nosub'
    await state.set_state(Broadcast.text)
    await state.update_data(audience=audience)
    await callback.message.edit_text(
        '✏️ Введите текст рассылки:',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='◀️ Отмена', callback_data='adm_broadcast')],
        ]),
    )
    await callback.answer()


@router.message(Broadcast.text)
async def step_broadcast_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data     = await state.get_data()
    audience = data.get('audience', 'all')
    await state.clear()

    meta = load_meta()
    all_ids = [int(k) for k in meta if k != 'admin_checker']

    from subscriptions import get_all_active_subs
    active_sub_ids = set(get_all_active_subs())

    if audience == 'sub':
        target_ids = [uid for uid in all_ids if uid in active_sub_ids]
    elif audience == 'nosub':
        target_ids = [uid for uid in all_ids if uid not in active_sub_ids]
    else:
        target_ids = all_ids

    sent = failed = 0
    for uid in target_ids:
        try:
            await message.bot.send_message(uid, message.text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f'📣 <b>Рассылка завершена</b>\n\n'
        f'✅ Отправлено: {sent}\n❌ Не доставлено: {failed}',
        parse_mode='HTML',
    )

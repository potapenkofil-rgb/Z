import asyncio

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
    data = await state.get_data()
    key  = f'adm_{message.from_user.id}'
    cl: TelegramClient = active[key]['client']
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
    cl: TelegramClient = active[f'adm_{message.from_user.id}']['client']
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

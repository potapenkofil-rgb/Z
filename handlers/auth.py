from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from config import PROXY
from handlers.start import _main_menu_kb, _main_menu_text
from sessions import load_meta, save_meta
from state import active
from userbot import launch_checker

router = Router()

# ─────────────────────────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────────────────────────

class Auth(StatesGroup):
    api_id   = State()
    api_hash = State()
    phone    = State()
    code     = State()
    password = State()


# ─────────────────────────────────────────────────────────────────
# Auth FSM handlers
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'auth')
async def cb_auth(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Auth.api_id)
    await callback.message.answer(
        '🔑 <b>Шаг 1 из 3 — API ID</b>\n\n'
        'Введите API ID вашего приложения:\n\n'
        'Выглядит так: <code>12345678</code>',
        parse_mode='HTML',
    )
    await callback.answer()


@router.message(Auth.api_id)
async def step_api_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer(
            '❌ API ID должен быть числом.\n\n'
            'Выглядит так: <code>12345678</code>',
            parse_mode='HTML',
        )
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(Auth.api_hash)
    await message.answer(
        '🔑 <b>Шаг 2 из 3 — API HASH</b>\n\n'
        'Введите API HASH вашего приложения:\n\n'
        'Выглядит так: <code>a1b2c3d4e5f6789012345678abcdef01</code>',
        parse_mode='HTML',
    )


@router.message(Auth.api_hash)
async def step_api_hash(message: Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(Auth.phone)
    await message.answer(
        '📱 <b>Шаг 3 из 3 — номер телефона</b>\n\n'
        'Введите номер, привязанный к аккаунту:\n\n'
        'Выглядит так: <code>+79001234567</code>',
        parse_mode='HTML',
    )


@router.message(Auth.phone)
async def step_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    data  = await state.get_data()
    cl    = TelegramClient(
        f'sessions/{message.from_user.id}',
        data['api_id'], data['api_hash'], proxy=PROXY,
    )
    try:
        await cl.connect()
        sent = await cl.send_code_request(phone)
    except ApiIdInvalidError:
        await cl.disconnect()
        await state.clear()
        await message.answer('❌ Неверный API ID или API HASH. Начните заново — /start')
        return
    except PhoneNumberInvalidError:
        await cl.disconnect()
        await state.clear()
        await message.answer('❌ Неверный номер телефона. Начните заново — /start')
        return
    await state.update_data(phone=phone, phone_code_hash=sent.phone_code_hash)
    active[message.from_user.id] = {'client': cl, 'chat_id': message.chat.id}
    await state.set_state(Auth.code)
    await message.answer(
        '📲 Код подтверждения отправлен в Telegram.\n\n'
        'Введите код <b>+1</b> к последней цифре.\n'
        'Например, если код <b>12345</b> — введите <b>12346</b>.',
        parse_mode='HTML',
    )


@router.message(Auth.code)
async def step_code(message: Message, state: FSMContext):
    try:
        code = str(int(message.text.strip()) - 1)
    except ValueError:
        await message.answer('❌ Введите числовой код:')
        return
    data    = await state.get_data()
    user_id = message.from_user.id
    entry   = active.get(user_id)
    if not entry:
        await state.clear()
        await message.answer('❌ Сессия истекла. Начните заново — /start')
        return
    cl: TelegramClient = entry['client']
    chat_id = entry['chat_id']
    try:
        await cl.sign_in(data['phone'], code, phone_code_hash=data['phone_code_hash'])
    except PhoneCodeExpiredError:
        await cl.disconnect()
        active.pop(user_id, None)
        await state.clear()
        await message.answer('❌ Код истёк. Начните заново — /start')
        return
    except PhoneCodeInvalidError:
        await message.answer('❌ Неверный код. Попробуйте ещё раз:')
        return
    except SessionPasswordNeededError:
        await state.set_state(Auth.password)
        await message.answer('🔐 Введите облачный пароль:')
        return
    await _finish_auth(message, state, user_id, chat_id, data)


@router.message(Auth.password)
async def step_password(message: Message, state: FSMContext):
    data    = await state.get_data()
    user_id = message.from_user.id
    entry   = active.get(user_id)
    if not entry:
        await state.clear()
        await message.answer('❌ Сессия истекла. Начните заново — /start')
        return
    cl: TelegramClient = entry['client']
    chat_id = entry['chat_id']
    try:
        await cl.sign_in(password=message.text)
    except Exception:
        await message.answer('❌ Неверный пароль. Попробуйте ещё раз:')
        return
    await _finish_auth(message, state, user_id, chat_id, data)


async def _finish_auth(message: Message, state: FSMContext,
                       user_id: int, chat_id: int, data: dict):
    entry = active.pop(user_id, None)
    if entry:
        try:
            await entry['client'].disconnect()
        except Exception:
            pass
    meta = load_meta()
    meta[str(user_id)] = {
        'api_id':   data['api_id'],
        'api_hash': data['api_hash'],
        'phone':    data.get('phone', ''),
        'chat_id':  chat_id,
    }
    save_meta(meta)
    await state.clear()
    await message.answer(
        '✅ <b>Аккаунт успешно подключён!</b>',
        parse_mode='HTML',
        reply_markup=_main_menu_kb(user_id),
    )
    launch_checker(user_id, data['api_id'], data['api_hash'], chat_id)

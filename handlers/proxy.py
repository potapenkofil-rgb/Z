from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from sessions import load_meta, save_meta
from state import userbot_refs

router = Router()


class SetProxy(StatesGroup):
    waiting = State()


def _proxy_text(uid: int) -> str:
    meta  = load_meta()
    proxy = meta.get(str(uid), {}).get('proxy')
    if not proxy:
        return (
            '🔌 <b>Прокси</b>\n\n'
            '📡 Текущий: <b>стандартный</b> (серверный)\n\n'
            'Поддерживается только <b>SOCKS5</b>.\n'
            'Укажи свой прокси, чтобы юзербот подключался через него.'
        )
    auth = f"{proxy['login']}:***@" if proxy.get('login') else ''
    return (
        f'🔌 <b>Прокси</b>\n\n'
        f'📡 Текущий: <code>{auth}{proxy["host"]}:{proxy["port"]}</code> (SOCKS5)\n\n'
        'После изменения нажми <b>Переподключить</b> чтобы применить.'
    )


def _proxy_kb(uid: int) -> InlineKeyboardMarkup:
    meta      = load_meta()
    has_proxy = bool(meta.get(str(uid), {}).get('proxy'))
    is_online = uid in userbot_refs
    rows = [
        [InlineKeyboardButton(text='✏️ Установить прокси', callback_data='proxy_set')],
    ]
    if has_proxy:
        rows.append([InlineKeyboardButton(text='🗑 Удалить прокси', callback_data='proxy_del')])
    if is_online:
        rows.append([InlineKeyboardButton(text='🔄 Переподключить', callback_data='proxy_reconnect')])
    rows.append([InlineKeyboardButton(text='◀️ Назад', callback_data='menu_account')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == 'proxy_menu')
async def cb_proxy_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_text(
            _proxy_text(uid), parse_mode='HTML', reply_markup=_proxy_kb(uid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(Command('proxy'))
async def cmd_proxy(message: Message):
    uid = message.from_user.id
    await message.answer(_proxy_text(uid), parse_mode='HTML', reply_markup=_proxy_kb(uid))


@router.callback_query(F.data == 'proxy_set')
async def cb_proxy_set(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetProxy.waiting)
    await callback.message.answer(
        '🔌 <b>Установка прокси</b>\n\n'
        'Поддерживается только <b>SOCKS5</b>.\n\n'
        'Введите в одном из форматов:\n'
        '<code>host:port</code>\n'
        '<code>host:port:login:password</code>\n\n'
        'Пример: <code>1.2.3.4:1080</code>',
        parse_mode='HTML',
    )
    await callback.answer()


@router.message(SetProxy.waiting)
async def step_proxy_input(message: Message, state: FSMContext):
    parts = message.text.strip().split(':')
    if len(parts) == 2:
        host, port_s = parts
        login = password = None
    elif len(parts) == 4:
        host, port_s, login, password = parts
    else:
        await message.answer(
            '❌ Неверный формат. Введите:\n'
            '<code>host:port</code> или <code>host:port:login:password</code>',
            parse_mode='HTML',
        )
        return

    try:
        port = int(port_s)
    except ValueError:
        await message.answer('❌ Порт должен быть числом.')
        return

    uid  = message.from_user.id
    meta = load_meta()
    if str(uid) not in meta:
        await state.clear()
        await message.answer('❌ Аккаунт не подключён. Начните с /start')
        return

    meta[str(uid)]['proxy'] = {
        'host':     host.strip(),
        'port':     port,
        'login':    login.strip() if login else None,
        'password': password.strip() if password else None,
    }
    save_meta(meta)
    await state.clear()
    await message.answer(
        f'✅ Прокси сохранён: <code>{host}:{port}</code>\n\n'
        'Нажми <b>Переподключить</b> в меню прокси чтобы применить.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔌 К прокси', callback_data='proxy_menu')],
            [InlineKeyboardButton(text='◀️ Меню',     callback_data='menu_main')],
        ]),
    )


@router.callback_query(F.data == 'proxy_del')
async def cb_proxy_del(callback: CallbackQuery):
    uid  = callback.from_user.id
    meta = load_meta()
    if str(uid) in meta:
        meta[str(uid)].pop('proxy', None)
        save_meta(meta)
    try:
        await callback.message.edit_text(
            _proxy_text(uid), parse_mode='HTML', reply_markup=_proxy_kb(uid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer('✅ Прокси удалён')


@router.callback_query(F.data == 'proxy_reconnect')
async def cb_proxy_reconnect(callback: CallbackQuery):
    import asyncio
    from userbot import connect_and_run
    from sessions import load_meta as lm

    uid  = callback.from_user.id
    meta = lm()
    info = meta.get(str(uid))
    if not info:
        await callback.answer('Аккаунт не найден', show_alert=True)
        return

    ref = userbot_refs.pop(uid, None)
    if ref:
        try:
            asyncio.run_coroutine_threadsafe(ref['client'].disconnect(), ref['loop'])
        except Exception:
            pass

    await callback.answer('🔄 Переподключаю…')
    await connect_and_run(uid, info['api_id'], info['api_hash'], info['chat_id'])
    try:
        await callback.message.edit_text(
            _proxy_text(uid), parse_mode='HTML', reply_markup=_proxy_kb(uid),
        )
    except TelegramBadRequest:
        pass

import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from config import SUB_TIERS
from cryptopay import create_invoice
from subscriptions import add_pending_invoice, get_expiry, has_active_sub

router = Router()

_TIER_LABELS = {
    '1m':  '1 месяц — $2',
    '3m':  '3 месяца — $6',
    '6m':  '6 месяцев — $12',
    '12m': '1 год — $24',
}


def _sub_status_text(user_id: int) -> str:
    if has_active_sub(user_id):
        expiry = get_expiry(user_id)
        days   = max(0, (expiry - int(time.time())) // 86400)
        return (
            f'💎 <b>Подписка активна</b>\n\n'
            f'⏳ Осталось дней: <b>{days}</b>\n'
            f'📨 Сообщения отправляются без рекламы'
        )
    return (
        '💎 <b>Подписка</b>\n\n'
        '❌ Не активна\n\n'
        '• К каждому сообщению добавляется реклама бота\n'
        '• Максимум 1 задача одновременно\n\n'
        '💳 Оплата через @CryptoBot'
    )


def _sub_kb(user_id: int) -> InlineKeyboardMarkup:
    label = '💳 Продлить' if has_active_sub(user_id) else '💳 Купить подписку'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label,              callback_data='sub_buy')],
        [InlineKeyboardButton(text='👥 Пригласить друга', callback_data='sub_ref')],
        [InlineKeyboardButton(text='◀️ Меню',            callback_data='menu_main')],
    ])


@router.callback_query(F.data == 'sub_menu')
async def cb_sub_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_text(
            _sub_status_text(uid), parse_mode='HTML',
            reply_markup=_sub_kb(uid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(F.text == '/ref')
async def cmd_ref(message: Message):
    uid      = message.from_user.id
    username = config.BOT_USERNAME
    if not username:
        await message.answer('❌ Реферальная ссылка недоступна — бот ещё запускается.')
        return
    link = f'https://t.me/{username}?start=ref_{uid}'
    await message.answer(
        f'👥 <b>Реферальная программа</b>\n\n'
        f'Поделись ссылкой с другом. Когда он купит подписку — ты получишь <b>+5 дней</b> бесплатно!\n\n'
        f'🔗 Твоя ссылка:\n<code>{link}</code>',
        parse_mode='HTML',
    )


@router.callback_query(F.data == 'sub_ref')
async def cb_sub_ref(callback: CallbackQuery):
    uid      = callback.from_user.id
    username = config.BOT_USERNAME
    if not username:
        await callback.answer('Реферальная ссылка пока недоступна', show_alert=True)
        return
    link = f'https://t.me/{username}?start=ref_{uid}'
    try:
        await callback.message.edit_text(
            f'👥 <b>Реферальная программа</b>\n\n'
            f'Поделись ссылкой с другом. Когда он купит подписку — ты получишь <b>+5 дней</b> бесплатно!\n\n'
            f'🔗 Твоя ссылка:\n<code>{link}</code>',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='◀️ Назад', callback_data='sub_menu')],
            ]),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == 'sub_buy')
async def cb_sub_buy(callback: CallbackQuery):
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f'sub_pay_{key}')]
        for key, label in _TIER_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text='◀️ Назад', callback_data='sub_menu')])
    await callback.message.edit_text(
        '💎 <b>Выберите период подписки:</b>',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('sub_pay_'))
async def cb_sub_pay(callback: CallbackQuery):
    tier_key = callback.data[8:]
    tier     = SUB_TIERS.get(tier_key)
    if not tier:
        await callback.answer('Неверный тариф')
        return

    price, days = tier
    uid         = callback.from_user.id
    await callback.answer('Создаю счёт…')

    try:
        invoice = await create_invoice(
            amount=price,
            asset='USDT',
            description=f'Подписка {_TIER_LABELS[tier_key]} (user {uid})',
        )
    except Exception as e:
        await callback.message.edit_text(
            f'❌ Не удалось создать счёт: {e}',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='◀️ Назад', callback_data='sub_menu')],
            ]),
        )
        return

    invoice_id = invoice['invoice_id']
    pay_url    = invoice.get('pay_url') or invoice.get('bot_invoice_url')
    add_pending_invoice(invoice_id, uid, days)

    await callback.message.edit_text(
        f'💳 <b>Счёт создан</b>\n\n'
        f'📦 Тариф: <b>{_TIER_LABELS[tier_key]}</b>\n'
        f'💰 Сумма: <b>{price} USDT</b>\n\n'
        f'Подписка активируется автоматически после оплаты (до 30 сек).',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💸 Оплатить', url=pay_url)],
            [InlineKeyboardButton(text='◀️ Меню',     callback_data='menu_main')],
        ]),
    )

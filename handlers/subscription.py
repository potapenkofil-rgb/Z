import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import SUB_PRICE_USDT
from cryptopay import create_invoice
from subscriptions import add_pending_invoice, get_expiry, has_active_sub

router = Router()


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
        f'❌ Не активна — к каждому сообщению флуда добавляется реклама бота\n\n'
        f'💰 Стоимость: <b>{SUB_PRICE_USDT} USDT / месяц</b>\n'
        f'💳 Оплата через @CryptoBot'
    )


def _sub_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if not has_active_sub(user_id):
        rows.append([InlineKeyboardButton(text='💳 Купить подписку', callback_data='sub_buy')])
    else:
        rows.append([InlineKeyboardButton(text='💳 Продлить', callback_data='sub_buy')])
    rows.append([InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == 'sub_menu')
async def cb_sub_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(
        _sub_status_text(uid), parse_mode='HTML',
        reply_markup=_sub_kb(uid),
    )
    await callback.answer()


@router.callback_query(F.data == 'sub_buy')
async def cb_sub_buy(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.answer('Создаю счёт…')

    try:
        invoice = await create_invoice(
            amount=SUB_PRICE_USDT,
            asset='USDT',
            description=f'Подписка на месяц для пользователя {uid}',
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
    add_pending_invoice(invoice_id, uid)

    text = (
        '💳 <b>Счёт создан</b>\n\n'
        f'💰 Сумма: <b>{SUB_PRICE_USDT} USDT</b>\n'
        f'⏱ Подписка активируется автоматически после оплаты (до 30 секунд).\n\n'
        f'Нажми кнопку ниже чтобы оплатить через CryptoBot.'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💸 Оплатить', url=pay_url)],
        [InlineKeyboardButton(text='◀️ Меню',     callback_data='menu_main')],
    ])
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=kb)

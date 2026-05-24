from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from balance import create_balance_invoice, get_balance, get_txn_history
from cryptopay import create_invoice

router = Router()

REASON_LABELS = {
    'deposit':    '⬆️ Пополнение',
    'ad_payment': '📢 Реклама',
    'refund':     '↩️ Возврат',
    'admin':      '🔐 Администратор',
}


class DepositFlow(StatesGroup):
    enter_amount = State()


def _balance_text(uid: int) -> str:
    bal  = get_balance(uid)
    txns = get_txn_history(uid, 7)
    lines = [f'💰 <b>Баланс: ${bal:.2f} USDT</b>\n']
    if txns:
        lines.append('📋 <b>Последние операции:</b>')
        for t in txns:
            dt    = datetime.fromtimestamp(t['created_at']).strftime('%d.%m %H:%M')
            label = REASON_LABELS.get(t['reason'], t['reason'])
            sign  = '+' if t['delta'] >= 0 else ''
            note  = f' <i>({t["note"]})</i>' if t.get('note') else ''
            lines.append(f'{label}{note}  <b>{sign}${t["delta"]:.2f}</b>  <code>{dt}</code>')
    return '\n'.join(lines)


def _balance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Пополнить', callback_data='bal_deposit')],
        [InlineKeyboardButton(text='◀️ Меню',      callback_data='menu_main')],
    ])


@router.message(Command('balance'))
async def cmd_balance(message: Message):
    await message.answer(
        _balance_text(message.from_user.id), parse_mode='HTML', reply_markup=_balance_kb(),
    )


@router.callback_query(F.data == 'bal_menu')
async def cb_bal_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            _balance_text(callback.from_user.id), parse_mode='HTML', reply_markup=_balance_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == 'bal_deposit')
async def cb_bal_deposit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositFlow.enter_amount)
    await callback.message.answer(
        '💳 <b>Пополнение баланса</b>\n\n'
        'Введите сумму в USDT <i>(минимум $1)</i>:',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='❌ Отмена', callback_data='bal_menu')],
        ]),
    )
    await callback.answer()


@router.message(DepositFlow.enter_amount)
async def step_deposit_amount(message: Message, state: FSMContext):
    raw = message.text.replace(',', '.').strip()
    try:
        amount = float(raw)
    except ValueError:
        await message.answer(
            '❌ Введите число, например: <code>10</code> или <code>5.50</code>',
            parse_mode='HTML',
        )
        return
    if amount < 1:
        await message.answer('❌ Минимальная сумма — <b>$1 USDT</b>', parse_mode='HTML')
        return
    if amount > 10_000:
        await message.answer('❌ Максимальная сумма — <b>$10 000 USDT</b>', parse_mode='HTML')
        return

    uid    = message.from_user.id
    amount = round(amount, 2)
    try:
        inv = await create_invoice(
            amount=amount,
            asset='USDT',
            description=f'Пополнение баланса ${amount:.2f}',
        )
    except Exception as e:
        await message.answer(f'❌ Ошибка создания счёта: {e}')
        return

    create_balance_invoice(uid, inv['invoice_id'], amount)
    await state.clear()

    await message.answer(
        f'✅ <b>Счёт на ${amount:.2f} USDT создан.</b>\n\n'
        'Оплатите через CryptoBot — баланс пополнится автоматически.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💳 Оплатить через CryptoBot', url=inv['pay_url'])],
            [InlineKeyboardButton(text='💰 Мой баланс', callback_data='bal_menu')],
        ]),
    )

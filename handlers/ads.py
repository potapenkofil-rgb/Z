import asyncio
from datetime import date, datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ads import (
    AD_PRICES,
    create_ad,
    get_ad,
    is_slot_taken,
    set_ad_invoice,
)
from cryptopay import create_invoice

router = Router()


# ─────────────────────────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────────────────────────

class AdFlow(StatesGroup):
    choose_type = State()
    choose_date = State()
    enter_text  = State()
    enter_url   = State()
    enter_label = State()
    confirm     = State()


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _available_dates(ad_type: str) -> list:
    """Return list of YYYY-MM-DD strings for next 7 days that are not taken
    and at least 24h from now (UTC)."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    dates = []
    for i in range(1, 8):
        d = now.date() + timedelta(days=i)
        # Check 24h constraint: show_date starts at midnight UTC, need 24h before that
        show_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
        if show_dt < cutoff:
            continue
        if is_slot_taken(d.isoformat(), ad_type):
            continue
        dates.append(d.isoformat())
    return dates


def _type_label(ad_type: str) -> str:
    return '🔘 Кнопка в меню' if ad_type == 'button' else '📨 Рассылка'


def _ads_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f'🔘 Кнопка в меню (${AD_PRICES["button"]:.0f}/день)',
            callback_data='ads_type_button',
        )],
        [InlineKeyboardButton(
            text=f'📨 Рассылка (${AD_PRICES["broadcast"]:.0f}/день)',
            callback_data='ads_type_broadcast',
        )],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')],
    ])


def _dates_kb(dates: list) -> InlineKeyboardMarkup:
    rows = []
    for d in dates:
        rows.append([InlineKeyboardButton(
            text=d, callback_data=f'ads_date_{d}',
        )])
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Оплатить', callback_data=f'ads_confirm_{ad_id}')],
        [InlineKeyboardButton(text='❌ Отмена',   callback_data='ads_cancel')],
    ])


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')],
    ])


def _skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⏭ Пропустить', callback_data='ads_skip_url')],
        [InlineKeyboardButton(text='❌ Отмена',      callback_data='ads_cancel')],
    ])


def _preview_text(data: dict) -> str:
    ad_type   = data.get('type', '')
    show_date = data.get('show_date', '')
    text      = data.get('text', '')
    url       = data.get('url') or '—'
    btn_label = data.get('btn_label') or '—'
    amount    = AD_PRICES.get(ad_type, 0)

    lines = [
        '📋 <b>Предпросмотр рекламы</b>\n',
        f'Тип:    {_type_label(ad_type)}',
        f'Дата:   {show_date}',
        f'Сумма:  ${amount:.2f} USDT\n',
        f'Текст:\n{text}',
    ]
    if ad_type == 'button':
        lines.append(f'\nСсылка: {url}')
        lines.append(f'Кнопка: {btn_label}')
    else:
        if url != '—':
            lines.append(f'\nСсылка: {url}')
            lines.append(f'Кнопка: {btn_label}')
    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────

@router.message(Command('ads'))
async def cmd_ads(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdFlow.choose_type)
    await message.answer(
        '📢 <b>Реклама в боте</b>\n\n'
        'Выберите тип размещения:',
        parse_mode='HTML',
        reply_markup=_ads_start_kb(),
    )


@router.callback_query(F.data == 'ads_start')
async def cb_ads_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdFlow.choose_type)
    await callback.message.edit_text(
        '📢 <b>Реклама в боте</b>\n\n'
        'Выберите тип размещения:',
        parse_mode='HTML',
        reply_markup=_ads_start_kb(),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 1 — choose type
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.choose_type, F.data.in_({'ads_type_button', 'ads_type_broadcast'}))
async def cb_ads_type(callback: CallbackQuery, state: FSMContext):
    ad_type = callback.data.replace('ads_type_', '')
    await state.update_data(type=ad_type)

    dates = _available_dates(ad_type)
    if not dates:
        await callback.message.edit_text(
            '😔 Нет доступных дат для размещения в ближайшие 7 дней.\n'
            '(Все слоты заняты или слишком мало времени до показа)',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='◀️ Назад', callback_data='ads_start')],
            ]),
        )
        await callback.answer()
        return

    await state.set_state(AdFlow.choose_date)
    await callback.message.edit_text(
        f'📅 Выберите дату показа ({_type_label(ad_type)}):',
        reply_markup=_dates_kb(dates),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 2 — choose date
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.choose_date, F.data.startswith('ads_date_'))
async def cb_ads_date(callback: CallbackQuery, state: FSMContext):
    show_date = callback.data[9:]  # 'ads_date_' is 9 chars

    data = await state.get_data()
    ad_type = data.get('type', '')

    # Double-check slot availability
    if is_slot_taken(show_date, ad_type):
        await callback.answer('❌ Этот слот уже занят, выберите другую дату', show_alert=True)
        return

    await state.update_data(show_date=show_date)
    await state.set_state(AdFlow.enter_text)
    await callback.message.edit_text(
        f'✏️ Введите текст рекламы (можно использовать HTML-форматирование):',
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 3 — enter text
# ─────────────────────────────────────────────────────────────────

@router.message(AdFlow.enter_text)
async def step_ads_text(message: Message, state: FSMContext):
    text = message.text or ''
    if not text.strip():
        await message.answer('Введите текст рекламы:', reply_markup=_cancel_kb())
        return

    await state.update_data(text=text.strip())

    data = await state.get_data()
    ad_type = data.get('type', '')

    if ad_type == 'button':
        # For button type, URL is required
        await state.set_state(AdFlow.enter_url)
        await message.answer(
            '🔗 Введите URL ссылки для кнопки:',
            reply_markup=_cancel_kb(),
        )
    else:
        # For broadcast, URL is optional
        await state.set_state(AdFlow.enter_url)
        await message.answer(
            '🔗 Введите URL ссылки (необязательно для рассылки):',
            reply_markup=_skip_kb(),
        )


# ─────────────────────────────────────────────────────────────────
# Step 4 — enter URL
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.enter_url, F.data == 'ads_skip_url')
async def cb_ads_skip_url(callback: CallbackQuery, state: FSMContext):
    await state.update_data(url=None, btn_label=None)
    await _show_preview(callback.message, state, edit=True)
    await callback.answer()


@router.message(AdFlow.enter_url)
async def step_ads_url(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')):
        data = await state.get_data()
        ad_type = data.get('type', '')
        if ad_type == 'button':
            await message.answer(
                '❌ Ссылка должна начинаться с http:// или https://',
                reply_markup=_cancel_kb(),
            )
        else:
            await message.answer(
                '❌ Ссылка должна начинаться с http:// или https://\nИли нажмите «Пропустить».',
                reply_markup=_skip_kb(),
            )
        return

    await state.update_data(url=url)
    await state.set_state(AdFlow.enter_label)
    await message.answer(
        '🏷 Введите текст кнопки (например: «Узнать подробнее»):',
        reply_markup=_cancel_kb(),
    )


# ─────────────────────────────────────────────────────────────────
# Step 5 — enter button label
# ─────────────────────────────────────────────────────────────────

@router.message(AdFlow.enter_label)
async def step_ads_label(message: Message, state: FSMContext):
    label = (message.text or '').strip()
    if not label:
        await message.answer('Введите текст кнопки:', reply_markup=_cancel_kb())
        return

    await state.update_data(btn_label=label)
    await _show_preview(message, state, edit=False)


# ─────────────────────────────────────────────────────────────────
# Preview & confirm
# ─────────────────────────────────────────────────────────────────

async def _show_preview(msg_or_message, state: FSMContext, edit: bool = False):
    data = await state.get_data()

    # Create ad in DB (unpaid status)
    uid = msg_or_message.chat.id if hasattr(msg_or_message, 'chat') else msg_or_message.from_user.id
    # We need user_id from state or message; use chat.id as proxy for DMs
    ad_id = create_ad(
        user_id=uid,
        ad_type=data['type'],
        text=data['text'],
        url=data.get('url'),
        btn_label=data.get('btn_label'),
        show_date=data['show_date'],
    )
    await state.update_data(ad_id=ad_id)
    await state.set_state(AdFlow.confirm)

    preview = _preview_text(data)
    kb = _confirm_kb(ad_id)

    if edit:
        await msg_or_message.edit_text(preview, parse_mode='HTML', reply_markup=kb)
    else:
        await msg_or_message.answer(preview, parse_mode='HTML', reply_markup=kb)


# ─────────────────────────────────────────────────────────────────
# Step 6 — confirm & pay
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.confirm, F.data.startswith('ads_confirm_'))
async def cb_ads_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ad_id = int(callback.data.split('_')[-1])
    ad = get_ad(ad_id)

    if not ad:
        await callback.answer('❌ Ошибка: объявление не найдено', show_alert=True)
        await state.clear()
        return

    ad_type = ad['type']
    amount = AD_PRICES[ad_type]
    show_date = ad['show_date']

    try:
        inv = await create_invoice(
            amount=amount,
            asset='USDT',
            description=f'Реклама ({_type_label(ad_type)}) на {show_date}',
        )
    except Exception as e:
        await callback.answer(f'❌ Ошибка создания счёта: {e}', show_alert=True)
        return

    invoice_id = inv['invoice_id']
    pay_url = inv['pay_url']

    set_ad_invoice(ad_id, invoice_id)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 Оплатить', url=pay_url)],
    ])
    await callback.message.edit_text(
        f'✅ <b>Счёт создан!</b>\n\n'
        f'Тип: {_type_label(ad_type)}\n'
        f'Дата показа: <b>{show_date}</b>\n'
        f'Сумма: <b>${amount:.2f} USDT</b>\n\n'
        f'Нажмите кнопку ниже для оплаты.\n'
        f'После оплаты реклама будет отправлена на проверку администратору.',
        parse_mode='HTML',
        reply_markup=kb,
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Cancel
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'ads_cancel')
async def cb_ads_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        '❌ Размещение рекламы отменено.',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📢 Разместить рекламу', callback_data='ads_start')],
            [InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')],
        ]),
    )
    await callback.answer()

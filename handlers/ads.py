from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ads import AD_PRICES, activate_ad, create_ad, get_ad, is_slot_taken, notify_admin_new_ad, set_ad_invoice
from balance import deduct_balance, get_balance
from cryptopay import create_invoice

router = Router()

RULES_TEXT = (
    '📋 <b>Правила размещения рекламы</b>\n\n'
    'Запрещено публиковать:\n\n'
    '❌ Рекламу сторонних Telegram-ботов <i>(тип «Рассылка»)</i>\n'
    '❌ Контент 18+ и материалы для взрослых\n'
    '❌ Материалы, разжигающие ненависть, дискриминацию или враждебность по любому признаку — расовому, национальному, религиозному, гендерному и иным\n'
    '❌ Контент, направленный против конкретных лиц или групп\n'
    '❌ Финансовые пирамиды, мошеннические схемы, нелицензированные казино\n'
    '❌ Нелегальные товары, вещества и услуги\n'
    '❌ Политическую агитацию и пропаганду\n\n'
    '⚠️ <b>Внимание:</b> реклама проходит модерацию. '
    'Если администратор отклонит объявление — возвращается только <b>50% оплаченной суммы</b>.\n\n'
    'Нажмите <b>«Принимаю»</b>, чтобы продолжить.'
)


# ─────────────────────────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────────────────────────

class AdFlow(StatesGroup):
    agree          = State()
    choose_type    = State()
    choose_date    = State()
    enter_content  = State()
    ask_button     = State()
    enter_btn_text = State()
    enter_btn_url  = State()
    confirm        = State()


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _available_dates(ad_type: str) -> list:
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    dates  = []
    for i in range(1, 8):
        d       = now.date() + timedelta(days=i)
        show_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        if show_dt < cutoff:
            continue
        if is_slot_taken(d.isoformat(), ad_type):
            continue
        dates.append(d.isoformat())
    return dates


def _type_label(ad_type: str) -> str:
    return '🔘 Кнопка в меню' if ad_type == 'button' else '📨 Рассылка'


def _dates_kb(dates: list) -> InlineKeyboardMarkup:
    MONTHS_RU = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    rows = []
    for d in dates:
        dt    = datetime.strptime(d, '%Y-%m-%d')
        label = f'{dt.day} {MONTHS_RU[dt.month]}'
        rows.append([InlineKeyboardButton(text=label, callback_data=f'ads_date_{d}')])
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')],
    ])


def _ask_button_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Добавить кнопку', callback_data='ads_add_btn')],
        [InlineKeyboardButton(text='⏭ Без кнопки',      callback_data='ads_skip_btn')],
        [InlineKeyboardButton(text='❌ Отмена',           callback_data='ads_cancel')],
    ])


def _confirm_kb(ad_id: int, balance: float = 0.0, amount: float = 0.0) -> InlineKeyboardMarkup:
    rows = []
    if balance >= amount > 0:
        rows.append([InlineKeyboardButton(
            text=f'💰 С баланса  (доступно ${balance:.2f})',
            callback_data=f'ads_pay_bal_{ad_id}',
        )])
    rows.append([InlineKeyboardButton(
        text='💳 CryptoBot',
        callback_data=f'ads_confirm_{ad_id}',
    )])
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_ad_preview(message: Message, data: dict):
    text       = data.get('text', '')
    url        = data.get('url')
    btn_label  = data.get('btn_label')
    media_type = data.get('media_type')
    file_id    = data.get('file_id')

    kb = None
    if url and btn_label:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_label, url=url)]
        ])

    try:
        if media_type == 'photo':
            await message.answer_photo(file_id, caption=text or None, parse_mode='HTML', reply_markup=kb)
        elif media_type == 'video':
            await message.answer_video(file_id, caption=text or None, parse_mode='HTML', reply_markup=kb)
        elif media_type == 'sticker':
            await message.answer_sticker(file_id)
            if text or kb:
                await message.answer(text or '​', parse_mode='HTML', reply_markup=kb)
        else:
            await message.answer(text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        await message.answer(f'⚠️ Ошибка предпросмотра: {e}')


async def _go_to_confirm(msg: Message, state: FSMContext, uid: int, edit: bool = False):
    data = await state.get_data()

    ad_id = create_ad(
        user_id=uid,
        ad_type=data['type'],
        text=data.get('text', ''),
        url=data.get('url'),
        btn_label=data.get('btn_label'),
        show_date=data['show_date'],
        media_type=data.get('media_type'),
        file_id=data.get('file_id'),
    )
    await state.update_data(ad_id=ad_id)
    await state.set_state(AdFlow.confirm)

    ad_type   = data['type']
    show_date = data['show_date']
    amount    = AD_PRICES[ad_type]
    balance   = get_balance(uid)

    summary = (
        f'📋 <b>Параметры объявления</b>\n\n'
        f'Тип: {_type_label(ad_type)}\n'
        f'Дата: <b>{show_date}</b>\n'
        f'Стоимость: <b>${amount:.2f} USDT</b>\n'
        f'Ваш баланс: <b>${balance:.2f}</b>\n'
    )
    if data.get('btn_label'):
        summary += f'Кнопка: «{data["btn_label"]}»'
        if data.get('url'):
            summary += f' → {data["url"]}'
        summary += '\n'

    kb = _confirm_kb(ad_id, balance, amount)

    if ad_type == 'broadcast':
        summary += '\n👆 <i>Выше — предпросмотр вашей рекламы</i>'
        try:
            await msg.answer('👁 <b>Предпросмотр:</b>', parse_mode='HTML')
            await _send_ad_preview(msg, data)
        except Exception:
            pass
        await msg.answer(summary, parse_mode='HTML', reply_markup=kb)
    else:
        if edit:
            try:
                await msg.edit_text(summary, parse_mode='HTML', reply_markup=kb)
                return
            except TelegramBadRequest:
                pass
        await msg.answer(summary, parse_mode='HTML', reply_markup=kb)


# ─────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────

@router.message(Command('ads'))
async def cmd_ads(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdFlow.agree)
    await message.answer(RULES_TEXT, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Принимаю', callback_data='ads_agree')],
        [InlineKeyboardButton(text='❌ Отмена',   callback_data='ads_cancel')],
    ]))


@router.callback_query(F.data == 'ads_start')
async def cb_ads_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdFlow.agree)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Принимаю', callback_data='ads_agree')],
        [InlineKeyboardButton(text='❌ Отмена',   callback_data='ads_cancel')],
    ])
    try:
        await callback.message.edit_text(RULES_TEXT, parse_mode='HTML', reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.answer(RULES_TEXT, parse_mode='HTML', reply_markup=kb)
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 0 — agree
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.agree, F.data == 'ads_agree')
async def cb_ads_agree(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdFlow.choose_type)
    await callback.message.edit_text(
        '📢 <b>Выберите тип размещения</b>\n\n'
        '🔘 <b>Кнопка в меню</b> — ваша кнопка-ссылка появляется внизу главного меню у всех пользователей на весь день.\n\n'
        '📨 <b>Рассылка</b> — ваше сообщение (текст, фото, видео или стикер) отправляется всем пользователям бота в 15:00 UTC.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f'🔘 Кнопка в меню  —  ${AD_PRICES["button"]:.0f}/день',
                callback_data='ads_type_button',
            )],
            [InlineKeyboardButton(
                text=f'📨 Рассылка  —  ${AD_PRICES["broadcast"]:.0f}/день',
                callback_data='ads_type_broadcast',
            )],
            [InlineKeyboardButton(text='❌ Отмена', callback_data='ads_cancel')],
        ]),
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
            '😔 Нет доступных дат на ближайшие 7 дней.\n'
            'Все слоты заняты или осталось менее 24 часов до показа.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='◀️ Назад', callback_data='ads_agree')],
            ]),
        )
        await callback.answer()
        return

    await state.set_state(AdFlow.choose_date)
    await callback.message.edit_text(
        f'{_type_label(ad_type)}\n\n📅 Выберите дату показа:',
        reply_markup=_dates_kb(dates),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 2 — choose date
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.choose_date, F.data.startswith('ads_date_'))
async def cb_ads_date(callback: CallbackQuery, state: FSMContext):
    show_date = callback.data[9:]
    data      = await state.get_data()
    ad_type   = data.get('type', '')

    if is_slot_taken(show_date, ad_type):
        await callback.answer('❌ Слот уже занят, выберите другую дату', show_alert=True)
        return

    await state.update_data(show_date=show_date)
    await state.set_state(AdFlow.enter_content)

    if ad_type == 'button':
        await callback.message.edit_text(
            '🔘 <b>Кнопка в меню</b>\n\n'
            'Введите текст кнопки, который увидят пользователи в главном меню:',
            parse_mode='HTML',
            reply_markup=_cancel_kb(),
        )
    else:
        await callback.message.edit_text(
            '📨 <b>Рассылка</b>\n\n'
            'Отправьте содержимое рекламы:\n\n'
            '• <b>Текст</b> — поддерживается <b>жирный</b>, <i>курсив</i>, '
            '<u>подчёркнутый</u>, <code>моноширинный</code> и другие форматы '
            '(нативное Telegram-форматирование или HTML)\n'
            '• <b>Фото</b> с подписью\n'
            '• <b>Видео</b> с подписью\n'
            '• <b>Премиум стикер</b>',
            parse_mode='HTML',
            reply_markup=_cancel_kb(),
        )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Step 3 — enter content
# ─────────────────────────────────────────────────────────────────

@router.message(AdFlow.enter_content)
async def step_ads_content(message: Message, state: FSMContext):
    data    = await state.get_data()
    ad_type = data.get('type', '')

    if ad_type == 'button':
        label = (message.text or '').strip()
        if not label:
            await message.answer('Введите текст кнопки:', reply_markup=_cancel_kb())
            return
        await state.update_data(btn_label=label, text=label, media_type=None, file_id=None)
        await state.set_state(AdFlow.enter_btn_url)
        await message.answer(
            '🔗 Введите URL ссылки для кнопки\n<i>Начинается с https://</i>',
            parse_mode='HTML',
            reply_markup=_cancel_kb(),
        )
        return

    # Broadcast — accept text, photo, video, sticker
    if message.sticker:
        await state.update_data(media_type='sticker', file_id=message.sticker.file_id, text='')
    elif message.photo:
        await state.update_data(
            media_type='photo',
            file_id=message.photo[-1].file_id,
            text=message.caption or '',
        )
    elif message.video:
        await state.update_data(
            media_type='video',
            file_id=message.video.file_id,
            text=message.caption or '',
        )
    elif message.text:
        text = message.text.strip()
        if not text:
            await message.answer('Введите текст рекламы:', reply_markup=_cancel_kb())
            return
        await state.update_data(media_type=None, file_id=None, text=text)
    else:
        await message.answer(
            '❌ Неподдерживаемый тип контента.\n'
            'Отправьте текст, фото, видео или стикер.',
            reply_markup=_cancel_kb(),
        )
        return

    await state.set_state(AdFlow.ask_button)
    await message.answer(
        '✅ Контент принят.\n\nДобавить кнопку-ссылку под рекламой?',
        reply_markup=_ask_button_kb(),
    )


# ─────────────────────────────────────────────────────────────────
# Step 4 — button choice (broadcast)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.ask_button, F.data == 'ads_add_btn')
async def cb_ads_add_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdFlow.enter_btn_text)
    await callback.message.edit_text(
        '🏷 Введите текст кнопки\n<i>Например: «Узнать подробнее»</i>',
        parse_mode='HTML',
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(AdFlow.ask_button, F.data == 'ads_skip_btn')
async def cb_ads_skip_btn(callback: CallbackQuery, state: FSMContext):
    await state.update_data(url=None, btn_label=None)
    await callback.answer()
    await _go_to_confirm(callback.message, state, uid=callback.from_user.id, edit=False)


# ─────────────────────────────────────────────────────────────────
# Step 5 — button text + URL
# ─────────────────────────────────────────────────────────────────

@router.message(AdFlow.enter_btn_text)
async def step_ads_btn_text(message: Message, state: FSMContext):
    label = (message.text or '').strip()
    if not label:
        await message.answer('Введите текст кнопки:', reply_markup=_cancel_kb())
        return
    await state.update_data(btn_label=label)
    await state.set_state(AdFlow.enter_btn_url)
    await message.answer('🔗 Введите URL ссылки:', reply_markup=_cancel_kb())


@router.message(AdFlow.enter_btn_url)
async def step_ads_btn_url(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')):
        await message.answer(
            '❌ URL должен начинаться с https:// или http://',
            reply_markup=_cancel_kb(),
        )
        return
    await state.update_data(url=url)
    await _go_to_confirm(message, state, uid=message.from_user.id, edit=False)


# ─────────────────────────────────────────────────────────────────
# Confirm & pay
# ─────────────────────────────────────────────────────────────────

@router.callback_query(AdFlow.confirm, F.data.startswith('ads_pay_bal_'))
async def cb_ads_pay_balance(callback: CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.split('_')[-1])
    ad    = get_ad(ad_id)
    if not ad:
        await callback.answer('❌ Объявление не найдено', show_alert=True)
        await state.clear()
        return

    amount = AD_PRICES[ad['type']]
    uid    = callback.from_user.id

    ok = deduct_balance(uid, amount, 'ad_payment', f'Реклама #{ad_id} · {ad["show_date"]}')
    if not ok:
        await callback.answer('❌ Недостаточно средств на балансе', show_alert=True)
        return

    activate_ad(ad_id)
    await state.clear()

    try:
        await notify_admin_new_ad(ad_id)
    except Exception:
        pass

    await callback.message.edit_text(
        f'✅ <b>Оплачено с баланса!</b>\n\n'
        f'Тип: {_type_label(ad["type"])}\n'
        f'Дата показа: <b>{ad["show_date"]}</b>\n'
        f'Сумма: <b>${amount:.2f} USDT</b>\n\n'
        'Реклама отправлена на проверку администратору.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💰 Баланс', callback_data='bal_menu')],
            [InlineKeyboardButton(text='◀️ Меню',   callback_data='menu_main')],
        ]),
    )
    await callback.answer()


@router.callback_query(AdFlow.confirm, F.data.startswith('ads_confirm_'))
async def cb_ads_confirm(callback: CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.split('_')[-1])
    ad    = get_ad(ad_id)

    if not ad:
        await callback.answer('❌ Объявление не найдено', show_alert=True)
        await state.clear()
        return

    amount    = AD_PRICES[ad['type']]
    show_date = ad['show_date']

    try:
        inv = await create_invoice(
            amount=amount,
            asset='USDT',
            description=f'Реклама ({_type_label(ad["type"])}) на {show_date}',
        )
    except Exception as e:
        await callback.answer(f'❌ Ошибка: {e}', show_alert=True)
        return

    set_ad_invoice(ad_id, inv['invoice_id'])
    await state.clear()

    await callback.message.edit_text(
        f'✅ <b>Счёт создан!</b>\n\n'
        f'Тип: {_type_label(ad["type"])}\n'
        f'Дата показа: <b>{show_date}</b>\n'
        f'Сумма: <b>${amount:.2f} USDT</b>\n\n'
        'После оплаты реклама поступит на проверку администратору.',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💳 Оплатить через CryptoBot', url=inv['pay_url'])],
        ]),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Cancel
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'ads_cancel')
async def cb_ads_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            '❌ Размещение рекламы отменено.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='📢 Разместить рекламу', callback_data='ads_start')],
                [InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')],
            ]),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

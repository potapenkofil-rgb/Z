from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from tasks import _t_by_tmpl
from templates import (
    delete_template_by_rowid,
    get_template_by_rowid,
    list_templates,
    update_template,
)

router = Router()


class EditTemplate(StatesGroup):
    rowid    = State()
    new_name = State()
    new_text = State()


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _card_text(name: str, text: str, tasks: list) -> str:
    preview = text[:200] + ('…' if len(text) > 200 else '')
    if tasks:
        ids   = [f'<code>#{t.id}</code>' for t in tasks[:5]]
        extra = len(tasks) - 5
        usage = ', '.join(ids)
        if extra > 0:
            usage += f' и ещё в {extra} задачах'
        used  = f'✅ Используется в задачах: {usage}'
    else:
        used = '❌ Не используется в активных задачах'
    return (
        f'📋 <b>Шаблон: {name}</b>\n\n'
        f'{used}\n\n'
        f'💬 <b>Текст:</b>\n<blockquote>{preview}</blockquote>'
    )


def _card_kb(rowid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✏️ Изменить', callback_data=f'tmpl_edit_{rowid}'),
            InlineKeyboardButton(text='❌ Удалить',  callback_data=f'tmpl_del_{rowid}'),
        ],
        [InlineKeyboardButton(text='◀️ Назад', callback_data='tmpl_list')],
    ])


def _list_kb(user_id: int) -> InlineKeyboardMarkup:
    tmpls = list_templates(user_id)
    if not tmpls:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f'tmpl_view_{rowid}')]
        for rowid, name, _ in tmpls
    ] + [[InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')]])


# ─────────────────────────────────────────────────────────────────
# Template list (back button)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'tmpl_list')
async def cb_tmpl_list(callback: CallbackQuery):
    uid = callback.from_user.id
    kb  = _list_kb(uid)
    try:
        await callback.message.edit_text('📋 <b>Шаблоны:</b>', parse_mode='HTML', reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Template card
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('tmpl_view_'))
async def cb_tmpl_view(callback: CallbackQuery):
    rowid = int(callback.data[10:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, text = row
    tasks = _t_by_tmpl(uid, name)
    try:
        await callback.message.edit_text(
            _card_text(name, text, tasks),
            parse_mode='HTML',
            reply_markup=_card_kb(rowid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Delete template
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('tmpl_del_'))
async def cb_tmpl_del(callback: CallbackQuery):
    rowid = int(callback.data[9:])
    uid   = callback.from_user.id
    if delete_template_by_rowid(rowid, uid):
        await callback.answer('✅ Шаблон удалён')
    else:
        await callback.answer('Шаблон не найден')
    kb = _list_kb(uid)
    try:
        await callback.message.edit_text('📋 <b>Шаблоны:</b>', parse_mode='HTML', reply_markup=kb)
    except TelegramBadRequest:
        pass


# ─────────────────────────────────────────────────────────────────
# Edit template — FSM
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('tmpl_edit_'))
async def cb_tmpl_edit(callback: CallbackQuery, state: FSMContext):
    rowid = int(callback.data[10:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, _ = row
    await state.set_state(EditTemplate.new_name)
    await state.update_data(rowid=rowid, old_name=name)
    await callback.message.edit_text(
        f'✏️ <b>Изменение шаблона «{name}»</b>\n\n'
        f'Введите новое название (или <code>-</code> чтобы оставить прежнее):',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='❌ Отмена', callback_data=f'tmpl_view_{rowid}')],
        ]),
    )
    await callback.answer()


@router.message(EditTemplate.new_name)
async def step_tmpl_new_name(message: Message, state: FSMContext):
    data     = await state.get_data()
    rowid    = data['rowid']
    old_name = data['old_name']
    new_name = message.text.strip()
    if new_name == '-':
        new_name = old_name
    await state.update_data(new_name=new_name)
    await state.set_state(EditTemplate.new_text)

    row = get_template_by_rowid(rowid, message.from_user.id)
    cur_text = row[1] if row else ''
    await message.answer(
        f'✏️ Введите новый текст шаблона (или <code>-</code> чтобы оставить прежний):\n\n'
        f'<blockquote>{cur_text[:300]}</blockquote>',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='❌ Отмена', callback_data=f'tmpl_view_{rowid}')],
        ]),
    )


@router.message(EditTemplate.new_text)
async def step_tmpl_new_text(message: Message, state: FSMContext):
    data     = await state.get_data()
    rowid    = data['rowid']
    new_name = data['new_name']
    uid      = message.from_user.id

    row = get_template_by_rowid(rowid, uid)
    if not row:
        await state.clear()
        await message.answer('❌ Шаблон не найден')
        return

    old_text = row[1]
    new_text = message.text.strip()
    if new_text == '-':
        new_text = old_text

    update_template(rowid, uid, new_name, new_text)
    await state.clear()

    tasks = _t_by_tmpl(uid, new_name)
    await message.answer(
        _card_text(new_name, new_text, tasks),
        parse_mode='HTML',
        reply_markup=_card_kb(rowid),
    )

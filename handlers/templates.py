import os
import re

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
    add_to_blacklist,
    delete_template_by_rowid,
    get_blacklist,
    get_template_by_rowid,
    list_templates,
    remove_from_blacklist,
    save_template,
    update_template,
)

router = Router()


class NewTemplate(StatesGroup):
    name = State()
    text = State()


class EditTemplate(StatesGroup):
    edit_name = State()
    edit_text = State()


class AddBlacklist(StatesGroup):
    chat_id = State()


# ─────────────────────────────────────────────────────────────────
# Template list
# ─────────────────────────────────────────────────────────────────

def _list_kb(user_id: int) -> InlineKeyboardMarkup:
    tmpls = list_templates(user_id)
    rows = [
        [InlineKeyboardButton(text=name or '(без названия)', callback_data=f'tmpl_view_{rowid}')]
        for rowid, name, _ in tmpls
    ]
    rows.append([InlineKeyboardButton(text='➕ Новый шаблон', callback_data='tmpl_new')])
    rows.append([InlineKeyboardButton(text='◀️ Меню', callback_data='menu_main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
# New template FSM
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'tmpl_new')
async def cb_tmpl_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTemplate.name)
    await callback.message.answer('📌 Введите название шаблона:')
    await callback.answer()


@router.message(NewTemplate.name)
async def step_tmpl_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(NewTemplate.text)
    await message.answer('✏️ Введите текст шаблона:')


@router.message(NewTemplate.text)
async def step_tmpl_text(message: Message, state: FSMContext):
    data = await state.get_data()
    uid  = message.from_user.id
    save_template(uid, data['name'], message.text)
    await state.clear()
    await message.answer(
        f'✅ Шаблон <b>{data["name"]}</b> сохранён!',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📋 К шаблонам', callback_data='tmpl_list')],
            [InlineKeyboardButton(text='◀️ Меню',       callback_data='menu_main')],
        ]),
    )


# ─────────────────────────────────────────────────────────────────
# Template card
# ─────────────────────────────────────────────────────────────────

def _card_text(name: str, text: str, tasks: list, media_path: str | None = None) -> str:
    preview = text[:200] + ('…' if len(text) > 200 else '') if text else '<i>без текста</i>'
    if tasks:
        ids   = [f'<code>#{t.id}</code>' for t in tasks[:5]]
        extra = len(tasks) - 5
        usage = ', '.join(ids)
        if extra > 0:
            usage += f' и ещё в {extra} задачах'
        used  = f'✅ Используется в задачах: {usage}'
    else:
        used = '❌ Не используется в активных задачах'
    media_line = '\n🖼 <b>Медиа:</b> прикреплено\n' if media_path else ''
    return (
        f'📋 <b>Шаблон: {name}</b>\n\n'
        f'{used}\n'
        f'{media_line}\n'
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


def _edit_choice_kb(rowid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✏️ Название', callback_data=f'tmpl_editname_{rowid}'),
            InlineKeyboardButton(text='📝 Текст',    callback_data=f'tmpl_edittext_{rowid}'),
        ],
        [InlineKeyboardButton(text='◀️ Назад', callback_data=f'tmpl_view_{rowid}')],
    ])


def _cancel_kb(rowid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отмена', callback_data=f'tmpl_view_{rowid}')],
    ])


@router.callback_query(F.data.startswith('tmpl_view_'))
async def cb_tmpl_view(callback: CallbackQuery):
    rowid = int(callback.data[10:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, text, media_path = row
    tasks = _t_by_tmpl(uid, name)
    try:
        await callback.message.edit_text(
            _card_text(name, text, tasks, media_path),
            parse_mode='HTML',
            reply_markup=_card_kb(rowid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


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
# Edit template
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('tmpl_edit_'))
async def cb_tmpl_edit(callback: CallbackQuery):
    rowid = int(callback.data[10:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, _, _mp = row
    try:
        await callback.message.edit_text(
            f'✏️ <b>Изменение шаблона «{name}»</b>\n\nЧто изменить?',
            parse_mode='HTML',
            reply_markup=_edit_choice_kb(rowid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith('tmpl_editname_'))
async def cb_tmpl_editname(callback: CallbackQuery, state: FSMContext):
    rowid = int(callback.data[14:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, _, _mp = row
    await state.set_state(EditTemplate.edit_name)
    await state.update_data(rowid=rowid, old_name=name)
    try:
        await callback.message.edit_text(
            f'✏️ Введите новое название шаблона:\n\nТекущее: <b>{name}</b>',
            parse_mode='HTML',
            reply_markup=_cancel_kb(rowid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(EditTemplate.edit_name)
async def step_edit_name(message: Message, state: FSMContext):
    data     = await state.get_data()
    rowid    = data['rowid']
    uid      = message.from_user.id
    new_name = message.text.strip()
    if not new_name:
        await message.answer('❌ Название не может быть пустым. Введите название:')
        return
    row = get_template_by_rowid(rowid, uid)
    if not row:
        await state.clear()
        await message.answer('❌ Шаблон не найден')
        return
    _, old_text, media_path = row
    update_template(rowid, uid, new_name, old_text, media_path)
    await state.clear()
    tasks = _t_by_tmpl(uid, new_name)
    await message.answer(
        _card_text(new_name, old_text, tasks, media_path),
        parse_mode='HTML',
        reply_markup=_card_kb(rowid),
    )


@router.callback_query(F.data.startswith('tmpl_edittext_'))
async def cb_tmpl_edittext(callback: CallbackQuery, state: FSMContext):
    rowid = int(callback.data[14:])
    uid   = callback.from_user.id
    row   = get_template_by_rowid(rowid, uid)
    if not row:
        await callback.answer('Шаблон не найден')
        return
    name, text, _mp = row
    await state.set_state(EditTemplate.edit_text)
    await state.update_data(rowid=rowid, name=name)
    try:
        await callback.message.edit_text(
            f'📝 Введите новый текст шаблона <b>{name}</b>:\n\n'
            f'<blockquote>{text[:300]}</blockquote>',
            parse_mode='HTML',
            reply_markup=_cancel_kb(rowid),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(EditTemplate.edit_text)
async def step_edit_text(message: Message, state: FSMContext):
    data     = await state.get_data()
    rowid    = data['rowid']
    name     = data['name']
    uid      = message.from_user.id
    new_text = message.text.strip()
    row = get_template_by_rowid(rowid, uid)
    if not row:
        await state.clear()
        await message.answer('❌ Шаблон не найден')
        return
    _, _, media_path = row
    update_template(rowid, uid, name, new_text, media_path)
    await state.clear()
    tasks = _t_by_tmpl(uid, name)
    await message.answer(
        _card_text(name, new_text, tasks, media_path),
        parse_mode='HTML',
        reply_markup=_card_kb(rowid),
    )


# ─────────────────────────────────────────────────────────────────
# Media template: send media with caption "/template название"
# ─────────────────────────────────────────────────────────────────

@router.message(
    F.content_type.in_({'photo', 'video', 'document', 'animation'})
    & F.caption.regexp(r'^/template\s+\S+')
)
async def cmd_template_media(message: Message):
    caption = message.caption or ''
    m = re.match(r'^/template\s+(\S+)', caption)
    if not m:
        return
    name = m.group(1)
    uid  = message.from_user.id

    os.makedirs('sessions/media_templates', exist_ok=True)
    safe_name = re.sub(r'[^\w\-]', '_', name)
    dest = f'sessions/media_templates/{uid}_{safe_name}'

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.animation:
        file_id = message.animation.file_id
    else:
        file_id = message.document.file_id

    await message.bot.download(file_id, destination=dest)
    save_template(uid, name, '', media_path=dest)

    await message.answer(
        f'✅ Медиашаблон <b>{name}</b> сохранён!',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📋 К шаблонам', callback_data='tmpl_list')],
            [InlineKeyboardButton(text='◀️ Меню',       callback_data='menu_main')],
        ]),
    )


# ─────────────────────────────────────────────────────────────────
# Blacklist
# ─────────────────────────────────────────────────────────────────

def _bl_text(uid: int) -> str:
    bl = get_blacklist(uid)
    if not bl:
        return '🚫 <b>Чёрный список</b>\n\n<i>Список пуст</i>'
    lines = [
        f'• {title or chat_id}  <code>{chat_id}</code>'
        for chat_id, title in bl
    ]
    return '🚫 <b>Чёрный список</b>\n\n' + '\n'.join(lines)


def _bl_kb(uid: int) -> InlineKeyboardMarkup:
    bl   = get_blacklist(uid)
    rows = []
    for chat_id, title in bl:
        label = title or str(chat_id)
        rows.append([InlineKeyboardButton(
            text=f'❌ {label}', callback_data=f'bl_del_{chat_id}'
        )])
    rows.append([InlineKeyboardButton(text='➕ Добавить', callback_data='bl_add')])
    rows.append([InlineKeyboardButton(text='◀️ Меню',    callback_data='menu_main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == 'bl_list')
async def cb_bl_list(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(_bl_text(uid), parse_mode='HTML', reply_markup=_bl_kb(uid))
    await callback.answer()


@router.callback_query(F.data.startswith('bl_del_'))
async def cb_bl_del(callback: CallbackQuery):
    uid     = callback.from_user.id
    chat_id = int(callback.data[7:])
    remove_from_blacklist(uid, chat_id)
    await callback.message.edit_text(_bl_text(uid), parse_mode='HTML', reply_markup=_bl_kb(uid))
    await callback.answer('✅ Удалён из чёрного списка')


@router.callback_query(F.data == 'bl_add')
async def cb_bl_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddBlacklist.chat_id)
    await callback.message.answer('🚫 Введите ID чата:')
    await callback.answer()


@router.message(AddBlacklist.chat_id)
async def step_bl_chat_id(message: Message, state: FSMContext):
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.answer('❌ Введите числовой ID чата:')
        return
    uid = message.from_user.id
    add_to_blacklist(uid, chat_id)
    await state.clear()
    await message.answer(
        f'✅ Чат <code>{chat_id}</code> добавлен в чёрный список',
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🚫 К списку', callback_data='bl_list')],
            [InlineKeyboardButton(text='◀️ Меню',    callback_data='menu_main')],
        ]),
    )

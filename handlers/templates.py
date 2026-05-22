from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from templates import (
    add_template,
    add_to_blacklist,
    delete_template,
    get_blacklist,
    get_templates,
    remove_from_blacklist,
)

router = Router()


class NewTemplate(StatesGroup):
    name = State()
    text = State()


class AddBlacklist(StatesGroup):
    chat_id = State()


# ─────────────────────────────────────────────────────────────────
# Templates list
# ─────────────────────────────────────────────────────────────────

def _tmpl_text(uid: int) -> str:
    items = get_templates(uid)
    if not items:
        return '📋 <b>Шаблоны</b>\n\n<i>Нет шаблонов</i>'
    lines = []
    for t in items:
        preview = (t['text'][:50] + '…') if len(t['text']) > 50 else t['text']
        lines.append(f'📌 <b>{t["name"]}</b>\n   <i>{preview}</i>')
    return '📋 <b>Шаблоны</b>\n\n' + '\n\n'.join(lines)


def _tmpl_kb(uid: int) -> InlineKeyboardMarkup:
    items = get_templates(uid)
    rows = []
    for t in items:
        rows.append([InlineKeyboardButton(
            text=f'❌ {t["name"]}', callback_data=f'tmpl_del_{t["id"]}'
        )])
    rows.append([InlineKeyboardButton(text='➕ Новый шаблон', callback_data='tmpl_new')])
    rows.append([InlineKeyboardButton(text='◀️ Меню',         callback_data='menu_main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == 'tmpl_list')
async def cb_tmpl_list(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(_tmpl_text(uid), parse_mode='HTML', reply_markup=_tmpl_kb(uid))
    await callback.answer()


@router.callback_query(F.data.startswith('tmpl_del_'))
async def cb_tmpl_del(callback: CallbackQuery):
    uid = callback.from_user.id
    tid = int(callback.data[9:])
    delete_template(tid, uid)
    await callback.message.edit_text(_tmpl_text(uid), parse_mode='HTML', reply_markup=_tmpl_kb(uid))
    await callback.answer('✅ Шаблон удалён')


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
    add_template(uid, data['name'], message.text)
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
# Blacklist
# ─────────────────────────────────────────────────────────────────

def _bl_text(uid: int) -> str:
    bl = get_blacklist(uid)
    if not bl:
        return '🚫 <b>Чёрный список</b>\n\n<i>Список пуст</i>'
    lines = [
        f'• {e["title"] or e["chat_id"]}  <code>{e["chat_id"]}</code>'
        for e in bl
    ]
    return '🚫 <b>Чёрный список</b>\n\n' + '\n'.join(lines)


def _bl_kb(uid: int) -> InlineKeyboardMarkup:
    bl   = get_blacklist(uid)
    rows = []
    for e in bl:
        label = e['title'] or str(e['chat_id'])
        rows.append([InlineKeyboardButton(
            text=f'❌ {label}', callback_data=f'bl_del_{e["chat_id"]}'
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

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()

# ─────────────────────────────────────────────────────────────────
# Guide UI helpers
# ─────────────────────────────────────────────────────────────────

def _guide_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📨 /flood',      callback_data='guide_flood'),
            InlineKeyboardButton(text='📁 /gflood',     callback_data='guide_gflood'),
        ],
        [
            InlineKeyboardButton(text='📋 Задачи',      callback_data='guide_tasks'),
            InlineKeyboardButton(text='🏓 /ping',       callback_data='guide_ping'),
        ],
        [
            InlineKeyboardButton(text='🚫 /noflood',    callback_data='guide_noflood'),
            InlineKeyboardButton(text='📵 /blacklist',  callback_data='guide_blacklist'),
        ],
        [
            InlineKeyboardButton(text='📝 /template',   callback_data='guide_template'),
            InlineKeyboardButton(text='🗂 /templates',  callback_data='guide_templates'),
        ],
        [InlineKeyboardButton(text='◀️ Меню',           callback_data='menu_main')],
    ])

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='◀️ Назад', callback_data='guide_main')],
    ])


# ─────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'guide_main')
async def cb_guide_main(callback: CallbackQuery):
    await callback.message.edit_text(
        '📖 <b>Гайд по командам</b>\n\nВыберите раздел:',
        parse_mode='HTML',
        reply_markup=_guide_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == 'guide_flood')
async def cb_guide_flood(callback: CallbackQuery):
    text = (
        '📨 <b>/flood — рассылка в чате</b>\n\n'
        'Отправляет сообщение N раз с заданной задержкой.\n\n'
        '<b>Формат:</b>\n'
        '<code>/flood [задержка] [кол-во] [текст] [флаги]</code>\n\n'
        '<b>Примеры:</b>\n'
        '<code>/flood 5 10 Привет!</code>\n'
        '→ отправит "Привет!" 10 раз, каждые 5 секунд\n\n'
        '<code>/flood 2 50</code> + прикреплённое фото\n'
        '→ перешлёт фото 50 раз с паузой 2 секунды\n\n'
        '<b>Флаги тегирования:</b>\n'
        '<code>--tagall</code> — скрыто тегает до 50 последних участников (кроме ботов)\n'
        '<code>--tagallwa</code> — то же, но также без администраторов\n\n'
        '<b>Пример:</b>\n'
        '<code>/flood 5 10 Акция! --tagallwa</code>\n\n'
        '💡 Команду пишите прямо в нужном чате'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_gflood')
async def cb_guide_gflood(callback: CallbackQuery):
    text = (
        '📁 <b>/gflood — рассылка по папке</b>\n\n'
        'Отправляет сообщение во все чаты выбранной папки.\n\n'
        '<b>Формат:</b>\n'
        '<code>/gflood [режим] [задержка] [кол-во] [текст] [флаги]</code>\n\n'
        '<b>Режимы:</b>\n'
        '  <code>s</code> — сразу во все чаты одновременно\n'
        '  <code>o</code> — по очереди, с задержкой между чатами\n\n'
        '<b>Флаги тегирования:</b>\n'
        '<code>--tagall</code> — скрыто тегает до 50 последних участников (кроме ботов)\n'
        '<code>--tagallwa</code> — то же, но также без администраторов\n\n'
        '<b>Примеры:</b>\n'
        '<code>/gflood s 3 5 Текст объявления</code>\n'
        '→ 5 раундов по всем чатам папки, интервал 3 сек\n\n'
        '<code>/gflood o 2 3 Акция --tagallwa</code>\n'
        '→ рассылка по очереди со скрытым тегом участников\n\n'
        '💡 После команды бот попросит выбрать папку'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_tasks')
async def cb_guide_tasks(callback: CallbackQuery):
    text = (
        '📋 <b>Управление задачами</b>\n\n'
        '<code>/tasks</code>\n'
        '→ список всех активных задач\n\n'
        '<code>/task [ID] ...</code>\n'
        '→ карточка задачи (до 5 ID через пробел)\n\n'
        '<code>/stop [ID] ...</code>\n'
        '→ остановить задачи (до 10 ID через пробел)\n'
        'Пример: <code>/stop 1 3 7</code>\n\n'
        '<code>/floodstop</code>\n'
        '→ остановить все рассылки в текущем чате\n\n'
        '💡 На карточке задачи есть кнопки паузы и стопа'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_ping')
async def cb_guide_ping(callback: CallbackQuery):
    text = (
        '🏓 <b>/ping — задержка соединения</b>\n\n'
        'Измеряет время отклика Telegram API.\n\n'
        '<b>Использование:</b>\n'
        '<code>/ping</code>\n\n'
        '💡 В чате с ботом сообщение остаётся\n'
        '💡 В других чатах удаляется через 1 секунду'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_noflood')
async def cb_guide_noflood(callback: CallbackQuery):
    text = (
        '🚫 <b>/noflood — запрет рассылки в чат</b>\n\n'
        'Добавляет или убирает текущий чат из чёрного списка.\n'
        'Flood и gflood не будут отправлять в заблокированные чаты.\n\n'
        '<b>Использование:</b>\n'
        '<code>/noflood</code> — добавить чат в чёрный список\n'
        '<code>/noflood off</code> — убрать чат из чёрного списка\n\n'
        '💡 Команды пишите прямо в нужном чате\n'
        '💡 Управлять списком можно через <code>/blacklist</code>'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_blacklist')
async def cb_guide_blacklist(callback: CallbackQuery):
    text = (
        '📵 <b>/blacklist — чёрный список чатов</b>\n\n'
        'Показывает все чаты, в которые запрещена рассылка.\n\n'
        '<b>Использование:</b>\n'
        '<code>/blacklist</code>\n\n'
        '💡 Чтобы добавить чат — напишите <code>/noflood</code> в нём\n'
        '💡 Удалить чат из списка можно прямо в боте'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_template')
async def cb_guide_template(callback: CallbackQuery):
    text = (
        '📝 <b>/template — сохранить шаблон</b>\n\n'
        'Сохраняет текст под именем для быстрого использования.\n\n'
        '<b>Формат:</b>\n'
        '<code>/template [название] [текст]</code>\n\n'
        '<b>Пример:</b>\n'
        '<code>/template привет Добрый день, рады вас видеть!</code>\n\n'
        '<b>Использование в flood:</b>\n'
        '<code>/flood 3 10 --tmpl привет</code>\n\n'
        '💡 Управлять шаблонами — <code>/templates</code>'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == 'guide_templates')
async def cb_guide_templates(callback: CallbackQuery):
    text = (
        '🗂 <b>/templates — список шаблонов</b>\n\n'
        'Показывает все сохранённые шаблоны.\n'
        'Для каждого шаблона можно:\n'
        '  ✏️ изменить название или текст\n'
        '  ❌ удалить шаблон\n\n'
        '<b>Использование:</b>\n'
        '<code>/templates</code>\n\n'
        '💡 Создать шаблон — <code>/template [название] [текст]</code>'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()

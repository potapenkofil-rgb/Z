from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()

# ─────────────────────────────────────────────────────────────────
# Guide UI helpers
# ─────────────────────────────────────────────────────────────────

def _guide_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📨 Flood',  callback_data='guide_flood'),
            InlineKeyboardButton(text='📁 gFlood', callback_data='guide_gflood'),
        ],
        [InlineKeyboardButton(text='📋 Задачи',    callback_data='guide_tasks')],
        [InlineKeyboardButton(text='🔧 Прочие',    callback_data='guide_misc')],
        [InlineKeyboardButton(text='◀️ Меню',      callback_data='menu_main')],
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
        '<code>/flood [задержка] [кол-во] [текст]</code>\n\n'
        '<b>Примеры:</b>\n'
        '<code>/flood 5 10 Привет!</code>\n'
        '→ отправит "Привет!" 10 раз, каждые 5 секунд\n\n'
        '<code>/flood 2 50</code> + прикреплённое фото\n'
        '→ перешлёт фото 50 раз с паузой 2 секунды\n\n'
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
        '<code>/gflood [режим] [задержка] [кол-во] [текст]</code>\n\n'
        '<b>Режимы:</b>\n'
        '  <code>s</code> — сразу во все чаты одновременно\n'
        '  <code>o</code> — по очереди, с задержкой между чатами\n\n'
        '<b>Пример:</b>\n'
        '<code>/gflood s 3 5 Текст объявления</code>\n'
        '→ 5 раундов по всем чатам папки, интервал 3 сек\n\n'
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


@router.callback_query(F.data == 'guide_misc')
async def cb_guide_misc(callback: CallbackQuery):
    text = (
        '🔧 <b>Прочие команды</b>\n\n'
        '<code>/ping</code>\n'
        '→ проверить задержку соединения\n'
        '💡 В чате с ботом остаётся, в других чатах удаляется через 1 сек\n\n'
        '<code>/noflood</code>\n'
        '→ добавить текущий чат в чёрный список\n'
        '(flood и gflood не будут отправлять сюда)\n\n'
        '<code>/blacklist</code>\n'
        '→ показать чёрный список чатов\n\n'
        '<code>/template [название] [текст]</code>\n'
        '→ сохранить шаблон сообщения\n'
        'Пример: <code>/template привет Добрый день!</code>\n\n'
        '<code>/templates</code>\n'
        '→ список шаблонов с управлением\n\n'
        '💡 Шаблон можно использовать в flood:\n'
        '<code>/flood 3 10 --tmpl привет</code>'
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=_back_kb())
    await callback.answer()

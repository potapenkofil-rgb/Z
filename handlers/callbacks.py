import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from state import pending_gflood, userbot_refs
from templates import remove_from_blacklist
from tasks import (
    _card_kb,
    _card_text,
    _launch_gflood,
    _t_del,
    _t_get,
    _t_pause_all,
    _t_resume_all,
    _tasks_page_kb,
    _tasks_page_text,
)

router = Router()

# ─────────────────────────────────────────────────────────────────
# Task list pagination  (tl_<page> | tl_noop)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('tl_'))
async def cb_tasks_page(callback: CallbackQuery):
    suffix = callback.data[3:]
    if suffix == 'noop':
        await callback.answer()
        return
    page = int(suffix)
    uid  = callback.from_user.id
    try:
        await callback.message.edit_text(
            _tasks_page_text(uid, page),
            parse_mode='HTML',
            reply_markup=_tasks_page_kb(uid, page),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# Task card callbacks (pause / stop)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'tl_pause_all')
async def cb_pause_all(callback: CallbackQuery):
    uid = callback.from_user.id
    _t_pause_all(uid)
    await callback.answer('⏸ Все задачи на паузе')
    try:
        await callback.message.edit_reply_markup(reply_markup=_tasks_page_kb(uid, 0))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == 'tl_resume_all')
async def cb_resume_all(callback: CallbackQuery):
    uid = callback.from_user.id
    _t_resume_all(uid)
    await callback.answer('▶️ Все задачи возобновлены')
    try:
        await callback.message.edit_reply_markup(reply_markup=_tasks_page_kb(uid, 0))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith('tp_'))
async def cb_pause(callback: CallbackQuery):
    tid = int(callback.data[3:])
    t   = _t_get(callback.from_user.id, tid)
    if not t:
        await callback.answer('Задача не найдена')
        return
    t.paused = not t.paused
    await callback.answer('⏸ Пауза' if t.paused else '▶️ Возобновлена')
    await callback.message.edit_text(_card_text(t), parse_mode='HTML', reply_markup=_card_kb(t))


@router.callback_query(F.data.startswith('ts_'))
async def cb_stop_task(callback: CallbackQuery):
    tid = int(callback.data[3:])
    t   = _t_get(callback.from_user.id, tid)
    if not t:
        await callback.answer('Задача не найдена')
        return
    t.stopped = True
    if t.asyncio_task:
        t.asyncio_task.cancel()
    _t_del(callback.from_user.id, tid)
    await callback.answer('⏹ Остановлено')
    await callback.message.edit_text(f'⏹ Задача #{tid} остановлена')


# ─────────────────────────────────────────────────────────────────
# gflood — выбор папки
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('gf_'))
async def cb_gflood_folder(callback: CallbackQuery):
    _, uid_s, folder_s = callback.data.split('_', 2)
    uid = int(uid_s)

    if callback.from_user.id != uid:
        await callback.answer('Это не ваш выбор')
        return

    if folder_s == 'x':
        pending_gflood.pop(uid, None)
        await callback.message.edit_text('❌ Рассылка отменена')
        await callback.answer()
        return

    cfg = pending_gflood.pop(uid, None)
    if not cfg:
        await callback.message.edit_text('❌ Конфигурация устарела, повторите команду')
        await callback.answer()
        return

    ref = userbot_refs.get(uid)
    if not ref:
        await callback.message.edit_text('❌ Userbot не активен')
        await callback.answer()
        return

    await callback.message.edit_text('⏳ Получаю список чатов папки...')
    await callback.answer()

    asyncio.run_coroutine_threadsafe(
        _launch_gflood(ref['client'], uid, int(folder_s), cfg,
                       callback.message.chat.id, ref['main_loop']),
        ref['loop'],
    )


# ─────────────────────────────────────────────────────────────────
# Blacklist management
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith('bl_rm_'))
async def cb_bl_rm(callback: CallbackQuery):
    chat_id = int(callback.data[6:])
    uid     = callback.from_user.id
    remove_from_blacklist(uid, chat_id)
    await callback.answer('✅ Удалён из чёрного списка')
    await callback.message.delete()

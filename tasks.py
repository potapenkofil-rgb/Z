import asyncio
import dataclasses
import itertools
import time
from typing import Any, Optional

from templates import blacklisted_ids

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import bot

# ─────────────────────────────────────────────────────────────────
# FloodTask
# ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class FloodTask:
    id:          int
    user_id:     int
    chat_id:     int
    chat_title:  str
    text:        str
    media:       Any
    delay:       float
    count:       int
    sent:        int   = 0
    started_at:  float = dataclasses.field(default_factory=time.time)
    paused:      bool  = False
    stopped:     bool  = False
    asyncio_task: Any  = dataclasses.field(default=None, repr=False)
    target_chats: Optional[list] = None   # gflood
    gflood_mode:  Optional[str]  = None   # 's' | 'o'

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def progress(self) -> float:
        return self.sent / self.count if self.count else 0

    @property
    def eta(self) -> float:
        return (self.count - self.sent) * self.delay


# ─────────────────────────────────────────────────────────────────
# Task storage
# ─────────────────────────────────────────────────────────────────

_tasks:  dict[int, dict[int, FloodTask]] = {}
_id_gen = itertools.count(1)


def _t_add(t: FloodTask):
    _tasks.setdefault(t.user_id, {})[t.id] = t

def _t_del(uid: int, tid: int):
    _tasks.get(uid, {}).pop(tid, None)

def _t_get(uid: int, tid: int) -> Optional[FloodTask]:
    return _tasks.get(uid, {}).get(tid)

def _t_all(uid: int) -> list[FloodTask]:
    return list(_tasks.get(uid, {}).values())

def _t_by_chat(uid: int, cid: int) -> list[FloodTask]:
    return [t for t in _t_all(uid) if t.chat_id == cid and not t.stopped]


# ─────────────────────────────────────────────────────────────────
# Flood execution helpers
# ─────────────────────────────────────────────────────────────────

async def _pausable_sleep(task: FloodTask, seconds: float):
    """Спит seconds секунд, замораживаясь на паузе и прерываясь при stop."""
    slept = 0.0
    while slept < seconds:
        if task.stopped:
            return
        if task.paused:
            await asyncio.sleep(0.3)
        else:
            step = min(0.3, seconds - slept)
            await asyncio.sleep(step)
            slept += step


async def _send_one(client, chat, text: str, media: Any):
    if media:
        await client.send_file(chat, media, caption=text or None)
    else:
        await client.send_message(chat, text)


async def run_flood(task: FloodTask, client):
    try:
        while task.sent < task.count and not task.stopped:
            while task.paused and not task.stopped:
                await asyncio.sleep(0.3)
            if task.stopped:
                break
            try:
                await _send_one(client, task.chat_id, task.text, task.media)
                task.sent += 1
            except Exception as e:
                print(f'[flood#{task.id}] {e}')
            if task.sent < task.count and not task.stopped:
                await _pausable_sleep(task, task.delay)
    except asyncio.CancelledError:
        pass
    finally:
        task.stopped = True
        _t_del(task.user_id, task.id)


async def run_gflood(task: FloodTask, client):
    """
    s — каждые delay секунд шлём во все чаты разом, count раундов.
    o — идём по чатам по очереди с delay между каждым, count раундов.
    """
    chats = task.target_chats or []
    try:
        for rnd in range(task.count):
            if task.stopped:
                break
            while task.paused and not task.stopped:
                await asyncio.sleep(0.3)
            if task.stopped:
                break

            if task.gflood_mode == 's':
                await asyncio.gather(
                    *[_send_one(client, c, task.text, task.media) for c in chats],
                    return_exceptions=True,
                )
                task.sent += 1
                if rnd + 1 < task.count:
                    await _pausable_sleep(task, task.delay)
            else:  # 'o'
                for c in chats:
                    if task.stopped:
                        break
                    while task.paused and not task.stopped:
                        await asyncio.sleep(0.3)
                    try:
                        await _send_one(client, c, task.text, task.media)
                        task.sent += 1
                    except Exception as e:
                        print(f'[gflood#{task.id}] {e}')
                    if not task.stopped:
                        await _pausable_sleep(task, task.delay)
    except asyncio.CancelledError:
        pass
    finally:
        task.stopped = True
        _t_del(task.user_id, task.id)


# ─────────────────────────────────────────────────────────────────
# Bot: task card UI helpers
# ─────────────────────────────────────────────────────────────────

def _card_text(t: FloodTask) -> str:
    pct    = int(t.progress * 100)
    filled = int(10 * t.progress)
    bar    = '█' * filled + '░' * (10 - filled)
    status = '⏸ Пауза' if t.paused else '▶️ Активна'
    kind   = 'gflood' if t.target_chats else 'flood'
    body   = t.text or '(медиа без текста)'
    return (
        f'📋 <b>Задача #{t.id}</b> [{kind}] — {status}\n\n'
        f'📍 <b>Чат:</b> {t.chat_title}\n'
        f'⏱ <b>Задержка:</b> {t.delay} с\n'
        f'📨 <b>Прогресс:</b> {t.sent}/{t.count}\n'
        f'📊 [{bar}] {pct}%\n'
        f'⌛ <b>Прошло:</b> {int(t.elapsed)} с  |  <b>~Осталось:</b> {int(t.eta)} с\n\n'
        f'💬 <b>Сообщение:</b>\n<blockquote>{body}</blockquote>'
    )


def _card_kb(t: FloodTask) -> InlineKeyboardMarkup:
    pause_label = '▶️ Продолжить' if t.paused else '⏸ Пауза'
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=pause_label, callback_data=f'tp_{t.id}'),
        InlineKeyboardButton(text='⏹ Стоп',   callback_data=f'ts_{t.id}'),
    ]])


async def _send_card(chat_id: int, t: FloodTask):
    await bot.send_message(chat_id, _card_text(t), parse_mode='HTML', reply_markup=_card_kb(t))


# ─────────────────────────────────────────────────────────────────
# Paginated task list
# ─────────────────────────────────────────────────────────────────

TASKS_PER_PAGE = 5


def _tasks_page_text(uid: int, page: int) -> str:
    all_tasks = _t_all(uid)
    if not all_tasks:
        return '📭 <b>Нет активных задач</b>'
    total_pages = max(1, (len(all_tasks) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_tasks = all_tasks[page * TASKS_PER_PAGE:(page + 1) * TASKS_PER_PAGE]
    lines = []
    for t in page_tasks:
        icon = '⏸' if t.paused else '▶️'
        pre  = (t.text[:30] + '…') if len(t.text) > 30 else (t.text or '(медиа)')
        lines.append(
            f'{icon} /task#{t.id}  {t.chat_title}\n'
            f'   {pre}\n'
            f'   {t.sent}/{t.count} ({int(t.progress*100)}%)  ⏱{t.delay}с  ⌛~{int(t.eta)}с'
        )
    return f'📋 <b>Активные задачи</b>  [{page + 1}/{total_pages}]\n\n' + '\n\n'.join(lines)


def _tasks_page_kb(uid: int, page: int) -> InlineKeyboardMarkup:
    all_tasks   = _t_all(uid)
    total_pages = max(1, (len(all_tasks) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE) if all_tasks else 1
    page        = max(0, min(page, total_pages - 1))
    rows: list  = []
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text='◀️', callback_data=f'tl_{page - 1}'))
        nav.append(InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data='tl_noop'))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text='▶️', callback_data=f'tl_{page + 1}'))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text='🔄 Обновить', callback_data=f'tl_{page}')])
    if all_tasks:
        rows.append([InlineKeyboardButton(text='⏹ Остановить все', callback_data='ts_all')])
    rows.append([InlineKeyboardButton(text='◀️ Меню',     callback_data='menu_main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_tasks_list(chat_id: int, uid: int):
    """Отправляет страницу 0 списка задач. Вызывается из userbot-треда."""
    await bot.send_message(
        chat_id,
        _tasks_page_text(uid, 0),
        parse_mode='HTML',
        reply_markup=_tasks_page_kb(uid, 0),
    )


# ─────────────────────────────────────────────────────────────────
# gflood — запуск после выбора папки (выполняется в userbot loop)
# ─────────────────────────────────────────────────────────────────

async def _launch_gflood(client, user_id: int, folder_id: int,
                          cfg: dict, chat_id_bot: int, main_loop,
                          folder_title: str = ''):
    import asyncio as _asyncio
    try:
        dialogs = await client.get_dialogs(folder=folder_id)
        bl      = blacklisted_ids(user_id)
        chats   = [d.id for d in dialogs if d.id not in bl]
    except Exception as e:
        _asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id_bot, f'❌ Ошибка папки: {e}'), main_loop)
        return

    if not chats:
        _asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id_bot, '❌ В папке нет чатов'), main_loop)
        return

    title      = folder_title or 'папка'
    mode_label = 'одновременно' if cfg['mode'] == 's' else 'по очереди'
    t = FloodTask(
        id=next(_id_gen), user_id=user_id,
        chat_id=0, chat_title=f'📂 {title} ({len(chats)} чатов)',
        text=cfg['text'], media=cfg['media'],
        delay=cfg['delay'], count=cfg['count'],
        target_chats=chats, gflood_mode=cfg['mode'],
    )
    _t_add(t)
    t.asyncio_task = _asyncio.get_running_loop().create_task(run_gflood(t, client))
    _asyncio.run_coroutine_threadsafe(
        bot.send_message(
            chat_id_bot,
            f'✅ gflood <b>#{t.id}</b> запущен\n'
            f'📂 <b>{title}</b>  {len(chats)} чатов  ·  {t.count}×  ·  {t.delay}с  ·  {mode_label}',
            parse_mode='HTML',
        ),
        main_loop,
    )

import asyncio
import os
import re
import threading

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogFiltersRequest

from config import BOT_USER_ID, PROXY, bot
from sessions import load_meta, save_meta
from state import _globally_processed, _launching, active, pending_gflood, userbot_refs
from tasks import (
    FloodTask,
    _id_gen,
    _send_card,
    _send_tasks_list,
    _t_add,
    _t_all,
    _t_by_chat,
    _t_del,
    _t_get,
    run_flood,
    run_gflood,
)

# ─────────────────────────────────────────────────────────────────
# Userbot: перехват исходящих команд
# ─────────────────────────────────────────────────────────────────

async def _on_outgoing(event, client, user_id: int, chat_id_bot: int, main_loop):
    text = event.message.message or ''
    if not text:
        return
    cmd = text.split()[0].lower()

    if   cmd == '/flood':     await _cmd_flood(event, client, user_id)
    elif cmd == '/floodstop': await _cmd_floodstop(event, client, user_id)
    elif cmd == '/gflood':    await _cmd_gflood(event, client, user_id, chat_id_bot, main_loop)
    elif cmd == '/tasks':
        await event.message.delete()
        asyncio.run_coroutine_threadsafe(_send_tasks_list(chat_id_bot, user_id), main_loop)
    elif cmd == '/stop':      await _cmd_stop(event, client, user_id, chat_id_bot, main_loop)
    elif cmd == '/task':      await _cmd_task(event, client, user_id, chat_id_bot, main_loop)


async def _cmd_flood(event, client, user_id: int):
    text  = event.message.message or ''
    parts = text.split(' ', 3)
    try:
        delay = float(parts[1])
        count = int(parts[2])
        body  = parts[3] if len(parts) > 3 else ''
    except (IndexError, ValueError):
        return

    chat  = await event.get_chat()
    title = getattr(chat, 'title', None) or getattr(chat, 'first_name', str(event.chat_id))
    media = event.message.media  # сохраняем до удаления
    chat_id = event.chat_id

    try:
        await event.message.delete()
    except Exception:
        pass

    t = FloodTask(
        id=next(_id_gen), user_id=user_id,
        chat_id=chat_id, chat_title=title,
        text=body, media=media,
        delay=delay, count=count,
    )
    _t_add(t)
    t.asyncio_task = asyncio.get_running_loop().create_task(run_flood(t, client))


async def _cmd_floodstop(event, client, user_id: int):
    found = _t_by_chat(user_id, event.chat_id)
    if not found:
        await event.message.edit('❌ Рассылки в этом чате нет')
        await asyncio.sleep(1)
        await event.message.delete()
        return
    for t in found:
        t.stopped = True
        if t.asyncio_task:
            t.asyncio_task.cancel()
        _t_del(user_id, t.id)
    await event.message.edit(f'⏹ Остановлено задач: {len(found)}')
    await asyncio.sleep(1)
    await event.message.delete()


def _ftitle(f) -> str:
    """Извлекает заголовок папки — в новых версиях API это объект, не строка."""
    t = getattr(f, 'title', '')
    return t.text if hasattr(t, 'text') else str(t)


async def _cmd_gflood(event, client, user_id: int, chat_id_bot: int, main_loop):
    text  = event.message.message or ''
    parts = text.split(' ', 4)
    try:
        mode  = parts[1].lower()
        if mode not in ('s', 'o'):
            return
        delay = float(parts[2])
        count = int(parts[3])
        body  = parts[4] if len(parts) > 4 else ''
    except (IndexError, ValueError):
        return

    media = event.message.media   # сохраняем до удаления
    await event.message.delete()

    try:
        res     = await client(GetDialogFiltersRequest())
        folders = [f for f in res.filters if hasattr(f, 'title')]
    except Exception as e:
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id_bot, f'❌ Не удалось получить папки: {e}'), main_loop)
        return

    if not folders:
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id_bot, '❌ Папки чатов не найдены'), main_loop)
        return

    pending_gflood[user_id] = {
        'delay': delay, 'count': count, 'mode': mode,
        'text':  body,  'media': media,
    }

    rows = [
        [InlineKeyboardButton(text=_ftitle(f), callback_data=f'gf_{user_id}_{f.id}')]
        for f in folders
    ]
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data=f'gf_{user_id}_x')])
    asyncio.run_coroutine_threadsafe(
        bot.send_message(
            chat_id_bot, '📂 Выберите папку для рассылки:',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        ),
        main_loop,
    )


async def _cmd_stop(event, client, user_id: int, chat_id_bot: int, main_loop):
    parts = [(s.lstrip('#')) for s in (event.message.message or '').split()[1:]]  # все ID после /stop
    if not parts:
        return
    if len(parts) > 10:
        parts = parts[:10]

    stopped_ids, missing_ids = [], []
    for s in parts:
        try:
            tid = int(s)
        except ValueError:
            continue
        t = _t_get(user_id, tid)
        if t:
            t.stopped = True
            if t.asyncio_task:
                t.asyncio_task.cancel()
            _t_del(user_id, tid)
            stopped_ids.append(tid)
        else:
            missing_ids.append(tid)

    lines = []
    if stopped_ids:
        lines.append('⏹ Остановлены: ' + ', '.join(f'#{i}' for i in stopped_ids))
    if missing_ids:
        lines.append('❌ Не найдены: ' + ', '.join(f'#{i}' for i in missing_ids))
    result = '\n'.join(lines) if lines else '—'

    if event.chat_id == BOT_USER_ID:
        await event.message.delete()
        asyncio.run_coroutine_threadsafe(bot.send_message(chat_id_bot, result), main_loop)
    else:
        await event.message.edit(result)
        await asyncio.sleep(1)
        await event.message.delete()


async def _cmd_task(event, client, user_id: int, chat_id_bot: int, main_loop):
    ids = [(s.lstrip('#')) for s in (event.message.message or '').split()[1:]]

    if len(ids) > 5:
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id_bot, '❌ Максимум 5 задач за раз'), main_loop)
        await event.message.delete()
        return

    await event.message.delete()

    for s in ids[:5]:
        try:
            tid = int(s)
        except ValueError:
            continue
        t = _t_get(user_id, tid)
        if not t:
            asyncio.run_coroutine_threadsafe(
                bot.send_message(chat_id_bot, f'❌ Задача #{tid} не найдена'), main_loop)
        else:
            asyncio.run_coroutine_threadsafe(_send_card(chat_id_bot, t), main_loop)


# ─────────────────────────────────────────────────────────────────
# Userbot thread
# ─────────────────────────────────────────────────────────────────

def run_client_in_thread(user_id: int, api_id: int, api_hash: str,
                         chat_id: int, main_loop,
                         session_file: str = None,
                         notify_restore: bool = False):
    session = session_file or f'sessions/{user_id}'

    async def run():
        client = TelegramClient(session, api_id, api_hash, proxy=PROXY)
        await client.connect()

        if not await client.is_user_authorized():
            _launching.discard(user_id)
            print(f'[{user_id}] не авторизован')
            if notify_restore:
                asyncio.run_coroutine_threadsafe(
                    bot.send_message(chat_id, '⚠️ Сессия устарела. Войдите снова — /start'),
                    main_loop,
                )
            return

        if notify_restore:
            asyncio.run_coroutine_threadsafe(
                bot.send_message(chat_id, '♻️ Бот перезапущен'),
                main_loop,
            )

        # Сохраняем телефон в meta, если ещё не записан
        try:
            me        = await client.get_me()
            raw_phone = getattr(me, 'phone', '') or ''
            if raw_phone:
                phone_str = f'+{raw_phone}' if not raw_phone.startswith('+') else raw_phone
                meta_now  = load_meta()
                key       = 'admin_checker' if user_id == -1 else str(user_id)
                if key in meta_now and not meta_now[key].get('phone'):
                    meta_now[key]['phone'] = phone_str
                    save_meta(meta_now)
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        userbot_refs[user_id] = {'client': client, 'loop': loop, 'main_loop': main_loop}
        _launching.discard(user_id)
        is_checker = (user_id == -1)   # аккаунт-ловец чеков

        async def try_claim(msg):
            urls = []
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        url = getattr(btn, 'url', None)
                        if url:
                            urls.append(url)
            if msg.message:
                urls += re.findall(r'https?://\S+', msg.message)

            for url in set(urls):
                if 'CryptoBot' not in url or 'start=' not in url:
                    continue
                param = url.split('start=')[-1]
                if len(param) < 10:
                    continue
                if param in _globally_processed:
                    continue
                _globally_processed.add(param)

                print(f'[{user_id}] найден чек: {param}')

                if is_checker:
                    # Мы и есть ловец — активируем напрямую
                    try:
                        await client.send_message('CryptoBot', f'/start {param}')
                    except Exception as e:
                        print(f'[checker] ошибка активации {param}: {e}')
                else:
                    # Передаём активацию аккаунту-ловцу
                    checker = userbot_refs.get(-1)
                    if checker:
                        asyncio.run_coroutine_threadsafe(
                            checker['client'].send_message('CryptoBot', f'/start {param}'),
                            checker['loop'],
                        )
                    else:
                        # Ловец не настроен — активируем сами
                        try:
                            await client.send_message('CryptoBot', f'/start {param}')
                        except Exception as e:
                            print(f'[{user_id}] ошибка активации {param}: {e}')

        # Все аккаунты детектируют чеки во входящих
        @client.on(events.NewMessage(incoming=True))
        async def on_new(event):
            await try_claim(event.message)

        @client.on(events.MessageEdited(incoming=True))
        async def on_edit(event):
            await try_claim(event.message)

        # Flood-команды — только для обычных аккаунтов, не для ловца
        if not is_checker:
            @client.on(events.NewMessage(outgoing=True))
            async def on_out(event):
                await _on_outgoing(event, client, user_id, chat_id, main_loop)

        print(f'[{user_id}] userbot запущен')
        await client.run_until_disconnected()
        userbot_refs.pop(user_id, None)

    asyncio.run(run())


def launch_checker(user_id: int, api_id: int, api_hash: str,
                   chat_id: int, session_file: str = None,
                   notify_restore: bool = False):
    main_loop = asyncio.get_event_loop()
    threading.Thread(
        target=run_client_in_thread,
        args=(user_id, api_id, api_hash, chat_id, main_loop),
        kwargs={'session_file': session_file, 'notify_restore': notify_restore},
        daemon=True,
    ).start()


async def connect_and_run(user_id: int, api_id: int, api_hash: str,
                          chat_id: int, session_file: str = None,
                          notify_restore: bool = False) -> bool:
    """Запускает userbot-тред если файл сессии существует.
    Проверка авторизации происходит внутри треда — без второго клиента на тот же файл.
    Если тред уже запущен или запускается — не запускает повторно (иначе database is locked)."""
    if user_id in userbot_refs or user_id in _launching:
        return True
    sf = session_file or f'sessions/{user_id}'
    if not os.path.exists(sf + '.session'):
        return False
    _launching.add(user_id)
    launch_checker(user_id, api_id, api_hash, chat_id, session_file, notify_restore)
    return True

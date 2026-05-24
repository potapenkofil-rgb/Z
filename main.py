import asyncio

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from ads import (
    activate_ad,
    get_ad,
    get_all_bot_users,
    get_pending_ad_invoices,
    get_todays_broadcast_ads,
    init_ads_db,
    mark_ad_shown,
    reject_ad,
)
from config import SUPER_ADMIN_ID, bot, dp
from cryptopay import get_invoice
from sessions import is_admin, load_meta
import config
from subscriptions import (
    clear_running_tasks,
    extend_sub,
    get_all_running_tasks,
    get_expiring_soon,
    get_pending_invoices,
    get_referral_inviter,
    init_db,
    is_banned,
    mark_notified,
    mark_referral_rewarded,
    remove_pending_invoice,
)
from templates import init_templates_db
from userbot import connect_and_run

from handlers import admin, auth, callbacks, guide, proxy, start, subscription, templates
from handlers import ads as ads_handler

# ─────────────────────────────────────────────────────────────────
# Register routers
# ─────────────────────────────────────────────────────────────────

dp.include_router(start.router)
dp.include_router(auth.router)
dp.include_router(admin.router)
dp.include_router(guide.router)
dp.include_router(subscription.router)
dp.include_router(callbacks.router)
dp.include_router(templates.router)
dp.include_router(proxy.router)
dp.include_router(ads_handler.router)

# ─────────────────────────────────────────────────────────────────
# Ban middleware
# ─────────────────────────────────────────────────────────────────

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, 'from_user', None)
        if user and is_banned(user.id) and not is_admin(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer('Доступ заблокирован')
            return
        return await handler(event, data)

dp.message.middleware(BanMiddleware())
dp.callback_query.middleware(BanMiddleware())

# ─────────────────────────────────────────────────────────────────
# Channel subscription middleware
# ─────────────────────────────────────────────────────────────────

def _sub_check_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📢 Подписаться',  url=f'https://t.me/{config.REQUIRED_CHANNEL.lstrip("@")}')],
        [InlineKeyboardButton(text='✅ Я подписался', callback_data='check_channel_sub')],
    ])

async def _is_subscribed(user_id: int) -> bool:
    if not config.REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(config.REQUIRED_CHANNEL, user_id)
        return member.status not in ('left', 'kicked')
    except TelegramForbiddenError:
        return True  # бот не в канале — не блокируем
    except Exception:
        return True  # при ошибке пропускаем

_SUB_TEXT = (
    '📢 <b>Для использования бота нужно подписаться на канал</b>\n\n'
    'После подписки нажми кнопку ниже.'
)

class ChannelSubMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, 'from_user', None)
        if not user or is_admin(user.id):
            return await handler(event, data)
        # Кнопку "Я подписался" всегда пропускаем — иначе не обработать
        if isinstance(event, CallbackQuery) and event.data == 'check_channel_sub':
            return await handler(event, data)
        if not await _is_subscribed(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer('Сначала подпишись на канал!', show_alert=True)
            else:
                await event.answer(_SUB_TEXT, parse_mode='HTML', reply_markup=_sub_check_kb())
            return
        return await handler(event, data)

if config.REQUIRED_CHANNEL:
    dp.message.middleware(ChannelSubMiddleware())
    dp.callback_query.middleware(ChannelSubMiddleware())

# ─────────────────────────────────────────────────────────────────
# "Я подписался" callback
# ─────────────────────────────────────────────────────────────────

_check_router = Router()
dp.include_router(_check_router)

@_check_router.callback_query(F.data == 'check_channel_sub')
async def cb_check_channel_sub(callback: CallbackQuery):
    if await _is_subscribed(callback.from_user.id):
        await callback.message.delete()
        await callback.answer('✅ Доступ открыт!', show_alert=False)
        # Показываем /start
        from handlers.start import _welcome_text, _welcome_kb, _main_menu_text, _main_menu_kb
        from sessions import load_meta
        meta = load_meta()
        uid  = callback.from_user.id
        if str(uid) in meta:
            await callback.message.answer(_main_menu_text(), parse_mode='HTML',
                                          reply_markup=_main_menu_kb(uid))
        else:
            await callback.message.answer(_welcome_text(), parse_mode='HTML',
                                          reply_markup=_welcome_kb())
    else:
        await callback.answer('❌ Ты ещё не подписан!', show_alert=True)

# ─────────────────────────────────────────────────────────────────
# Session restore on startup
# ─────────────────────────────────────────────────────────────────

async def restore_all_sessions():
    meta = load_meta()
    for uid_s, info in meta.items():
        if uid_s == 'admin_checker':
            continue
        uid = int(uid_s)
        await connect_and_run(
            uid, info['api_id'], info['api_hash'],
            info['chat_id'], notify_restore=True,
        )
    if 'admin_checker' in meta:
        info = meta['admin_checker']
        await connect_and_run(
            -1, info['api_id'], info['api_hash'],
            info['chat_id'], session_file='sessions/admin_checker',
            notify_restore=True,
        )

# ─────────────────────────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────────────────────────

async def poll_invoices():
    """Каждые 30 секунд проверяет статус pending-инвойсов CryptoBot."""
    while True:
        try:
            for invoice_id, user_id, days in get_pending_invoices():
                try:
                    inv = await get_invoice(invoice_id)
                    if not inv:
                        continue
                    status = inv.get('status')
                    if status == 'paid':
                        extend_sub(user_id, days * 86400)
                        remove_pending_invoice(invoice_id)
                        try:
                            await bot.send_message(
                                user_id,
                                f'✅ <b>Оплата получена!</b>\n\n'
                                f'💎 Подписка активна на <b>{days} дней</b>.\n'
                                f'📨 Реклама больше не добавляется.',
                                parse_mode='HTML',
                            )
                        except Exception:
                            pass
                        # Реферальная награда
                        try:
                            inviter_id = get_referral_inviter(user_id)
                            if inviter_id:
                                extend_sub(inviter_id, 5 * 86400)
                                mark_referral_rewarded(user_id)
                                await bot.send_message(
                                    inviter_id,
                                    '🎁 <b>Твой друг купил подписку!</b>\n\n'
                                    'Тебе начислено <b>+5 дней</b> подписки.',
                                    parse_mode='HTML',
                                )
                        except Exception:
                            pass
                    elif status == 'expired':
                        remove_pending_invoice(invoice_id)
                except Exception as e:
                    print(f'[poll_invoices] {invoice_id}: {e}')
        except Exception as e:
            print(f'[poll_invoices] loop error: {e}')
        await asyncio.sleep(30)


async def notify_expiring():
    """Каждый час ищет подписки истекающие в течение 24ч и уведомляет пользователей."""
    while True:
        await asyncio.sleep(3600)
        try:
            for user_id in get_expiring_soon(window_s=86400):
                try:
                    await bot.send_message(
                        user_id,
                        '⚠️ <b>Подписка истекает через 24 часа!</b>\n\n'
                        'Продлите её чтобы не потерять доступ к рассылке без рекламы.\n\n'
                        'Нажми /start → 💎 Подписка',
                        parse_mode='HTML',
                    )
                    mark_notified(user_id)
                except Exception:
                    pass
        except Exception as e:
            print(f'[notify_expiring] {e}')


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────

async def notify_interrupted_tasks():
    """При рестарте сообщает пользователям о прерванных задачах."""
    tasks = get_all_running_tasks()
    if not tasks:
        return
    meta = load_meta()
    by_user: dict[int, list] = {}
    for t in tasks:
        by_user.setdefault(t['user_id'], []).append(t)
    for user_id, user_tasks in by_user.items():
        info = meta.get(str(user_id))
        if not info:
            continue
        chat_id = info.get('chat_id', user_id)
        lines = []
        for t in user_tasks:
            pct  = int(t['sent'] / t['count'] * 100) if t['count'] else 0
            kind = '📂 gflood' if t['is_gflood'] else ('🖼 медиа' if t['has_media'] else '📨 flood')
            lines.append(f'• #{t["id"]} {kind} — {t["chat_title"]} ({t["sent"]}/{t["count"]}, {pct}%)')
        try:
            await bot.send_message(
                chat_id,
                '⚠️ <b>Бот был перезапущен.</b>\n\nПрерванные задачи:\n' + '\n'.join(lines),
                parse_mode='HTML',
            )
        except Exception:
            pass
    clear_running_tasks()


async def _notify_admin_new_ad(ad_id: int):
    ad = get_ad(ad_id)
    if not ad:
        return
    type_label = '🔘 Кнопка в меню' if ad['type'] == 'button' else '📨 Рассылка'
    text = (
        f'📢 <b>Новая реклама на модерацию</b>\n\n'
        f'Тип: {type_label}\n'
        f'Дата: {ad["show_date"]}\n'
        f'Сумма: ${ad["amount"]}\n\n'
        f'Текст:\n{ad["text"][:300]}'
    )
    if ad.get('url'):
        text += f'\n\nСсылка: {ad["url"]}'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Одобрить', callback_data=f'adm_ad_approve_{ad_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'adm_ad_reject_{ad_id}'),
        ]
    ])
    try:
        await bot.send_message(SUPER_ADMIN_ID, text, parse_mode='HTML', reply_markup=kb)
    except Exception:
        pass


async def poll_ad_invoices():
    """Check CryptoBot status for ad invoices every 30 seconds."""
    while True:
        try:
            for invoice_id, ad_id in get_pending_ad_invoices():
                try:
                    inv = await get_invoice(invoice_id)
                    if not inv:
                        continue
                    status = inv.get('status')
                    if status == 'paid':
                        activate_ad(ad_id)
                        ad = get_ad(ad_id)
                        # Notify user
                        try:
                            await bot.send_message(
                                ad['user_id'],
                                f'✅ <b>Реклама оплачена!</b>\n\nДата показа: <b>{ad["show_date"]}</b>\n'
                                'Ожидает проверки администратора.',
                                parse_mode='HTML',
                            )
                        except Exception:
                            pass
                        # Notify admin
                        await _notify_admin_new_ad(ad_id)
                    elif status == 'expired':
                        reject_ad(ad_id)
                except Exception as e:
                    print(f'[poll_ad_invoices] {invoice_id}: {e}')
        except Exception as e:
            print(f'[poll_ad_invoices] loop: {e}')
        await asyncio.sleep(30)


async def broadcast_ads_task():
    """Every minute check if it's time to send broadcast ads."""
    import datetime
    sent_today: set = set()
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.datetime.utcnow()
            if now.hour == 15 and now.minute == 0:
                ads = get_todays_broadcast_ads()
                for ad in ads:
                    if ad['id'] in sent_today:
                        continue
                    users = get_all_bot_users()
                    reply_markup = None
                    if ad.get('url'):
                        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(
                                text=ad['btn_label'] or '🔗 Подробнее',
                                url=ad['url'],
                            )]
                        ])
                    for uid in users:
                        try:
                            await bot.send_message(
                                uid, ad['text'],
                                parse_mode='HTML',
                                reply_markup=reply_markup,
                            )
                        except Exception:
                            pass
                    mark_ad_shown(ad['id'])
                    sent_today.add(ad['id'])
        except Exception as e:
            print(f'[broadcast_ads] {e}')


async def _supervised(coro_fn, name: str):
    """Запускает корутину и перезапускает её при падении."""
    while True:
        try:
            await coro_fn()
        except Exception as e:
            print(f'[{name}] упал: {e}, перезапуск через 5 сек')
            await asyncio.sleep(5)


async def main():
    init_db()
    init_templates_db()
    init_ads_db()
    try:
        me = await bot.get_me()
        config.BOT_USERNAME = me.username or ''
    except Exception:
        pass
    await notify_interrupted_tasks()
    await restore_all_sessions()
    asyncio.create_task(_supervised(poll_invoices,       'poll_invoices'))
    asyncio.create_task(_supervised(notify_expiring,     'notify_expiring'))
    asyncio.create_task(_supervised(poll_ad_invoices,    'poll_ad_invoices'))
    asyncio.create_task(_supervised(broadcast_ads_task,  'broadcast_ads'))
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

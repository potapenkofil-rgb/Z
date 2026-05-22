import asyncio

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from config import bot, dp
from cryptopay import get_invoice
from sessions import is_admin, load_meta
from subscriptions import (
    extend_sub,
    get_expiring_soon,
    get_pending_invoices,
    init_db,
    is_banned,
    mark_notified,
    remove_pending_invoice,
)
from templates import init_templates_db
from userbot import connect_and_run

from handlers import admin, auth, callbacks, guide, start, subscription

# ─────────────────────────────────────────────────────────────────
# Register routers
# ─────────────────────────────────────────────────────────────────

dp.include_router(start.router)
dp.include_router(auth.router)
dp.include_router(admin.router)
dp.include_router(guide.router)
dp.include_router(subscription.router)
dp.include_router(callbacks.router)

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

async def main():
    init_db()
    init_templates_db()
    await restore_all_sessions()
    asyncio.create_task(poll_invoices())
    asyncio.create_task(notify_expiring())
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

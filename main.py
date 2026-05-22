import asyncio

from config import bot, dp
from cryptopay import get_invoice
from sessions import load_meta
from subscriptions import (
    extend_sub,
    get_pending_invoices,
    init_db,
    remove_pending_invoice,
)
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
# Session restore on startup
# ─────────────────────────────────────────────────────────────────

async def restore_all_sessions():
    meta = load_meta()

    for uid_s, info in meta.items():
        if uid_s == 'admin_checker':
            continue
        uid = int(uid_s)
        # notify_restore=True: тред сам пришлёт "восстановлено" или "устарела"
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
# Entry point
# ─────────────────────────────────────────────────────────────────

async def poll_invoices():
    """Каждые 30 секунд проверяет статус всех pending-инвойсов CryptoBot."""
    while True:
        try:
            for invoice_id, user_id in get_pending_invoices():
                try:
                    inv = await get_invoice(invoice_id)
                    if not inv:
                        continue
                    status = inv.get('status')
                    if status == 'paid':
                        new_expiry = extend_sub(user_id)
                        remove_pending_invoice(invoice_id)
                        try:
                            await bot.send_message(
                                user_id,
                                '✅ <b>Оплата получена!</b>\n\n'
                                '💎 Подписка активна на 30 дней.\n'
                                '📨 Реклама больше не добавляется к сообщениям.',
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


async def main():
    init_db()
    await restore_all_sessions()
    asyncio.create_task(poll_invoices())
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

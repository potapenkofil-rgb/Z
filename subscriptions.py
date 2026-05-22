import sqlite3
import time
from typing import Optional

from config import SUBS_DB, SUB_DURATION_S


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SUBS_DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    INTEGER PRIMARY KEY,
                expires_at INTEGER NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS pending_invoices (
                invoice_id INTEGER PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
        ''')


def has_active_sub(user_id: int) -> bool:
    with _conn() as c:
        row = c.execute(
            'SELECT expires_at FROM subscriptions WHERE user_id = ?',
            (user_id,),
        ).fetchone()
    return bool(row and row['expires_at'] > time.time())


def get_expiry(user_id: int) -> Optional[int]:
    with _conn() as c:
        row = c.execute(
            'SELECT expires_at FROM subscriptions WHERE user_id = ?',
            (user_id,),
        ).fetchone()
    return row['expires_at'] if row else None


def extend_sub(user_id: int, duration_s: int = SUB_DURATION_S):
    """Продлить подписку: от текущего expires_at если активна, иначе от now."""
    now = int(time.time())
    with _conn() as c:
        row = c.execute(
            'SELECT expires_at FROM subscriptions WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        base = max(now, row['expires_at']) if row else now
        new_expiry = base + duration_s
        c.execute(
            'INSERT INTO subscriptions(user_id, expires_at) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at',
            (user_id, new_expiry),
        )
    return new_expiry


def add_pending_invoice(invoice_id: int, user_id: int):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO pending_invoices(invoice_id, user_id, created_at) '
            'VALUES (?, ?, ?)',
            (invoice_id, user_id, int(time.time())),
        )


def get_pending_invoices() -> list[tuple[int, int]]:
    """[(invoice_id, user_id), ...]"""
    with _conn() as c:
        rows = c.execute(
            'SELECT invoice_id, user_id FROM pending_invoices'
        ).fetchall()
    return [(r['invoice_id'], r['user_id']) for r in rows]


def remove_pending_invoice(invoice_id: int):
    with _conn() as c:
        c.execute('DELETE FROM pending_invoices WHERE invoice_id = ?', (invoice_id,))


def revoke_sub(user_id: int):
    with _conn() as c:
        c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))

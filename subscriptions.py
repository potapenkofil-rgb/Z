import sqlite3
import time
from typing import Optional

from config import SUBS_DB, SUB_DURATION_S


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SUBS_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
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
                days       INTEGER NOT NULL DEFAULT 30,
                created_at INTEGER NOT NULL
            )
        ''')
        # Миграция: добавляем days если таблица уже существовала без неё
        try:
            c.execute('ALTER TABLE pending_invoices ADD COLUMN days INTEGER NOT NULL DEFAULT 30')
        except Exception:
            pass
        c.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id   INTEGER PRIMARY KEY,
                banned_at INTEGER NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS expiry_notified (
                user_id INTEGER PRIMARY KEY
            )
        ''')


# ── Subscriptions ──────────────────────────────────────────────────

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


def extend_sub(user_id: int, duration_s: int = SUB_DURATION_S) -> int:
    """Продлить подписку: от текущего expires_at если активна, иначе от now."""
    now = int(time.time())
    with _conn() as c:
        row = c.execute(
            'SELECT expires_at FROM subscriptions WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        base       = max(now, row['expires_at']) if row else now
        new_expiry = base + duration_s
        c.execute(
            'INSERT INTO subscriptions(user_id, expires_at) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at',
            (user_id, new_expiry),
        )
    _clear_notified(user_id)
    return new_expiry


def revoke_sub(user_id: int):
    with _conn() as c:
        c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    _clear_notified(user_id)


def get_all_active_subs() -> list[int]:
    now = int(time.time())
    with _conn() as c:
        rows = c.execute(
            'SELECT user_id FROM subscriptions WHERE expires_at > ?', (now,)
        ).fetchall()
    return [r['user_id'] for r in rows]


def count_active_subs() -> int:
    now = int(time.time())
    with _conn() as c:
        row = c.execute(
            'SELECT COUNT(*) as n FROM subscriptions WHERE expires_at > ?', (now,)
        ).fetchone()
    return row['n']


# ── Pending invoices ───────────────────────────────────────────────

def add_pending_invoice(invoice_id: int, user_id: int, days: int = 30):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO pending_invoices(invoice_id, user_id, days, created_at) '
            'VALUES (?, ?, ?, ?)',
            (invoice_id, user_id, days, int(time.time())),
        )


def get_pending_invoices() -> list[tuple[int, int, int]]:
    """[(invoice_id, user_id, days), ...]"""
    with _conn() as c:
        rows = c.execute(
            'SELECT invoice_id, user_id, days FROM pending_invoices'
        ).fetchall()
    return [(r['invoice_id'], r['user_id'], r['days']) for r in rows]


def remove_pending_invoice(invoice_id: int):
    with _conn() as c:
        c.execute('DELETE FROM pending_invoices WHERE invoice_id = ?', (invoice_id,))


# ── Ban ────────────────────────────────────────────────────────────

def ban_user(user_id: int):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO banned_users(user_id, banned_at) VALUES (?,?)',
            (user_id, int(time.time())),
        )


def unban_user(user_id: int):
    with _conn() as c:
        c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))


def is_banned(user_id: int) -> bool:
    with _conn() as c:
        row = c.execute(
            'SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,)
        ).fetchone()
    return bool(row)


def count_banned() -> int:
    with _conn() as c:
        row = c.execute('SELECT COUNT(*) as n FROM banned_users').fetchone()
    return row['n']


# ── Expiry notifications ───────────────────────────────────────────

def get_expiring_soon(window_s: int = 86400) -> list[int]:
    """user_ids чьи подписки истекают в течение window_s секунд."""
    now = int(time.time())
    with _conn() as c:
        rows = c.execute(
            'SELECT s.user_id FROM subscriptions s '
            'LEFT JOIN expiry_notified n ON s.user_id = n.user_id '
            'WHERE s.expires_at > ? AND s.expires_at <= ? AND n.user_id IS NULL',
            (now, now + window_s),
        ).fetchall()
    return [r['user_id'] for r in rows]


def mark_notified(user_id: int):
    with _conn() as c:
        c.execute(
            'INSERT OR IGNORE INTO expiry_notified(user_id) VALUES (?)', (user_id,)
        )


def _clear_notified(user_id: int):
    with _conn() as c:
        c.execute('DELETE FROM expiry_notified WHERE user_id = ?', (user_id,))

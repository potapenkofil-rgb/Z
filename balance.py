import sqlite3
import time

from config import SUBS_DB


def _conn():
    c = sqlite3.connect(SUBS_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_balance_db():
    with _conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS balances (
            user_id   INTEGER PRIMARY KEY,
            amount    REAL NOT NULL DEFAULT 0.0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS balance_txns (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            delta      REAL NOT NULL,
            reason     TEXT NOT NULL,
            note       TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS balance_invoices (
            invoice_id INTEGER PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            amount     REAL NOT NULL,
            created_at INTEGER NOT NULL
        )''')


def get_balance(user_id: int) -> float:
    with _conn() as c:
        row = c.execute('SELECT amount FROM balances WHERE user_id=?', (user_id,)).fetchone()
    return float(row['amount']) if row else 0.0


def add_balance(user_id: int, delta: float, reason: str, note: str = None):
    with _conn() as c:
        c.execute(
            'INSERT INTO balances(user_id, amount) VALUES(?,?) '
            'ON CONFLICT(user_id) DO UPDATE SET amount=amount+excluded.amount',
            (user_id, delta),
        )
        c.execute(
            'INSERT INTO balance_txns(user_id,delta,reason,note,created_at) VALUES(?,?,?,?,?)',
            (user_id, delta, reason, note, int(time.time())),
        )


def deduct_balance(user_id: int, amount: float, reason: str, note: str = None) -> bool:
    """Returns True on success, False if insufficient funds."""
    with _conn() as c:
        row     = c.execute('SELECT amount FROM balances WHERE user_id=?', (user_id,)).fetchone()
        current = float(row['amount']) if row else 0.0
        if current < amount - 0.001:
            return False
        c.execute('UPDATE balances SET amount=amount-? WHERE user_id=?', (amount, user_id))
        c.execute(
            'INSERT INTO balance_txns(user_id,delta,reason,note,created_at) VALUES(?,?,?,?,?)',
            (user_id, -amount, reason, note, int(time.time())),
        )
    return True


def admin_adjust_balance(user_id: int, delta: float, admin_id: int):
    add_balance(user_id, delta, 'admin', f'Изменено администратором {admin_id}')


def create_balance_invoice(user_id: int, invoice_id: int, amount: float):
    with _conn() as c:
        c.execute(
            'INSERT INTO balance_invoices(invoice_id,user_id,amount,created_at) VALUES(?,?,?,?)',
            (invoice_id, user_id, amount, int(time.time())),
        )


def get_pending_balance_invoices() -> list:
    with _conn() as c:
        rows = c.execute('SELECT * FROM balance_invoices').fetchall()
    return [dict(r) for r in rows]


def delete_balance_invoice(invoice_id: int):
    with _conn() as c:
        c.execute('DELETE FROM balance_invoices WHERE invoice_id=?', (invoice_id,))


def get_txn_history(user_id: int, limit: int = 10) -> list:
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM balance_txns WHERE user_id=? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]

import sqlite3
import time
from typing import Optional

from config import SUBS_DB


def _conn():
    c = sqlite3.connect(SUBS_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_ads_db():
    with _conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS ads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            type       TEXT NOT NULL,
            text       TEXT NOT NULL DEFAULT '',
            url        TEXT DEFAULT NULL,
            btn_label  TEXT DEFAULT NULL,
            show_date  TEXT NOT NULL,
            amount     REAL NOT NULL,
            invoice_id INTEGER DEFAULT NULL,
            status     TEXT NOT NULL DEFAULT 'unpaid',
            created_at INTEGER NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bot_users (
            user_id    INTEGER PRIMARY KEY,
            first_seen INTEGER NOT NULL
        )''')


AD_PRICES = {'button': 10.0, 'broadcast': 8.0}


def create_ad(user_id, ad_type, text, url, btn_label, show_date) -> int:
    """Returns new ad id."""
    amount = AD_PRICES[ad_type]
    with _conn() as c:
        cur = c.execute(
            'INSERT INTO ads(user_id,type,text,url,btn_label,show_date,amount,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (user_id, ad_type, text, url, btn_label, show_date, amount, int(time.time()))
        )
    return cur.lastrowid


def set_ad_invoice(ad_id, invoice_id):
    with _conn() as c:
        c.execute('UPDATE ads SET invoice_id=?, status="pending_payment" WHERE id=?', (invoice_id, ad_id))


def activate_ad(ad_id):
    """Mark ad as paid/pending admin review."""
    with _conn() as c:
        c.execute('UPDATE ads SET status="pending" WHERE id=?', (ad_id,))


def approve_ad(ad_id):
    with _conn() as c:
        c.execute('UPDATE ads SET status="approved" WHERE id=?', (ad_id,))


def reject_ad(ad_id):
    with _conn() as c:
        c.execute('UPDATE ads SET status="rejected" WHERE id=?', (ad_id,))


def mark_ad_shown(ad_id):
    with _conn() as c:
        c.execute('UPDATE ads SET status="shown" WHERE id=?', (ad_id,))


def get_ad(ad_id) -> Optional[dict]:
    with _conn() as c:
        row = c.execute('SELECT * FROM ads WHERE id=?', (ad_id,)).fetchone()
    return dict(row) if row else None


def get_pending_ads() -> list:
    """Ads waiting for admin review."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM ads WHERE status='pending' ORDER BY show_date").fetchall()
    return [dict(r) for r in rows]


def get_ads_for_date(show_date: str, ad_type: str) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM ads WHERE show_date=? AND type=? AND status IN ('approved','pending')",
            (show_date, ad_type)
        ).fetchall()
    return [dict(r) for r in rows]


def get_todays_active_button_ad() -> Optional[dict]:
    from datetime import date
    today = date.today().isoformat()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM ads WHERE show_date=? AND type='button' AND status IN ('approved','pending') LIMIT 1",
            (today,)
        ).fetchone()
    return dict(row) if row else None


def get_todays_broadcast_ads() -> list:
    from datetime import date
    today = date.today().isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM ads WHERE show_date=? AND type='broadcast' AND status='approved'",
            (today,)
        ).fetchall()
    return [dict(r) for r in rows]


def is_slot_taken(show_date: str, ad_type: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM ads WHERE show_date=? AND type=? AND status NOT IN ('unpaid','rejected')",
            (show_date, ad_type)
        ).fetchone()
    return bool(row)


def get_pending_ad_invoices() -> list:
    """Returns [(invoice_id, ad_id), ...]"""
    with _conn() as c:
        rows = c.execute(
            "SELECT invoice_id, id FROM ads WHERE status='pending_payment' AND invoice_id IS NOT NULL"
        ).fetchall()
    return [(r['invoice_id'], r['id']) for r in rows]


def add_bot_user(user_id: int):
    with _conn() as c:
        c.execute(
            'INSERT OR IGNORE INTO bot_users(user_id, first_seen) VALUES(?,?)',
            (user_id, int(time.time()))
        )


def get_all_bot_users() -> list:
    with _conn() as c:
        rows = c.execute('SELECT user_id FROM bot_users').fetchall()
    return [r['user_id'] for r in rows]

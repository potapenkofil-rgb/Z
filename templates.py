import sqlite3

from config import SUBS_DB


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SUBS_DB)
    c.row_factory = sqlite3.Row
    return c


def init_templates_db():
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS templates (
                user_id INTEGER,
                name    TEXT,
                text    TEXT NOT NULL,
                PRIMARY KEY (user_id, name)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id    INTEGER,
                chat_id    INTEGER,
                chat_title TEXT DEFAULT '',
                PRIMARY KEY (user_id, chat_id)
            )
        ''')


# ── Templates ──────────────────────────────────────────────────────

def save_template(user_id: int, name: str, text: str):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO templates(user_id, name, text) VALUES (?,?,?)',
            (user_id, name, text),
        )


def get_template(user_id: int, name: str) -> str | None:
    with _conn() as c:
        row = c.execute(
            'SELECT text FROM templates WHERE user_id=? AND name=?',
            (user_id, name),
        ).fetchone()
    return row['text'] if row else None


def list_templates(user_id: int) -> list[tuple[str, str]]:
    with _conn() as c:
        rows = c.execute(
            'SELECT name, text FROM templates WHERE user_id=? ORDER BY name',
            (user_id,),
        ).fetchall()
    return [(r['name'], r['text']) for r in rows]


def delete_template(user_id: int, name: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            'DELETE FROM templates WHERE user_id=? AND name=?',
            (user_id, name),
        )
    return cur.rowcount > 0


# ── Blacklist ──────────────────────────────────────────────────────

def add_to_blacklist(user_id: int, chat_id: int, chat_title: str = ''):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO blacklist(user_id, chat_id, chat_title) VALUES (?,?,?)',
            (user_id, chat_id, chat_title),
        )


def remove_from_blacklist(user_id: int, chat_id: int):
    with _conn() as c:
        c.execute(
            'DELETE FROM blacklist WHERE user_id=? AND chat_id=?',
            (user_id, chat_id),
        )


def get_blacklist(user_id: int) -> list[tuple[int, str]]:
    with _conn() as c:
        rows = c.execute(
            'SELECT chat_id, chat_title FROM blacklist WHERE user_id=?',
            (user_id,),
        ).fetchall()
    return [(r['chat_id'], r['chat_title']) for r in rows]


def is_blacklisted(user_id: int, chat_id: int) -> bool:
    with _conn() as c:
        row = c.execute(
            'SELECT 1 FROM blacklist WHERE user_id=? AND chat_id=?',
            (user_id, chat_id),
        ).fetchone()
    return bool(row)

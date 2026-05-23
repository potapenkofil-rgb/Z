import sqlite3

from config import SUBS_DB


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SUBS_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_templates_db():
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS templates (
                user_id    INTEGER,
                name       TEXT,
                text       TEXT NOT NULL,
                media_path TEXT DEFAULT NULL,
                PRIMARY KEY (user_id, name)
            )
        ''')
        try:
            c.execute('ALTER TABLE templates ADD COLUMN media_path TEXT DEFAULT NULL')
        except Exception:
            pass
        c.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id    INTEGER,
                chat_id    INTEGER,
                chat_title TEXT DEFAULT '',
                PRIMARY KEY (user_id, chat_id)
            )
        ''')


# ── Templates ──────────────────────────────────────────────────────

def save_template(user_id: int, name: str, text: str, media_path: str | None = None):
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO templates(user_id, name, text, media_path) VALUES (?,?,?,?)',
            (user_id, name, text, media_path),
        )


def get_template(user_id: int, name: str) -> dict | None:
    """Returns {'text': ..., 'media_path': ...} or None."""
    with _conn() as c:
        row = c.execute(
            'SELECT text, media_path FROM templates WHERE user_id=? AND name=?',
            (user_id, name),
        ).fetchone()
    return {'text': row['text'], 'media_path': row['media_path']} if row else None


def list_templates(user_id: int) -> list[tuple[int, str, str]]:
    """Returns [(rowid, name, text), ...]"""
    with _conn() as c:
        rows = c.execute(
            'SELECT rowid, name, text FROM templates WHERE user_id=? ORDER BY name',
            (user_id,),
        ).fetchall()
    return [(r['rowid'], r['name'], r['text']) for r in rows]


def get_template_by_rowid(rowid: int, user_id: int) -> tuple[str, str, str | None] | None:
    """Returns (name, text, media_path) or None."""
    with _conn() as c:
        row = c.execute(
            'SELECT name, text, media_path FROM templates WHERE rowid=? AND user_id=?',
            (rowid, user_id),
        ).fetchone()
    return (row['name'], row['text'], row['media_path']) if row else None


def update_template(rowid: int, user_id: int, new_name: str, new_text: str,
                    media_path: str | None = None) -> bool:
    with _conn() as c:
        cur = c.execute(
            'UPDATE templates SET name=?, text=?, media_path=? WHERE rowid=? AND user_id=?',
            (new_name, new_text, media_path, rowid, user_id),
        )
    return cur.rowcount > 0


def delete_template(user_id: int, name: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            'DELETE FROM templates WHERE user_id=? AND name=?',
            (user_id, name),
        )
    return cur.rowcount > 0


def delete_template_by_rowid(rowid: int, user_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            'DELETE FROM templates WHERE rowid=? AND user_id=?',
            (rowid, user_id),
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


def blacklisted_ids(user_id: int) -> set[int]:
    return {chat_id for chat_id, _ in get_blacklist(user_id)}

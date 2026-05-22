import os
import sqlite3

DB_PATH = 'sessions/subs.db'


def _conn() -> sqlite3.Connection:
    os.makedirs('sessions', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS templates '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, '
        'name TEXT NOT NULL, text TEXT NOT NULL)'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS blacklist '
        '(user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT "", '
        'PRIMARY KEY (user_id, chat_id))'
    )
    conn.commit()
    return conn


def get_templates(user_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            'SELECT id, name, text FROM templates WHERE user_id=? ORDER BY id',
            (user_id,)
        ).fetchall()
    return [{'id': r[0], 'name': r[1], 'text': r[2]} for r in rows]


def add_template(user_id: int, name: str, text: str) -> int:
    with _conn() as c:
        cur = c.execute(
            'INSERT INTO templates (user_id, name, text) VALUES (?, ?, ?)',
            (user_id, name, text),
        )
        return cur.lastrowid


def delete_template(template_id: int, user_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            'DELETE FROM templates WHERE id=? AND user_id=?',
            (template_id, user_id),
        )
        return cur.rowcount > 0


def get_blacklist(user_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            'SELECT chat_id, title FROM blacklist WHERE user_id=? ORDER BY title',
            (user_id,)
        ).fetchall()
    return [{'chat_id': r[0], 'title': r[1]} for r in rows]


def add_to_blacklist(user_id: int, chat_id: int, title: str = '') -> None:
    with _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO blacklist (user_id, chat_id, title) VALUES (?, ?, ?)',
            (user_id, chat_id, title),
        )


def remove_from_blacklist(user_id: int, chat_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            'DELETE FROM blacklist WHERE user_id=? AND chat_id=?',
            (user_id, chat_id),
        )
        return cur.rowcount > 0


def blacklisted_ids(user_id: int) -> set[int]:
    return {e['chat_id'] for e in get_blacklist(user_id)}

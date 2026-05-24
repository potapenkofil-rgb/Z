import sqlite3

from config import SUBS_DB

MODE_ALL   = 'all'    # чаты + каналы + ЛС
MODE_NO_DM = 'no_dm'  # только чаты + каналы


def _conn():
    c = sqlite3.connect(SUBS_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_settings_db():
    with _conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_checker_modes (
            user_id INTEGER PRIMARY KEY,
            mode    TEXT NOT NULL
        )''')


def _get(key: str, default: str = '') -> str:
    with _conn() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def _set(key: str, value: str):
    with _conn() as c:
        c.execute(
            'INSERT INTO settings(key,value) VALUES(?,?) '
            'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, value),
        )


def get_global_checker_mode() -> str:
    return _get('checker_dm_mode', MODE_NO_DM)


def set_global_checker_mode(mode: str):
    _set('checker_dm_mode', mode)


def get_user_checker_mode(user_id: int) -> str:
    """Returns MODE_ALL, MODE_NO_DM, or 'inherit' (use global)."""
    with _conn() as c:
        row = c.execute(
            'SELECT mode FROM user_checker_modes WHERE user_id=?', (user_id,)
        ).fetchone()
    return row['mode'] if row else 'inherit'


def set_user_checker_mode(user_id: int, mode: str):
    with _conn() as c:
        if mode == 'inherit':
            c.execute('DELETE FROM user_checker_modes WHERE user_id=?', (user_id,))
        else:
            c.execute(
                'INSERT INTO user_checker_modes(user_id,mode) VALUES(?,?) '
                'ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode',
                (user_id, mode),
            )


def should_catch_dm(user_id: int) -> bool:
    """Returns True if DMs should be processed for this user."""
    user_mode = get_user_checker_mode(user_id)
    effective  = user_mode if user_mode != 'inherit' else get_global_checker_mode()
    return effective == MODE_ALL


def get_all_user_overrides() -> list:
    with _conn() as c:
        rows = c.execute('SELECT * FROM user_checker_modes').fetchall()
    return [dict(r) for r in rows]

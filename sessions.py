import json
import os
import threading

from config import ADMINS_FILE, SESSIONS_META, SUPER_ADMIN_ID

_meta_lock   = threading.Lock()
_admins_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────────
# Session meta helpers
# ─────────────────────────────────────────────────────────────────

def load_meta() -> dict:
    with _meta_lock:
        if os.path.exists(SESSIONS_META):
            with open(SESSIONS_META) as f:
                return json.load(f)
        return {}


def save_meta(meta: dict):
    with _meta_lock:
        tmp = SESSIONS_META + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(meta, f)
        os.replace(tmp, SESSIONS_META)


# ─────────────────────────────────────────────────────────────────
# Admin helpers
# ─────────────────────────────────────────────────────────────────

def load_admins() -> list[int]:
    with _admins_lock:
        if os.path.exists(ADMINS_FILE):
            with open(ADMINS_FILE) as f:
                return json.load(f).get('admins', [])
        return []


def save_admins(admins: list[int]) -> None:
    with _admins_lock:
        tmp = ADMINS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'admins': admins}, f)
        os.replace(tmp, ADMINS_FILE)


def is_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID or user_id in load_admins()


def add_admin(user_id: int) -> None:
    admins = load_admins()
    if user_id not in admins and user_id != SUPER_ADMIN_ID:
        admins.append(user_id)
        save_admins(admins)


def remove_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID:
        return False
    admins = load_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_admins(admins)
        return True
    return False

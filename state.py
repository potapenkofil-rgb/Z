# ─────────────────────────────────────────────────────────────────
# Shared mutable state
# No local imports — keeps this module dependency-free to avoid
# circular import chains.
# ─────────────────────────────────────────────────────────────────

# Временные auth-клиенты во время FSM авторизации
# Ключи: user_id (int) для обычных, "adm_{user_id}" (str) для admin-checker
active: dict = {}

# Запущенные userbot-треды
# { user_id: {'client': TelegramClient, 'loop': asyncio loop, 'main_loop': main asyncio loop} }
# user_id == -1 зарезервирован для аккаунта-ловца чеков
userbot_refs: dict = {}

# Ожидающие конфигурации gflood (пока пользователь выбирает папку)
# { user_id: {'delay': ..., 'count': ..., 'mode': ..., 'text': ..., 'media': ...} }
pending_gflood: dict = {}

# Глобальная дедупликация чеков — чтобы один чек не активировался дважды,
# даже если его увидели несколько аккаунтов одновременно
_globally_processed: set = set()

# User IDs, для которых тред уже запущен но ещё не добавил себя в userbot_refs
# Защита от race condition при двойном вызове connect_and_run
_launching: set = set()

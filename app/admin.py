from datetime import datetime

from app.db import Database


class AdminService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def is_admin(self, user_id: int) -> bool:
        return self._db.is_user_admin(user_id)

    def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        return self._db.is_chat_admin(user_id, chat_id)

    def add_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._db.add_chat_admin(user_id, chat_id)

    def remove_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._db.remove_chat_admin(user_id, chat_id)

    def ban_user(self, user_id: int, chat_id: int, banned_until: datetime | None) -> None:
        self._db.add_chat_ban(user_id, chat_id, banned_until)

    def unban_user(self, user_id: int, chat_id: int) -> None:
        self._db.remove_chat_ban(user_id, chat_id)

    def is_banned(self, user_id: int, chat_id: int) -> bool:
        return self._db.is_chat_banned(user_id, chat_id)

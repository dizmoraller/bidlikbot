from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple, Set

import sqlite3
import threading


GLOBAL_CHAT_ID = 0
INSULT_PROBABILITY_KEY = "insult_probability"
DEFAULT_INSULT_PROBABILITY = 0.02
INSULT_BOOST_KEY = "insult_boost_multiplier"
DEFAULT_INSULT_BOOST = 2.0
INSULT_LEVEL_KEY = "insult_level"
DEFAULT_INSULT_LEVEL = 4
QUESTION_PHRASE_CHANCE_KEY = "question_phrase_chance"
DEFAULT_QUESTION_PHRASE_CHANCE = 0.5
WHEN_PHRASE_CHANCE_KEY = "when_phrase_chance"
DEFAULT_WHEN_PHRASE_CHANCE = 0.5
DEFAULT_QUESTION_TEMPLATES = [
    ("кто", "{mention}{question}"),
    ("кого", "{mention}'а{question}"),
    ("у кого", "У {mention}'а{question}"),
    ("кому", "{mention}'у{question}"),
    ("с кем", "С {mention}'ом{question}"),
    ("кем", "{mention}'ом{question}"),
    ("в ком", "В {mention}'е{question}"),
    ("чей", "{mention}'а{question}"),
    ("чьё", "{mention}'а{question}"),
    ("чья", "{mention}'а{question}"),
    ("чьи", "{mention}'а{question}"),
    ("сколько", "{number}"),
]


@dataclass
class UserRecord:
    id: int
    username: str
    chat_id: int
    tag: bool
    is_admin: bool


@dataclass
class QuestionTemplate:
    trigger_text: str
    response_template: str
    chat_id: int = GLOBAL_CHAT_ID


class Database:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._lock = threading.Lock()
        self._ensure_tables()

    def _fetchone(self, query: str, params=()) -> Optional[Sequence]:
        """Execute a query and return the first row (or None)."""
        with self._lock:
            return self._connection.execute(query, params).fetchone()

    def _fetchall(self, query: str, params=()) -> List[Sequence]:
        """Execute a query and return all rows."""
        with self._lock:
            return self._connection.execute(query, params).fetchall() or []

    def _commit_query(self, query: str, params=()):
        """Execute a query and commit."""
        with self._lock:
            self._connection.execute(query, params)
            self._connection.commit()

    @classmethod
    def init(cls, database_path: str) -> "Database":
        connection = sqlite3.connect(database_path, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        return cls(connection)

    def ensure_user(self, user_id: int, username: str, chat_id: int) -> None:
        self._commit_query(
            """
            INSERT INTO "user" (id, username, chat_id)
            VALUES (?, ?, ?)
            ON CONFLICT (id, chat_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, chat_id),
        )

    def get_user(self, user_id: int, chat_id: int) -> Optional[UserRecord]:
        row = self._fetchone(
            "SELECT id, username, chat_id, tag, is_admin FROM user WHERE id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        return self._map_user(row)

    def get_tagged_users(self, chat_id: int) -> List[UserRecord]:
        rows = self._fetchall(
            "SELECT id, username, chat_id, tag, is_admin FROM user WHERE chat_id = ? AND tag = 1",
            (chat_id,),
        )
        return [self._map_user(row) for row in rows if row]

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        row = self._fetchone(
            """
            SELECT id, username, chat_id, tag, is_admin
            FROM user
            WHERE LOWER(username) = LOWER(?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (username,),
        )
        return self._map_user(row)

    def get_tag_status(self, user_id: int, chat_id: int) -> Optional[bool]:
        row = self._fetchone(
            "SELECT tag FROM user WHERE id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        return row[0] if row else None

    def set_tag_status(self, user_id: int, chat_id: int, should_tag: bool) -> None:
        self._commit_query(
            "UPDATE user SET tag = ? WHERE id = ? AND chat_id = ?",
            (should_tag, user_id, chat_id),
        )

    def get_question_templates(self, chat_id: Optional[int] = None) -> List[QuestionTemplate]:
        if chat_id is None:
            params = (GLOBAL_CHAT_ID,)
            query = "SELECT chat_id, trigger_text, response_template FROM question_templates WHERE chat_id = ?"
        else:
            params = (GLOBAL_CHAT_ID, chat_id)
            query = "SELECT chat_id, trigger_text, response_template FROM question_templates WHERE chat_id IN (?, ?)"

        rows = self._fetchall(query, params)
        template_map = {}
        for row in rows:
            tpl_chat_id, trigger, response = row
            if tpl_chat_id == GLOBAL_CHAT_ID and trigger in template_map:
                continue
            template_map[trigger] = QuestionTemplate(
                trigger_text=trigger,
                response_template=response,
                chat_id=tpl_chat_id,
            )
        return list(template_map.values())

    def get_question_triggers(self, chat_id: Optional[int] = None) -> List[str]:
        templates = self.get_question_templates(chat_id)
        return sorted({template.trigger_text for template in templates})

    def save_question_template(self, template: QuestionTemplate) -> None:
        self._commit_query(
            """
            INSERT INTO question_templates (chat_id, trigger_text, response_template)
            VALUES (?, ?, ?)
            ON CONFLICT (chat_id, trigger_text) DO UPDATE SET
                response_template = excluded.response_template
            """,
            (template.chat_id, template.trigger_text, template.response_template),
        )

    def delete_question_template(self, chat_id: int, trigger_text: str) -> bool:
        self._commit_query(
            "DELETE FROM question_templates WHERE chat_id = ? AND trigger_text = ?",
            (chat_id, trigger_text),
        )
        return self._connection.total_changes > 0

    def get_insult_probability(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_PROBABILITY_KEY)
            if chat_value is not None:
                try:
                    return float(chat_value)
                except (TypeError, ValueError):
                    pass

        row = self._fetchone(
            """
            SELECT value FROM bot_settings WHERE key = ?
            """,
            (INSULT_PROBABILITY_KEY,),
        )
        if not row:
            return DEFAULT_INSULT_PROBABILITY
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return DEFAULT_INSULT_PROBABILITY

    def set_insult_probability(self, probability: float, chat_id: Optional[int] = None) -> None:
        if chat_id is not None:
            self._set_chat_setting(chat_id, INSULT_PROBABILITY_KEY, str(probability))
            return

        self._commit_query(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (INSULT_PROBABILITY_KEY, str(probability)),
        )

    def get_insult_boost_multiplier(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_BOOST_KEY)
            if chat_value is not None:
                try:
                    return max(1.0, float(chat_value))
                except (TypeError, ValueError):
                    pass

        row = self._fetchone(
            "SELECT value FROM bot_settings WHERE key = ?",
            (INSULT_BOOST_KEY,),
        )
        if not row:
            return DEFAULT_INSULT_BOOST
        try:
            return max(1.0, float(row[0]))
        except (TypeError, ValueError):
            return DEFAULT_INSULT_BOOST

    def set_insult_boost_multiplier(self, multiplier: float, chat_id: Optional[int] = None) -> None:
        multiplier = max(1.0, multiplier)
        if chat_id is not None:
            self._set_chat_setting(chat_id, INSULT_BOOST_KEY, str(multiplier))
            return

        self._commit_query(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (INSULT_BOOST_KEY, str(multiplier)),
        )

    def get_insult_level(self, chat_id: Optional[int] = None) -> int:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_LEVEL_KEY)
            if chat_value is not None:
                try:
                    return int(chat_value)
                except ValueError:
                    pass

        row = self._fetchone(
            """
            SELECT value FROM bot_settings WHERE key = ?
            """,
            (INSULT_LEVEL_KEY,),
        )
        if not row:
            return DEFAULT_INSULT_LEVEL
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return DEFAULT_INSULT_LEVEL

    def get_question_phrase_chance(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, QUESTION_PHRASE_CHANCE_KEY)
            if chat_value is not None:
                try:
                    return max(0.0, min(1.0, float(chat_value)))
                except (TypeError, ValueError):
                    pass

        row = self._fetchone(
            "SELECT value FROM bot_settings WHERE key = ?",
            (QUESTION_PHRASE_CHANCE_KEY,),
        )
        if not row:
            return DEFAULT_QUESTION_PHRASE_CHANCE
        try:
            return max(0.0, min(1.0, float(row[0])))
        except (TypeError, ValueError):
            return DEFAULT_QUESTION_PHRASE_CHANCE

    def get_when_phrase_chance(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, WHEN_PHRASE_CHANCE_KEY)
            if chat_value is not None:
                try:
                    return max(0.0, min(1.0, float(chat_value)))
                except (TypeError, ValueError):
                    pass

        row = self._fetchone(
            "SELECT value FROM bot_settings WHERE key = ?",
            (WHEN_PHRASE_CHANCE_KEY,),
        )
        if not row:
            return DEFAULT_WHEN_PHRASE_CHANCE
        try:
            return max(0.0, min(1.0, float(row[0])))
        except (TypeError, ValueError):
            return DEFAULT_WHEN_PHRASE_CHANCE

    def set_insult_level(self, level: int, chat_id: Optional[int] = None) -> None:
        if chat_id is not None:
            self._set_chat_setting(chat_id, INSULT_LEVEL_KEY, str(level))
            return

        self._commit_query(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (INSULT_LEVEL_KEY, str(level)),
        )

    def set_question_phrase_chance(self, chance: float, chat_id: Optional[int] = None) -> None:
        chance = max(0.0, min(1.0, chance))
        if chat_id is not None:
            self._set_chat_setting(chat_id, QUESTION_PHRASE_CHANCE_KEY, str(chance))
            return

        self._commit_query(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (QUESTION_PHRASE_CHANCE_KEY, str(chance)),
        )

    def set_when_phrase_chance(self, chance: float, chat_id: Optional[int] = None) -> None:
        chance = max(0.0, min(1.0, chance))
        if chat_id is not None:
            self._set_chat_setting(chat_id, WHEN_PHRASE_CHANCE_KEY, str(chance))
            return

        self._commit_query(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (WHEN_PHRASE_CHANCE_KEY, str(chance)),
        )

    def get_chat_insult_overrides(self, chat_id: int) -> Tuple[Optional[float], Optional[int], Optional[float]]:
        raw_probability = self._get_chat_setting(chat_id, INSULT_PROBABILITY_KEY)
        raw_level = self._get_chat_setting(chat_id, INSULT_LEVEL_KEY)
        raw_multiplier = self._get_chat_setting(chat_id, INSULT_BOOST_KEY)
        probability = None
        level = None
        multiplier = None
        if raw_probability is not None:
            try:
                probability = float(raw_probability)
            except (TypeError, ValueError):
                probability = None
        if raw_level is not None:
            try:
                level = int(raw_level)
            except (TypeError, ValueError):
                level = None
        if raw_multiplier is not None:
            try:
                multiplier = max(1.0, float(raw_multiplier))
            except (TypeError, ValueError):
                multiplier = None
        return probability, level, multiplier

    def get_chat_question_phrase_override(self, chat_id: int) -> Optional[float]:
        raw_value = self._get_chat_setting(chat_id, QUESTION_PHRASE_CHANCE_KEY)
        if raw_value is None:
            return None
        try:
            return max(0.0, min(1.0, float(raw_value)))
        except (TypeError, ValueError):
            return None

    def get_chat_when_phrase_override(self, chat_id: int) -> Optional[float]:
        raw_value = self._get_chat_setting(chat_id, WHEN_PHRASE_CHANCE_KEY)
        if raw_value is None:
            return None
        try:
            return max(0.0, min(1.0, float(raw_value)))
        except (TypeError, ValueError):
            return None

    def is_user_admin(self, user_id: int) -> bool:
        row = self._fetchone(
            "SELECT COUNT(*) FROM user WHERE id = ? AND is_admin = 1",
            (user_id,),
        )
        return bool(row[0]) if row else False

    def set_user_admin(self, user_id: int, is_admin: bool) -> None:
        self._commit_query(
            "UPDATE user SET is_admin = ? WHERE id = ?",
            (is_admin, user_id),
        )

    def add_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._commit_query(
            """
            INSERT INTO chat_admins (user_id, chat_id)
            VALUES (?, ?)
            ON CONFLICT (user_id, chat_id) DO NOTHING
            """,
            (user_id, chat_id),
        )

    def remove_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._commit_query(
            "DELETE FROM chat_admins WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )

    def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM chat_admins WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        return row is not None

    def get_chat_admin_ids(self, chat_id: int) -> Set[int]:
        rows = self._fetchall(
            "SELECT user_id FROM chat_admins WHERE chat_id = ?",
            (chat_id,),
        )
        return {row[0] for row in rows if row and row[0] is not None}

    def add_chat_ban(self, user_id: int, chat_id: int, banned_until: Optional[datetime]) -> None:
        value = (
            banned_until.astimezone(timezone.utc).isoformat() if banned_until is not None else None
        )
        self._commit_query(
            """
            INSERT INTO chat_bans (user_id, chat_id, banned_until)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET banned_until = excluded.banned_until
            """,
            (user_id, chat_id, value),
        )

    def remove_chat_ban(self, user_id: int, chat_id: int) -> None:
        self._commit_query(
            "DELETE FROM chat_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )

    def is_chat_banned(self, user_id: int, chat_id: int) -> bool:
        row = self._fetchone(
            "SELECT banned_until FROM chat_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        if not row:
            return False
        banned_until_str = row[0]
        if banned_until_str:
            banned_until = datetime.fromisoformat(banned_until_str).replace(tzinfo=timezone.utc)
            if banned_until <= datetime.now(timezone.utc):
                self.remove_chat_ban(user_id, chat_id)
                return False
        return True

    def get_chat_users(self, chat_id: int) -> List[UserRecord]:
        rows = self._fetchall(
            "SELECT id, username, chat_id, tag, is_admin FROM user WHERE chat_id = ? ORDER BY CASE WHEN username IS NULL THEN 1 ELSE 0 END, username, id",
            (chat_id,),
        )
        return [self._map_user(row) for row in rows if row]

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _map_user(row: Optional[Sequence]) -> Optional[UserRecord]:
        if not row:
            return None
        user_id, username, chat_id, tag, is_admin = row
        return UserRecord(
            id=user_id,
            username=username or "",
            chat_id=chat_id,
            tag=bool(tag),
            is_admin=bool(is_admin),
        )

    def _ensure_question_templates_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS question_templates (
                chat_id INTEGER NOT NULL DEFAULT 0,
                trigger_text TEXT NOT NULL,
                response_template TEXT NOT NULL,
                PRIMARY KEY (chat_id, trigger_text)
            )
            """
        )

    def _ensure_settings_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

    def _ensure_chat_settings_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            )
            """
        )

    def _ensure_chat_admins_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS chat_admins (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )

    def _ensure_chat_bans_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS chat_bans (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                banned_until TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )

    def _ensure_tables(self) -> None:
        self._ensure_user_table()
        self._ensure_question_templates_table()
        self._ensure_settings_table()
        self._ensure_chat_settings_table()
        self._ensure_chat_admins_table()
        self._ensure_chat_bans_table()
        self._ensure_default_question_templates()

    def _ensure_user_table(self) -> None:
        self._commit_query(
            """
            CREATE TABLE IF NOT EXISTS "user" (
                id       INTEGER,
                username TEXT,
                chat_id  INTEGER,
                tag      INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                PRIMARY KEY (id, chat_id)
            )
            """
        )

    def _ensure_default_question_templates(self) -> None:
        existing = {row[0] for row in self._fetchall(
            "SELECT trigger_text FROM question_templates WHERE chat_id = ?",
            (GLOBAL_CHAT_ID,),
        )}
        templates_to_insert = [
            (GLOBAL_CHAT_ID, trigger, template)
            for trigger, template in DEFAULT_QUESTION_TEMPLATES
            if trigger not in existing
        ]
        if not templates_to_insert:
            return
        with self._lock:
            self._connection.executemany(
                """
                INSERT INTO question_templates (chat_id, trigger_text, response_template)
                VALUES (?, ?, ?)
                """,
                templates_to_insert,
            )
            self._connection.commit()

    def _get_chat_setting(self, chat_id: int, key: str) -> Optional[str]:
        row = self._fetchone(
            "SELECT value FROM chat_settings WHERE chat_id = ? AND key = ?",
            (chat_id, key),
        )
        return row[0] if row else None

    def _set_chat_setting(self, chat_id: int, key: str, value: str) -> None:
        self._commit_query(
            """
            INSERT INTO chat_settings (chat_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT (chat_id, key) DO UPDATE SET value = excluded.value
            """,
            (chat_id, key, value),
        )

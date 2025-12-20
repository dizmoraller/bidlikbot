from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple, Set

import psycopg2


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
        self._cursor = connection.cursor()
        self._ensure_user_admin_column()
        self._ensure_user_unique_constraint()
        self._ensure_question_templates_table()
        self._ensure_settings_table()
        self._ensure_chat_settings_table()
        self._ensure_chat_admins_table()
        self._ensure_chat_bans_table()
        self._ensure_default_question_templates()

    @classmethod
    def init(cls, database_url: str) -> "Database":
        connection = psycopg2.connect(database_url)
        return cls(connection)

    def ensure_user(self, user_id: int, username: str, chat_id: int) -> None:
        self._cursor.execute(
            """
            INSERT INTO users.user (id, username, chat_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id, chat_id) DO UPDATE SET username = EXCLUDED.username
            """,
            (user_id, username, chat_id),
        )
        self._connection.commit()

    def get_user(self, user_id: int, chat_id: int) -> Optional[UserRecord]:
        self._cursor.execute(
            "SELECT id, username, chat_id, tag, is_admin FROM users.user WHERE id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        row = self._cursor.fetchone()
        return self._map_user(row)

    def get_tagged_users(self, chat_id: int) -> List[UserRecord]:
        self._cursor.execute(
            "SELECT id, username, chat_id, tag, is_admin FROM users.user WHERE chat_id = %s AND tag = True",
            (chat_id,),
        )
        rows = self._cursor.fetchall() or []
        return [self._map_user(row) for row in rows if row]

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        self._cursor.execute(
            """
            SELECT id, username, chat_id, tag, is_admin
            FROM users.user
            WHERE LOWER(username) = LOWER(%s)
            ORDER BY id DESC
            LIMIT 1
            """,
            (username,),
        )
        row = self._cursor.fetchone()
        return self._map_user(row)

    def get_tag_status(self, user_id: int, chat_id: int) -> Optional[bool]:
        self._cursor.execute(
            "SELECT tag FROM users.user WHERE id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        row = self._cursor.fetchone()
        return row[0] if row else None

    def set_tag_status(self, user_id: int, chat_id: int, should_tag: bool) -> None:
        self._cursor.execute(
            "UPDATE users.user SET tag = %s WHERE id = %s AND chat_id = %s",
            (should_tag, user_id, chat_id),
        )
        self._connection.commit()

    def get_question_templates(self, chat_id: Optional[int] = None) -> List[QuestionTemplate]:
        if chat_id is None:
            params = (GLOBAL_CHAT_ID,)
            query = "SELECT chat_id, trigger_text, response_template FROM users.question_templates WHERE chat_id = %s"
        else:
            params = (GLOBAL_CHAT_ID, chat_id)
            query = "SELECT chat_id, trigger_text, response_template FROM users.question_templates WHERE chat_id IN (%s, %s)"

        self._cursor.execute(query, params)
        rows = self._cursor.fetchall() or []
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
        self._cursor.execute(
            """
            INSERT INTO users.question_templates (chat_id, trigger_text, response_template)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id, trigger_text) DO UPDATE SET
                response_template = EXCLUDED.response_template
            """,
            (template.chat_id, template.trigger_text, template.response_template),
        )
        self._connection.commit()

    def delete_question_template(self, chat_id: int, trigger_text: str) -> bool:
        self._cursor.execute(
            """
            DELETE FROM users.question_templates
            WHERE chat_id = %s AND trigger_text = %s
            """,
            (chat_id, trigger_text),
        )
        deleted = self._cursor.rowcount > 0
        self._connection.commit()
        return deleted

    def get_insult_probability(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_PROBABILITY_KEY)
            if chat_value is not None:
                try:
                    return float(chat_value)
                except (TypeError, ValueError):
                    pass

        self._cursor.execute(
            """
            SELECT value FROM users.bot_settings WHERE key = %s
            """,
            (INSULT_PROBABILITY_KEY,),
        )
        row = self._cursor.fetchone()
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

        self._cursor.execute(
            """
            INSERT INTO users.bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (INSULT_PROBABILITY_KEY, str(probability)),
        )
        self._connection.commit()

    def get_insult_boost_multiplier(self, chat_id: Optional[int] = None) -> float:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_BOOST_KEY)
            if chat_value is not None:
                try:
                    return max(1.0, float(chat_value))
                except (TypeError, ValueError):
                    pass

        self._cursor.execute(
            "SELECT value FROM users.bot_settings WHERE key = %s",
            (INSULT_BOOST_KEY,),
        )
        row = self._cursor.fetchone()
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

        self._cursor.execute(
            """
            INSERT INTO users.bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (INSULT_BOOST_KEY, str(multiplier)),
        )
        self._connection.commit()

    def get_insult_level(self, chat_id: Optional[int] = None) -> int:
        if chat_id is not None:
            chat_value = self._get_chat_setting(chat_id, INSULT_LEVEL_KEY)
            if chat_value is not None:
                try:
                    return int(chat_value)
                except ValueError:
                    pass

        self._cursor.execute(
            """
            SELECT value FROM users.bot_settings WHERE key = %s
            """,
            (INSULT_LEVEL_KEY,),
        )
        row = self._cursor.fetchone()
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

        self._cursor.execute(
            "SELECT value FROM users.bot_settings WHERE key = %s",
            (QUESTION_PHRASE_CHANCE_KEY,),
        )
        row = self._cursor.fetchone()
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

        self._cursor.execute(
            "SELECT value FROM users.bot_settings WHERE key = %s",
            (WHEN_PHRASE_CHANCE_KEY,),
        )
        row = self._cursor.fetchone()
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

        self._cursor.execute(
            """
            INSERT INTO users.bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (INSULT_LEVEL_KEY, str(level)),
        )
        self._connection.commit()

    def set_question_phrase_chance(self, chance: float, chat_id: Optional[int] = None) -> None:
        chance = max(0.0, min(1.0, chance))
        if chat_id is not None:
            self._set_chat_setting(chat_id, QUESTION_PHRASE_CHANCE_KEY, str(chance))
            return

        self._cursor.execute(
            """
            INSERT INTO users.bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (QUESTION_PHRASE_CHANCE_KEY, str(chance)),
        )
        self._connection.commit()

    def set_when_phrase_chance(self, chance: float, chat_id: Optional[int] = None) -> None:
        chance = max(0.0, min(1.0, chance))
        if chat_id is not None:
            self._set_chat_setting(chat_id, WHEN_PHRASE_CHANCE_KEY, str(chance))
            return

        self._cursor.execute(
            """
            INSERT INTO users.bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (WHEN_PHRASE_CHANCE_KEY, str(chance)),
        )
        self._connection.commit()

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
        self._cursor.execute(
            "SELECT COALESCE(bool_or(is_admin), FALSE) FROM users.user WHERE id = %s",
            (user_id,),
        )
        row = self._cursor.fetchone()
        return bool(row[0]) if row else False

    def set_user_admin(self, user_id: int, is_admin: bool) -> None:
        self._cursor.execute(
            "UPDATE users.user SET is_admin = %s WHERE id = %s",
            (is_admin, user_id),
        )
        self._connection.commit()

    def add_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._cursor.execute(
            """
            INSERT INTO users.chat_admins (user_id, chat_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, chat_id) DO NOTHING
            """,
            (user_id, chat_id),
        )
        self._connection.commit()

    def remove_chat_admin(self, user_id: int, chat_id: int) -> None:
        self._cursor.execute(
            "DELETE FROM users.chat_admins WHERE user_id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        self._connection.commit()

    def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        self._cursor.execute(
            "SELECT 1 FROM users.chat_admins WHERE user_id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        return self._cursor.fetchone() is not None

    def get_chat_admin_ids(self, chat_id: int) -> Set[int]:
        self._cursor.execute(
            "SELECT user_id FROM users.chat_admins WHERE chat_id = %s",
            (chat_id,),
        )
        rows = self._cursor.fetchall() or []
        return {row[0] for row in rows if row and row[0] is not None}

    def add_chat_ban(self, user_id: int, chat_id: int, banned_until: Optional[datetime]) -> None:
        value = (
            banned_until.astimezone(timezone.utc) if banned_until is not None else None
        )
        self._cursor.execute(
            """
            INSERT INTO users.chat_bans (user_id, chat_id, banned_until)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET banned_until = EXCLUDED.banned_until
            """,
            (user_id, chat_id, value),
        )
        self._connection.commit()

    def remove_chat_ban(self, user_id: int, chat_id: int) -> None:
        self._cursor.execute(
            "DELETE FROM users.chat_bans WHERE user_id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        self._connection.commit()

    def is_chat_banned(self, user_id: int, chat_id: int) -> bool:
        self._cursor.execute(
            "SELECT banned_until FROM users.chat_bans WHERE user_id = %s AND chat_id = %s",
            (user_id, chat_id),
        )
        row = self._cursor.fetchone()
        if not row:
            return False
        banned_until = row[0]
        if banned_until and banned_until <= datetime.now(timezone.utc):
            self.remove_chat_ban(user_id, chat_id)
            return False
        return True

    def get_chat_users(self, chat_id: int) -> List[UserRecord]:
        self._cursor.execute(
            "SELECT id, username, chat_id, tag, is_admin FROM users.user WHERE chat_id = %s ORDER BY username NULLS LAST, id",
            (chat_id,),
        )
        rows = self._cursor.fetchall() or []
        return [self._map_user(row) for row in rows if row]


    def close(self) -> None:
        self._cursor.close()
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
            tag=tag,
            is_admin=bool(is_admin),
        )

    def _ensure_question_templates_table(self) -> None:
        self._cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users.question_templates (
                chat_id BIGINT NOT NULL DEFAULT 0,
                trigger_text TEXT NOT NULL,
                response_template TEXT NOT NULL,
                PRIMARY KEY (chat_id, trigger_text)
            )
            """
        )
        self._connection.commit()
        self._migrate_question_templates_schema()

    def _migrate_question_templates_schema(self) -> None:
        self._cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'users' AND table_name = 'question_templates'
            """
        )
        columns = {row[0] for row in self._cursor.fetchall() or []}
        if "response_template" not in columns:
            self._cursor.execute(
                "ALTER TABLE users.question_templates ADD COLUMN response_template TEXT"
            )
            self._cursor.execute(
                """
                UPDATE users.question_templates
                SET response_template = COALESCE(user_template, bot_template, '{mention}{question}')
                """
            )
            self._connection.commit()
        if "chat_id" not in columns:
            self._cursor.execute(
                "ALTER TABLE users.question_templates ADD COLUMN chat_id BIGINT NOT NULL DEFAULT 0"
            )
            self._connection.commit()
        self._cursor.execute(
            "ALTER TABLE users.question_templates DROP CONSTRAINT IF EXISTS question_templates_pkey"
        )
        self._cursor.execute(
            "ALTER TABLE users.question_templates ADD PRIMARY KEY (chat_id, trigger_text)"
        )
        self._connection.commit()
        # Optionally drop old columns
        drop_columns = []
        if "bot_template" in columns:
            drop_columns.append("bot_template")
        if "user_template" in columns:
            drop_columns.append("user_template")
        for column in drop_columns:
            self._cursor.execute(f"ALTER TABLE users.question_templates DROP COLUMN IF EXISTS {column}")
        if drop_columns:
            self._connection.commit()

    def _ensure_settings_table(self) -> None:
        self._cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users.bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def _ensure_chat_settings_table(self) -> None:
        self._cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users.chat_settings (
                chat_id BIGINT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            )
            """
        )
        self._connection.commit()

    def _ensure_chat_admins_table(self) -> None:
        self._cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users.chat_admins (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )
        self._connection.commit()

    def _ensure_chat_bans_table(self) -> None:
        self._cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users.chat_bans (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                banned_until TIMESTAMPTZ,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )
        self._connection.commit()


    def _ensure_user_admin_column(self) -> None:
        self._cursor.execute(
            """
            ALTER TABLE users.user
            ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE
            """
        )
        self._cursor.execute(
            "UPDATE users.user SET is_admin = FALSE WHERE is_admin IS NULL"
        )
        self._connection.commit()

    def _ensure_user_unique_constraint(self) -> None:
        self._cursor.execute(
            """
            DELETE FROM users."user" a
            USING users."user" b
            WHERE a.ctid < b.ctid
              AND a.id = b.id
              AND a.chat_id = b.chat_id
            """
        )
        self._connection.commit()
        self._cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_schema = 'users'
                      AND table_name = 'user'
                      AND constraint_name = 'user_pk'
                ) THEN
                    ALTER TABLE users."user"
                    ADD CONSTRAINT user_pk PRIMARY KEY (id, chat_id);
                END IF;
            END $$;
            """
        )
        self._connection.commit()

    def _ensure_default_question_templates(self) -> None:
        self._cursor.execute(
            "SELECT trigger_text FROM users.question_templates WHERE chat_id = %s",
            (GLOBAL_CHAT_ID,),
        )
        existing = {row[0] for row in self._cursor.fetchall() or []}
        templates_to_insert = [
            (GLOBAL_CHAT_ID, trigger, template)
            for trigger, template in DEFAULT_QUESTION_TEMPLATES
            if trigger not in existing
        ]
        if not templates_to_insert:
            return

        self._cursor.executemany(
            """
            INSERT INTO users.question_templates (chat_id, trigger_text, response_template)
            VALUES (%s, %s, %s)
            """,
            templates_to_insert,
        )
        self._connection.commit()

    def _get_chat_setting(self, chat_id: int, key: str) -> Optional[str]:
        self._cursor.execute(
            "SELECT value FROM users.chat_settings WHERE chat_id = %s AND key = %s",
            (chat_id, key),
        )
        row = self._cursor.fetchone()
        return row[0] if row else None

    def _set_chat_setting(self, chat_id: int, key: str, value: str) -> None:
        self._cursor.execute(
            """
            INSERT INTO users.chat_settings (chat_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value
            """,
            (chat_id, key, value),
        )
        self._connection.commit()

import random
import re
from datetime import datetime, timedelta, timezone
from time import sleep
from collections import defaultdict, deque
from typing import DefaultDict, Deque, Dict, Optional, Tuple

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException

from app.admin import AdminService
from app.db import Database, QuestionTemplate, UserRecord, GLOBAL_CHAT_ID
from app.llm import LLM
from app.texts import (
    FLEXIBLE_TIME_RESPONSES,
    INSULT_FALLBACKS,
    QUANTITY_RESPONSES,
    TIME_UNIT_OPTIONS,
    WHEN_RESPONSES,
)
from app.utils import (
    generate_seed,
    handle_question_templates,
    reply_with_typing,
    when,
    find_question_match,
)


def register_handlers(bot: TeleBot, db: Database, llm: LLM, admin_service: AdminService) -> None:
    HISTORY_LIMIT = 10
    chat_history: DefaultDict[int, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))

    @bot.message_handler(content_types=["text", "photo", "video"])
    def handle_message(message):
        user_id = message.from_user.id
        username = message.from_user.username
        chat_id = message.chat.id
        raw_text = (message.text or message.caption or "") or ""
        text = raw_text.lower()
        db.ensure_user(user_id, username, chat_id)

        if admin_service.is_banned(user_id, chat_id):
            return

        _ensure_chat_owner_admin(bot, chat_id, user_id, admin_service)

        history_content = raw_text.strip() or _describe_non_text_message(message)
        if history_content:
            history_queue = chat_history.setdefault(chat_id, deque(maxlen=HISTORY_LIMIT))
            display_name = username or str(user_id)
            history_queue.append((display_name, history_content))

        if _handle_admin_commands(bot, message, text, raw_text, user_id, chat_id, db, admin_service):
            return

        template_scope = None if getattr(message.chat, "type", "") == "private" else chat_id
        question_templates = db.get_question_templates(template_scope)
        question_match = find_question_match(text, question_templates)

        scope_for_settings = chat_id if template_scope is not None else None
        insult_probability = db.get_insult_probability(scope_for_settings)
        insult_level = db.get_insult_level(scope_for_settings)
        if insult_level <= 1:
            insult_probability = 0.0
        if "быдлик" in text and question_match is None and insult_probability > 0:
            boost = db.get_insult_boost_multiplier()
            insult_probability = min(1.0, insult_probability * boost)

        if insult_probability > 0 and random.random() < insult_probability:
            if message.content_type == "photo":
                prompt = "фото"
            elif message.content_type == "video":
                prompt = "видео"
            else:
                prompt = text

            history_queue = chat_history.get(chat_id)
            history_lines = [f"{name}: {content}" for name, content in list(history_queue or [])]
            answer = llm.generate_insult(prompt, insult_level, history_lines)
            if answer is None:
                answer = random.choice(INSULT_FALLBACKS)
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, answer)

        handle_question_templates(
            bot,
            message,
            text,
            chat_id,
            db,
            templates=question_templates,
            match=question_match,
        )

        if "быдлик не тегай меня" in text:
            tag_status = db.get_tag_status(user_id, chat_id)
            if tag_status:
                db.set_tag_status(user_id, chat_id, False)
                reply_with_typing(
                    bot,
                    message,
                    'Готово\nЕсли захочешь, чтобы я снова тебя тегал, просто напиши мне "Быдлик тегай меня"',
                )
            else:
                reply_with_typing(bot, message, "Ты уже просил, я тебя не тегаю")

        if "быдлик тегай меня" in text:
            tag_status = db.get_tag_status(user_id, chat_id)
            if not tag_status:
                db.set_tag_status(user_id, chat_id, True)
                reply_with_typing(
                    bot,
                    message,
                    'Готово\nЕсли захочешь, чтобы я перестал тебя тегать, просто напиши мне "Быдлик не тегай меня"',
                )
            else:
                reply_with_typing(bot, message, "Я тебя и так тегаю")

        if "быдлик насколько" in text:
            que_s = text.split("насколько", 1)
            que = que_s[1]
            seed = generate_seed(que, user_id)
            random.seed(int(seed))
            result = str(random.randrange(1, 100) + 1)
            reply_with_typing(bot, message, "На" + " " + result + "%")

        if "быдлик когда" in text:
            list_choice = random.choice(WHEN_RESPONSES)
            if list_choice is TIME_UNIT_OPTIONS:
                date_choice = random.choice(TIME_UNIT_OPTIONS)
                numbers = random.randrange(1, 100)
                result = when(date_choice, numbers)
            else:
                result = random.choice(FLEXIBLE_TIME_RESPONSES)
            reply_with_typing(bot, message, result)

        if "быдлик сколько" in text:
            que_s = text.split("сколько", 1)
            que = que_s[1]
            seed = generate_seed(que, user_id)
            random.seed(int(seed))
            if random.randint(1, 2) == 1:
                seed = generate_seed(que, user_id)
                random.seed(int(seed))
                result = str(random.randrange(1, 100) + 1)
            else:
                result = random.choice(QUANTITY_RESPONSES)
            reply_with_typing(bot, message, result)

        if "быдлик " in text and " или " in text:
            que_s = text.split("быдлик", 1)[1].split(" или ")
            if not que_s[0].strip():
                que_s = que_s[1:]
            result = random.choice(que_s)
            reply_with_typing(bot, message, result)


def _handle_admin_commands(
    bot: TeleBot,
    message,
    text: str,
    raw_text: str,
    user_id: int,
    chat_id: int,
    db: Database,
    admin_service: AdminService,
) -> bool:
    chat_type = getattr(message.chat, "type", "")
    is_private_chat = chat_type == "private"
    has_chat_admin_rights = admin_service.is_chat_admin(user_id, chat_id) if not is_private_chat else False
    is_global_admin = admin_service.is_admin(user_id)

    if text.startswith("быдлик добавь вопрос"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут добавлять вопросы")
            return True

        payload = _extract_payload(raw_text, "быдлик добавь вопрос")
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) != 2 or not all(parts):
            reply_with_typing(
                bot,
                message,
                "Формат: Быдлик добавь вопрос триггер|ответ (используй {mention} и {question})",
            )
            return True

        trigger_text, template_text = parts
        target_chat_id = GLOBAL_CHAT_ID if (is_private_chat and is_global_admin) else chat_id
        if is_private_chat and not is_global_admin:
            reply_with_typing(bot, message, "Глобальные шаблоны можно менять только глобальным администраторам")
            return True

        db.save_question_template(
            QuestionTemplate(
                trigger_text=trigger_text.lower(),
                response_template=template_text,
                chat_id=target_chat_id,
            )
        )
        scope = "глобально" if target_chat_id == GLOBAL_CHAT_ID else "для этого чата"
        reply_with_typing(bot, message, f"Шаблон сохранён {scope}")
        return True

    if text.startswith("быдлик шанс оскорбления"):
        if is_private_chat and not is_global_admin:
            reply_with_typing(bot, message, "Глобальный шанс оскорбления может менять только глобальный администратор")
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут обновлять шанс оскорбления в чате")
            return True

        payload = _extract_payload(raw_text, "быдлик шанс оскорбления")
        try:
            value = float(payload.replace("%", "").strip())
        except ValueError:
            reply_with_typing(bot, message, "Формат: Быдлик шанс оскорбления 5.5 (в процентах)")
            return True

        clamped_value = max(0.0, min(100.0, value))
        target_chat_id = None if is_private_chat else chat_id
        db.set_insult_probability(clamped_value / 100, target_chat_id)
        if target_chat_id is None:
            reply_with_typing(bot, message, f"Глобальный шанс оскорбления обновлён до {clamped_value:.2f}%")
        else:
            reply_with_typing(bot, message, f"Шанс оскорбления в этом чате обновлён до {clamped_value:.2f}%")
        return True

    if text.startswith("быдлик уровень оскорблений"):
        if is_private_chat and not is_global_admin:
            reply_with_typing(bot, message, "Глобальный уровень оскорблений может менять только глобальный администратор")
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администратор чата может менять уровень оскорблений")
            return True

        payload = _extract_payload(raw_text, "быдлик уровень оскорблений")
        try:
            level = int(payload.split()[0])
        except (ValueError, IndexError):
            reply_with_typing(bot, message, "Формат: Быдлик уровень оскорблений N (1-4)")
            return True

        if level < 1 or level > 4:
            reply_with_typing(bot, message, "Допустимые значения: 1, 2, 3 или 4")
            return True

        target_chat_id = None if is_private_chat else chat_id
        db.set_insult_level(level, target_chat_id)
        if target_chat_id is None:
            reply_with_typing(bot, message, f"Глобальный уровень оскорблений установлен на {level}")
        else:
            reply_with_typing(bot, message, f"Уровень оскорблений в этом чате установлен на {level}")
        return True

    if text.startswith("быдлик множитель оскорбления"):
        if not admin_service.is_admin(user_id):
            reply_with_typing(bot, message, "Только администраторы могут обновлять множитель")
            return True

        payload = text.split("быдлик множитель оскорбления", 1)[1].strip()
        try:
            value = float(payload.strip())
        except ValueError:
            reply_with_typing(bot, message, "Формат: Быдлик множитель оскорбления 2 (минимум 1)")
            return True

        clamped_value = max(1.0, value)
        db.set_insult_boost_multiplier(clamped_value)
        reply_with_typing(bot, message, f"Множитель оскорбления обновлён до {clamped_value:.2f}")
        return True

    if text.startswith("быдлик команды"):
        reply_with_typing(bot, message, _build_help_message(db, chat_id if not is_private_chat else None))
        return True

    if text.startswith("быдлик админские команды"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут смотреть админскую справку")
            return True
        reply_with_typing(bot, message, _build_admin_help_message())
        return True
    if text.startswith("быдлик покажи юзеров"):
        if is_private_chat:
            reply_with_typing(bot, message, "Список пользователей доступен только внутри чата")
            return True
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут просматривать список пользователей")
            return True

        chat_users = db.get_chat_users(chat_id)
        if not chat_users:
            reply_with_typing(bot, message, "Нет данных о пользователях этого чата")
            return True

        lines = ["Пользователи и статус тегов:"]
        for user in chat_users:
            status = "тегаю" if user.tag else "не тегаю"
            display_name = user.username or str(user.id)
            lines.append(f"{display_name} — {status}")
        reply_with_typing(bot, message, "\n".join(lines))
        return True
    if text.startswith("быдлик тегай") or text.startswith("быдлик не тегай"):
        if is_private_chat:
            reply_with_typing(bot, message, "Настройки тегов доступны только в чате")
            return True
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администратор чата может менять теги других пользователей")
            return True

        if text.startswith("быдлик тегай"):
            should_tag = True
            command_prefix = "быдлик тегай"
        else:
            should_tag = False
            command_prefix = "быдлик не тегай"

        target_user_id, _ = _extract_target_info(message, raw_text, command_prefix, db)
        if target_user_id is None:
            reply_with_typing(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение после команды 'тегай' или 'не тегай'",
            )
            return True

        db.set_tag_status(target_user_id, chat_id, should_tag)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        status_text = "теперь тегается" if should_tag else "теперь без тегов"
        reply_with_typing(bot, message, f"{target_name} {status_text}")
        return True

    if text.startswith("быдлик сделай админом"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут назначать админов")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик сделай админом", db)
        if target_user_id is None:
            reply_with_typing(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик сделай админом 123",
            )
            return True

        admin_service.add_chat_admin(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_with_typing(bot, message, f"{target_name} теперь администратор этого чата")
        return True

    if text.startswith("быдлик убери админа"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Только администраторы могут снимать админов")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик убери админа", db)
        if target_user_id is None:
            reply_with_typing(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик убери админа 123",
            )
            return True

        admin_service.remove_chat_admin(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_with_typing(bot, message, f"{target_name} больше не администратор этого чата")
        return True

    if text.startswith("быдлик бан"):
        if is_private_chat or not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Банить можно только в чате и только администраторам")
            return True

        target_user_id, remainder = _extract_target_info(message, raw_text, "быдлик бан", db)
        if target_user_id is None:
            reply_with_typing(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик бан 123 10м",
            )
            return True

        remainder = remainder.lstrip()
        if remainder.lower().startswith("на "):
            remainder = remainder[3:].strip()
        banned_until, duration_error = _parse_duration_to_datetime(remainder)
        if duration_error:
            reply_with_typing(bot, message, duration_error)
            return True

        admin_service.ban_user(target_user_id, chat_id, banned_until)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        if banned_until:
            reply_with_typing(
                bot,
                message,
                f"{target_name} забанен до {banned_until.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            )
        else:
            reply_with_typing(bot, message, f"{target_name} забанен без срока")
        return True

    if text.startswith("быдлик разбан"):
        if is_private_chat or not (is_global_admin or has_chat_admin_rights):
            reply_with_typing(bot, message, "Разбанить можно только в чате и только администраторам")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик разбан", db)
        if target_user_id is None:
            reply_with_typing(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик разбан 123",
            )
            return True

        admin_service.unban_user(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_with_typing(bot, message, f"{target_name} разбанен")
        return True

    return False


def _extract_payload(raw_text: str, command_prefix: str) -> str:
    lower_text = raw_text.lower()
    start_index = lower_text.find(command_prefix)
    if start_index == -1:
        return ""
    return raw_text[start_index + len(command_prefix) :].strip()


def _extract_target_info(
    message, raw_text: str, command_prefix: str, db: Database
) -> Tuple[Optional[int], str]:
    payload = _extract_payload(raw_text, command_prefix)
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, payload
    if not payload:
        return None, ""

    if payload.startswith("@"):
        token = payload.split()[0]
        username = token[1:]
        user = db.get_user_by_username(username)
        remainder = payload[len(token) :].strip()
        return (user.id if user else None), remainder

    token = payload.split()[0]
    try:
        target_id = int(token)
        remainder = payload[len(token) :].strip()
        return target_id, remainder
    except ValueError:
        return None, payload


def _format_target_name(user: Optional[UserRecord], fallback_id: int) -> str:
    if user and user.username:
        return f"@{user.username}"
    return str(fallback_id)


def _parse_duration_to_datetime(value: str) -> Tuple[Optional[datetime], Optional[str]]:
    if not value:
        return None, None
    token = value.split()[0]
    match = re.match(r"^(\d+)\s*([a-zа-я]+)?$", token)
    if not match:
        return None, "Используй формат: число + единица (с, м, ч, д)"

    amount = int(match.group(1))
    unit = (match.group(2) or "m").lower()
    unit_map = {
        "s": "seconds",
        "sec": "seconds",
        "сек": "seconds",
        "с": "seconds",
        "m": "minutes",
        "min": "minutes",
        "мин": "minutes",
        "м": "minutes",
        "h": "hours",
        "hour": "hours",
        "час": "hours",
        "ч": "hours",
        "d": "days",
        "day": "days",
        "д": "days",
    }
    duration_key = unit_map.get(unit)
    if duration_key is None:
        return None, "Неизвестная единица времени. Используй с, м, ч или д"

    delta = timedelta(**{duration_key: amount})
    return datetime.now(timezone.utc) + delta, None


def _describe_non_text_message(message) -> str:
    mapping = {
        "photo": "[фото]",
        "video": "[видео]",
        "audio": "[аудио]",
        "voice": "[голосовое]",
        "sticker": "[стикер]",
        "document": "[документ]",
    }
    return mapping.get(message.content_type, f"[{message.content_type}]")


def _ensure_chat_owner_admin(bot: TeleBot, chat_id: int, user_id: int, admin_service: AdminService) -> None:
    try:
        member = bot.get_chat_member(chat_id, user_id)
    except ApiTelegramException:
        return

    if getattr(member, "status", None) == "creator":
        admin_service.add_chat_admin(user_id, chat_id)


def _build_help_message(db: Database, chat_id: Optional[int]) -> str:
    commands = [
        "Быдлик когда/сколько/насколько/... — развлечения и рандомные ответы",
        "Быдлик тегай меня / Быдлик не тегай меня — управлять собственным тегом",
        "Быдлик команды — эта справка",
    ]
    triggers = db.get_question_triggers(chat_id if chat_id is not None else None)
    if triggers:
        commands.insert(1, f"{', '.join(triggers)} — вопросы из набора (выбор пользователя)")
    return "Доступные команды:\n" + "\n".join(commands)


def _build_admin_help_message() -> str:
    commands = [
        "Быдлик добавь вопрос триггер|ответ — добавить вопрос (локально в чате). Используй {mention} и {question}",
        "Быдлик шанс оскорбления X — шанс оскорбления % (глобально в личке, локально в чате)",
        "Быдлик уровень оскорблений 1-4 — изменить уровень оскорблений",
        "Быдлик множитель оскорбления X — глобальный множитель шанса",
        "Быдлик сделай админом @user / Быдлик убери админа @user",
        "Быдлик бан @user 10м / Быдлик разбан @user",
        "Быдлик покажи юзеров — список пользователей/тегов",
        "Быдлик тегай @user / Быдлик не тегай @user — изменить тег другого пользователя",
        "Быдлик админские команды — эта справка",
    ]
    return "Админские команды:\n" + "\n".join(commands)

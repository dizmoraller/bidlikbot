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
)
from app.utils import (
    generate_seed,
    handle_question_templates,
    reply_with_typing,
    when,
    find_question_match,
)


def register_handlers(bot: TeleBot, db: Database, llm: LLM, admin_service: AdminService) -> None:
    HISTORY_LIMIT = 20
    chat_history: DefaultDict[int, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
    try:
        bot_info = bot.get_me()
        bot_id = bot_info.id
        bot_username = bot_info.username
    except Exception:
        bot_id = None
        bot_username = None

    @bot.message_handler(content_types=["text", "photo", "video"])
    def handle_message(message):
        user_id = message.from_user.id
        username = message.from_user.username
        display_name = _format_display_name(message.from_user)
        chat_id = message.chat.id
        raw_text = (message.text or message.caption or "") or ""
        text = raw_text.lower()
        db.ensure_user(user_id, username, chat_id)

        if admin_service.is_banned(user_id, chat_id):
            return

        _ensure_chat_owner_admin(bot, chat_id, user_id, admin_service)

        history_content = raw_text.strip() or _describe_non_text_message(message)
        history_queue = chat_history.get(chat_id)
        if history_queue is None:
            history_queue = chat_history.setdefault(chat_id, deque(maxlen=HISTORY_LIMIT))
        user_history_committed = False

        def commit_user_history() -> None:
            nonlocal user_history_committed
            if user_history_committed or not history_content or history_queue is None:
                return
            history_queue.append((display_name, history_content))
            user_history_committed = True

        def log_bot_history(text: str) -> None:
            if not text or history_queue is None:
                return
            history_queue.append(("Быдлик", text))

        def send_reply(bot: TeleBot, message, text: str) -> None:
            commit_user_history()
            reply_with_typing(bot, message, text)
            log_bot_history(text)

        if _handle_admin_commands(
            bot,
            message,
            text,
            raw_text,
            user_id,
            chat_id,
            db,
            admin_service,
            llm,
            send_reply,
        ):
            commit_user_history()
            return

        template_scope = None if getattr(message.chat, "type", "") == "private" else chat_id
        question_templates = db.get_question_templates(template_scope)
        question_match = find_question_match(text, question_templates)

        scope_for_settings = chat_id if template_scope is not None else None
        insult_probability = db.get_insult_probability(scope_for_settings)
        insult_level = db.get_insult_level(scope_for_settings)
        question_phrase_chance = db.get_question_phrase_chance(scope_for_settings)
        when_phrase_chance = db.get_when_phrase_chance(scope_for_settings)
        if insult_level <= 1:
            insult_probability = 0.0
        boost_on_reply = _is_reply_to_bot(message, bot_id, bot_username)
        if (("быдлик" in text and question_match is None) or boost_on_reply) and insult_probability > 0:
            boost = db.get_insult_boost_multiplier(scope_for_settings)
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
            answer = llm.generate_insult(display_name, prompt, insult_level, history_lines)
            if answer is None:
                answer = random.choice(INSULT_FALLBACKS)
            commit_user_history()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, answer)
            log_bot_history(answer)

        handle_question_templates(
            bot,
            message,
            text,
            chat_id,
            db,
            user_id=user_id,
            templates=question_templates,
            match=question_match,
            phrase_chance=question_phrase_chance,
            reply_func=send_reply,
        )

        if "быдлик не тегай меня" in text:
            tag_status = db.get_tag_status(user_id, chat_id)
            if tag_status:
                db.set_tag_status(user_id, chat_id, False)
                send_reply(
                    bot,
                    message,
                    'Готово\nЕсли захочешь, чтобы я снова тебя тегал, просто напиши мне "Быдлик тегай меня"',
                )
            else:
                send_reply(bot, message, "Ты уже просил, я тебя не тегаю")

        if "быдлик тегай меня" in text:
            tag_status = db.get_tag_status(user_id, chat_id)
            if not tag_status:
                db.set_tag_status(user_id, chat_id, True)
                send_reply(
                    bot,
                    message,
                    'Готово\nЕсли захочешь, чтобы я перестал тебя тегать, просто напиши мне "Быдлик не тегай меня"',
                )
            else:
                send_reply(bot, message, "Я тебя и так тегаю")

        if "быдлик насколько" in text:
            que_s = text.split("насколько", 1)
            que = que_s[1]
            seed = generate_seed(que, user_id)
            random.seed(int(seed))
            result = str(random.randrange(1, 100) + 1)
            send_reply(bot, message, "На" + " " + result + "%")

        if "быдлик когда" in text:
            if random.random() < when_phrase_chance:
                result = random.choice(FLEXIBLE_TIME_RESPONSES)
            else:
                date_choice = random.choice(TIME_UNIT_OPTIONS)
                numbers = random.randrange(1, 100)
                result = when(date_choice, numbers)
            send_reply(bot, message, result)

        if "быдлик " in text and " или " in text:
            que_s = text.split("быдлик", 1)[1].split(" или ")
            if not que_s[0].strip():
                que_s = que_s[1:]
            result = random.choice(que_s)
            send_reply(bot, message, result)

        commit_user_history()


def _handle_admin_commands(
    bot: TeleBot,
    message,
    text: str,
    raw_text: str,
    user_id: int,
    chat_id: int,
    db: Database,
    admin_service: AdminService,
    llm: Optional[LLM] = None,
    reply_func=reply_with_typing,
) -> bool:
    chat_type = getattr(message.chat, "type", "")
    is_private_chat = chat_type == "private"
    has_chat_admin_rights = admin_service.is_chat_admin(user_id, chat_id) if not is_private_chat else False
    is_global_admin = admin_service.is_admin(user_id)

    if text.startswith("быдлик добавь вопрос"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут добавлять вопросы")
            return True

        payload = _extract_payload(raw_text, "быдлик добавь вопрос")
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) != 2 or not all(parts):
            reply_func(
                bot,
                message,
                "Формат: Быдлик добавь вопрос триггер|ответ (используй {mention}, {question}, {number}, {percent})",
            )
            return True

        trigger_text, template_text = parts
        target_chat_id = GLOBAL_CHAT_ID if (is_private_chat and is_global_admin) else chat_id
        if is_private_chat and not is_global_admin:
            reply_func(bot, message, "Глобальные шаблоны можно менять только глобальным администраторам")
            return True
        existing_triggers = db.get_question_triggers(None if target_chat_id == GLOBAL_CHAT_ID else target_chat_id)
        if trigger_text.lower() in existing_triggers:
            reply_func(bot, message, "Такой вопрос уже существует")
            return True

        db.save_question_template(
            QuestionTemplate(
                trigger_text=trigger_text.lower(),
                response_template=template_text,
                chat_id=target_chat_id,
            )
        )
        scope = "глобально" if target_chat_id == GLOBAL_CHAT_ID else "для этого чата"
        reply_func(bot, message, f"Шаблон сохранён {scope}")
        return True

    if text.startswith("быдлик удали вопрос"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут удалять вопросы")
            return True

        payload = _extract_payload(raw_text, "быдлик удали вопрос")
        trigger_text = payload.strip()
        if not trigger_text:
            reply_func(bot, message, "Формат: Быдлик удали вопрос <текст вопроса>")
            return True

        target_chat_id = GLOBAL_CHAT_ID if (is_private_chat and is_global_admin) else chat_id
        if is_private_chat and not is_global_admin:
            reply_func(bot, message, "Глобальные шаблоны можно менять только глобальным администраторам")
            return True

        deleted = db.delete_question_template(target_chat_id, trigger_text.lower())
        if not deleted:
            reply_func(bot, message, "Такого вопроса нет")
            return True

        scope = "глобально" if target_chat_id == GLOBAL_CHAT_ID else "для этого чата"
        reply_func(bot, message, f"Вопрос удалён {scope}")
        return True

    if text.startswith("быдлик шанс оскорбления"):
        if is_private_chat and not is_global_admin:
            reply_func(bot, message, "Глобальный шанс оскорбления может менять только глобальный администратор")
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут обновлять шанс оскорбления в чате")
            return True

        payload = _extract_payload(raw_text, "быдлик шанс оскорбления")
        try:
            value = float(payload.replace("%", "").strip())
        except ValueError:
            reply_func(bot, message, "Формат: Быдлик шанс оскорбления 5.5 (в процентах)")
            return True

        clamped_value = max(0.0, min(100.0, value))
        target_chat_id = None if is_private_chat else chat_id
        db.set_insult_probability(clamped_value / 100, target_chat_id)
        if target_chat_id is None:
            reply_func(bot, message, f"Глобальный шанс оскорбления обновлён до {clamped_value:.2f}%")
        else:
            reply_func(bot, message, f"Шанс оскорбления в этом чате обновлён до {clamped_value:.2f}%")
        return True

    if text.startswith("быдлик уровень оскорблений"):
        if is_private_chat and not is_global_admin:
            reply_func(bot, message, "Глобальный уровень оскорблений может менять только глобальный администратор")
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администратор чата может менять уровень оскорблений")
            return True

        payload = _extract_payload(raw_text, "быдлик уровень оскорблений")
        try:
            level = int(payload.split()[0])
        except (ValueError, IndexError):
            reply_func(bot, message, "Формат: Быдлик уровень оскорблений N (1-4)")
            return True

        if level < 1 or level > 4:
            reply_func(bot, message, "Допустимые значения: 1, 2, 3 или 4")
            return True

        target_chat_id = None if is_private_chat else chat_id
        db.set_insult_level(level, target_chat_id)
        if target_chat_id is None:
            reply_func(bot, message, f"Глобальный уровень оскорблений установлен на {level}")
        else:
            reply_func(bot, message, f"Уровень оскорблений в этом чате установлен на {level}")
        return True

    if text.startswith("быдлик множитель оскорбления"):
        if is_private_chat and not is_global_admin:
            reply_func(bot, message, "Глобальный множитель оскорбления может менять только глобальный администратор")
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администратор чата может менять множитель в этом чате")
            return True

        payload = _extract_payload(raw_text, "быдлик множитель оскорбления")
        try:
            value = float(payload.strip())
        except ValueError:
            reply_func(bot, message, "Формат: Быдлик множитель оскорбления 2 (минимум 1)")
            return True

        clamped_value = max(1.0, value)
        target_chat_id = None if is_private_chat else chat_id
        db.set_insult_boost_multiplier(clamped_value, target_chat_id)
        if target_chat_id is None:
            reply_func(bot, message, f"Глобальный множитель оскорбления обновлён до {clamped_value:.2f}")
        else:
            reply_func(bot, message, f"Множитель оскорбления в этом чате обновлён до {clamped_value:.2f}")
        return True

    if text.startswith("быдлик шанс фразы в числовых"):
        if is_private_chat and not is_global_admin:
            reply_func(
                bot,
                message,
                "Глобальный шанс фразы в числовых может менять только глобальный администратор",
            )
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут менять шанс фразы в числовых в чате")
            return True

        payload = _extract_payload(raw_text, "быдлик шанс фразы в числовых")
        try:
            value = float(payload.replace("%", "").strip())
        except ValueError:
            reply_func(bot, message, "Формат: Быдлик шанс фразы в числовых 50 (в процентах)")
            return True

        clamped_value = max(0.0, min(100.0, value))
        target_chat_id = None if is_private_chat else chat_id
        db.set_question_phrase_chance(clamped_value / 100, target_chat_id)
        if target_chat_id is None:
            reply_func(bot, message, f"Глобальный шанс фразы в числовых обновлён до {clamped_value:.2f}%")
        else:
            reply_func(bot, message, f"Шанс фразы в числовых в этом чате обновлён до {clamped_value:.2f}%")
        return True

    if text.startswith("быдлик шанс фразы в когда"):
        if is_private_chat and not is_global_admin:
            reply_func(
                bot,
                message,
                "Глобальный шанс фразы в когда может менять только глобальный администратор",
            )
            return True

        if not is_private_chat and not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут менять шанс фразы в когда в чате")
            return True

        payload = _extract_payload(raw_text, "быдлик шанс фразы в когда")
        try:
            value = float(payload.replace("%", "").strip())
        except ValueError:
            reply_func(bot, message, "Формат: Быдлик шанс фразы в когда 50 (в процентах)")
            return True

        clamped_value = max(0.0, min(100.0, value))
        target_chat_id = None if is_private_chat else chat_id
        db.set_when_phrase_chance(clamped_value / 100, target_chat_id)
        if target_chat_id is None:
            reply_func(bot, message, f"Глобальный шанс фразы в когда обновлён до {clamped_value:.2f}%")
        else:
            reply_func(bot, message, f"Шанс фразы в когда в этом чате обновлён до {clamped_value:.2f}%")
        return True

    if text.startswith("быдлик настройки"):
        target_chat_id = chat_id if not is_private_chat else None
        reply_func(bot, message, _build_settings_summary(db, target_chat_id))
        return True

    if text.startswith("быдлик команды"):
        reply_func(bot, message, _build_help_message(db, chat_id if not is_private_chat else None))
        return True

    if text.startswith("быдлик админские команды"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут смотреть админскую справку")
            return True
        reply_func(bot, message, _build_admin_help_message())
        return True
    if text.startswith("быдлик сколько запросов"):
        if not is_global_admin:
            reply_func(bot, message, "Только глобальный администратор может смотреть остаток запросов")
            return True
        if llm is None:
            reply_func(bot, message, "LLM не настроен")
            return True
        status = llm.get_tokens_status()
        if not status:
            reply_func(bot, message, "Не удалось получить остаток запросов")
            return True
        lines = [
            f"Токенов: {status['total']}",
            f"Остаток запросов: {status['total_remaining']}",
        ]
        reply_func(bot, message, "\n".join(lines))
        return True
    if text.startswith("быдлик покажи юзеров"):
        if is_private_chat:
            reply_func(bot, message, "Список пользователей доступен только внутри чата")
            return True
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут просматривать список пользователей")
            return True

        chat_users = db.get_chat_users(chat_id)
        chat_admin_ids = db.get_chat_admin_ids(chat_id)
        if not chat_users:
            reply_func(bot, message, "Нет данных о пользователях этого чата")
            return True

        lines = ["Пользователи и статус тегов:"]
        for user in chat_users:
            status = "тегаю" if user.tag else "не тегаю"
            display_name = user.username or str(user.id)
            labels = []
            if user.is_admin:
                labels.append("глоб. админ")
            if user.id in chat_admin_ids:
                labels.append("админ чата")
            extra = f" ({', '.join(labels)})" if labels else ""
            lines.append(f"{display_name} — {status}{extra}")
        reply_func(bot, message, "\n".join(lines))
        return True
    if text.startswith("быдлик тегай") or text.startswith("быдлик не тегай"):
        if is_private_chat:
            reply_func(bot, message, "Настройки тегов доступны только в чате")
            return True
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администратор чата может менять теги других пользователей")
            return True

        if text.startswith("быдлик тегай"):
            should_tag = True
            command_prefix = "быдлик тегай"
        else:
            should_tag = False
            command_prefix = "быдлик не тегай"

        target_user_id, _ = _extract_target_info(message, raw_text, command_prefix, db)
        if target_user_id is None:
            reply_func(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение после команды 'тегай' или 'не тегай'",
            )
            return True

        db.set_tag_status(target_user_id, chat_id, should_tag)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        status_text = "теперь тегается" if should_tag else "теперь без тегов"
        reply_func(bot, message, f"{target_name} {status_text}")
        return True

    if text.startswith("быдлик сделай админом"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут назначать админов")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик сделай админом", db)
        if target_user_id is None:
            reply_func(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик сделай админом 123",
            )
            return True

        admin_service.add_chat_admin(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_func(bot, message, f"{target_name} теперь администратор этого чата")
        return True

    if text.startswith("быдлик убери админа"):
        if not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Только администраторы могут снимать админов")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик убери админа", db)
        if target_user_id is None:
            reply_func(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик убери админа 123",
            )
            return True
        if admin_service.is_admin(target_user_id):
            reply_func(bot, message, "Глобального администратора нельзя снять с админки")
            return True

        admin_service.remove_chat_admin(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_func(bot, message, f"{target_name} больше не администратор этого чата")
        return True

    if text.startswith("быдлик бан"):
        if is_private_chat or not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Банить можно только в чате и только администраторам")
            return True

        target_user_id, remainder = _extract_target_info(message, raw_text, "быдлик бан", db)
        if target_user_id is None:
            reply_func(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик бан 123 10м",
            )
            return True
        if admin_service.is_admin(target_user_id) or admin_service.is_chat_admin(target_user_id, chat_id):
            reply_func(bot, message, "Нельзя забанить администратора")
            return True

        remainder = remainder.lstrip()
        if remainder.lower().startswith("на "):
            remainder = remainder[3:].strip()
        banned_until, duration_error = _parse_duration_to_datetime(remainder)
        if duration_error:
            reply_func(bot, message, duration_error)
            return True

        admin_service.ban_user(target_user_id, chat_id, banned_until)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        if banned_until:
            reply_func(
                bot,
                message,
                f"{target_name} забанен до {banned_until.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            )
        else:
            reply_func(bot, message, f"{target_name} забанен без срока")
        return True

    if text.startswith("быдлик разбан"):
        if is_private_chat or not (is_global_admin or has_chat_admin_rights):
            reply_func(bot, message, "Разбанить можно только в чате и только администраторам")
            return True

        target_user_id, _ = _extract_target_info(message, raw_text, "быдлик разбан", db)
        if target_user_id is None:
            reply_func(
                bot,
                message,
                "Укажи ID, @username или ответь на сообщение: Быдлик разбан 123",
            )
            return True

        admin_service.unban_user(target_user_id, chat_id)
        target_user = db.get_user(target_user_id, chat_id)
        target_name = _format_target_name(target_user, target_user_id)
        reply_func(bot, message, f"{target_name} разбанен")
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


def _is_reply_to_bot(message, bot_id: Optional[int], bot_username: Optional[str]) -> bool:
    reply = getattr(message, "reply_to_message", None)
    if not reply:
        return False
    reply_user = getattr(reply, "from_user", None)
    if not reply_user:
        return False
    reply_id = getattr(reply_user, "id", None)
    if bot_id is not None and reply_id == bot_id:
        return True
    reply_username = getattr(reply_user, "username", None)
    if bot_username and reply_username == bot_username:
        return True
    return bool(getattr(reply_user, "is_bot", False))


def _format_display_name(user) -> str:
    username = getattr(user, "username", None) or ""
    first_name = getattr(user, "first_name", None) or ""
    last_name = getattr(user, "last_name", None) or ""
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()

    if username:
        return f"{username} ({full_name})" if full_name else username
    if full_name:
        return full_name
    return str(getattr(user, "id", "unknown"))


def _build_help_message(db: Database, chat_id: Optional[int]) -> str:
    commands = [
        "Быдлик когда/сколько/насколько/... — развлечения и рандомные ответы",
        "Быдлик тегай меня / Быдлик не тегай меня — управлять собственным тегом",
        "Быдлик настройки — текущее состояние оскорблений",
        "Быдлик команды — эта справка",
    ]
    triggers = db.get_question_triggers(chat_id if chat_id is not None else None)
    if triggers:
        commands.insert(1, f"{', '.join(triggers)} — вопросы из набора (выбор пользователя)")
    return "Доступные команды:\n" + "\n".join(commands)


def _build_settings_summary(db: Database, chat_id: Optional[int]) -> str:
    def format_percent(value: float) -> str:
        return f"{value * 100:.2f}%"

    lines = [
        "Глобальные настройки:",
        f"- Шанс оскорбления: {format_percent(db.get_insult_probability())}",
        f"- Уровень оскорблений: {db.get_insult_level()}",
        f"- Множитель шанса: {db.get_insult_boost_multiplier():.2f}",
        f"- Шанс фразы в числовых: {format_percent(db.get_question_phrase_chance())}",
        f"- Шанс фразы в когда: {format_percent(db.get_when_phrase_chance())}",
    ]

    if chat_id is not None:
        chat_probability = db.get_insult_probability(chat_id)
        chat_level = db.get_insult_level(chat_id)
        chat_multiplier = db.get_insult_boost_multiplier(chat_id)
        override_probability, override_level, override_multiplier = db.get_chat_insult_overrides(chat_id)
        chat_phrase_chance = db.get_question_phrase_chance(chat_id)
        override_phrase_chance = db.get_chat_question_phrase_override(chat_id)
        chat_when_phrase_chance = db.get_when_phrase_chance(chat_id)
        override_when_phrase_chance = db.get_chat_when_phrase_override(chat_id)
        chat_lines = [
            "",
            "Настройки этого чата:",
            f"- Шанс оскорбления: {format_percent(chat_probability)} "
            + ("(локально)" if override_probability is not None else "(глобально)"),
            f"- Уровень оскорблений: {chat_level} "
            + ("(локально)" if override_level is not None else "(глобально)"),
            f"- Множитель шанса: {chat_multiplier:.2f} "
            + ("(локально)" if override_multiplier is not None else "(глобально)"),
            f"- Шанс фразы в числовых: {format_percent(chat_phrase_chance)} "
            + ("(локально)" if override_phrase_chance is not None else "(глобально)"),
            f"- Шанс фразы в когда: {format_percent(chat_when_phrase_chance)} "
            + ("(локально)" if override_when_phrase_chance is not None else "(глобально)"),
        ]
        lines.extend(chat_lines)

    return "\n".join(lines)


def _build_admin_help_message() -> str:
    commands = [
        "Быдлик добавь вопрос триггер|ответ — добавить вопрос (локально в чате). Используй {mention}, {question}, {number}, {percent}",
        "Быдлик удали вопрос <текст> — удалить вопрос (локально в чате)",
        "Быдлик шанс оскорбления X — шанс оскорбления % (глобально в личке, локально в чате)",
        "Быдлик уровень оскорблений 1-4 — изменить уровень оскорблений",
        "Быдлик множитель оскорбления X — множитель шанса (глобально в личке, локально в чате)",
        "Быдлик шанс фразы в числовых X — шанс фразы вместо числа (глобально в личке, локально в чате)",
        "Быдлик шанс фразы в когда X — шанс фразы вместо даты (глобально в личке, локально в чате)",
        "Быдлик сколько запросов — остаток запросов к LLM",
        "Быдлик сделай админом @user / Быдлик убери админа @user",
        "Быдлик бан @user 10м / Быдлик разбан @user",
        "Быдлик покажи юзеров — список пользователей/тегов",
        "Быдлик тегай @user / Быдлик не тегай @user — изменить тег другого пользователя",
        "Быдлик админские команды — эта справка",
    ]
    return "Админские команды:\n" + "\n".join(commands)

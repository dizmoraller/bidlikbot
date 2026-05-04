import random
import re
import threading
import time

from datetime import date
from typing import Union

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException

from app.db import Database, QuestionTemplate, UserRecord
from app.texts import QUANTITY_RESPONSES

# Minimum interval (seconds) between send_chat_action calls per chat
_CHAT_ACTION_THROTTLE_SECONDS = 5
# Per-chat timestamp of last successful send_chat_action
_last_chat_action: dict[int, float] = {}


def when(date_choice, numbers):
    if numbers % 10 == 1 and numbers != 11:
        result = "Через" + " " + str(numbers) + " " + date_choice[0]
    elif 1 < numbers % 10 < 5 and (numbers % 100 < 10 or numbers % 100 >= 20):
        result = "Через" + " " + str(numbers) + " " + date_choice[1]
    else:
        result = "Через" + " " + str(numbers) + " " + date_choice[2]
    return result


def generate_seed(que, user_id):
    uni_que = ""
    for i in range(len(que)):
        uni_que += str(ord(que[i]))
    current_date = str(date.today())
    res_date = current_date.replace("-", "")
    text_user_id = str(user_id)
    seed = res_date + text_user_id + uni_que
    return seed


def select_user(db: Database, chat_id: int) -> Union[UserRecord, str]:
    members = db.get_tagged_users(chat_id)
    weighted_members: list[Union[UserRecord, str]] = []
    for member in members:
        weighted_members.extend([member, member])
    weighted_members.append("bot")
    return random.choice(weighted_members)


def _send_chat_action_safe(bot: TeleBot, chat_id: int) -> None:
    """Send typing action with throttle and error handling."""
    now = time.monotonic()
    last = _last_chat_action.get(chat_id, 0)
    if now - last < _CHAT_ACTION_THROTTLE_SECONDS:
        return
    try:
        bot.send_chat_action(chat_id, "typing")
        _last_chat_action[chat_id] = now
    except ApiTelegramException:
        # 429 Too Many Requests or other API errors — silently ignore
        pass


def reply_with_typing(bot: TeleBot, message, text: str) -> None:
    _send_chat_action_safe(bot, message.chat.id)
    time.sleep(random.randint(2, 7))
    bot.reply_to(message, text)


def handle_question_templates(
    bot: TeleBot,
    message,
    text: str,
    chat_id: int,
    db: Database,
    user_id: int | None = None,
    templates: list[QuestionTemplate] | None = None,
    match: tuple[QuestionTemplate, str] | None = None,
    phrase_chance: float = 0.0,
    phrase_responses: list[str] | None = None,
    reply_func=reply_with_typing,
) -> bool:
    templates = templates or db.get_question_templates()
    match = match or find_question_match(text, templates)
    if not match:
        return False
    template, question_tail = match
    selected = select_user(db, chat_id)
    rng = None
    if user_id is not None and ("{number}" in template.response_template or "{percent}" in template.response_template):
        seed = generate_seed(question_tail, user_id)
        rng = random.Random(int(seed))

    response = format_question_response(
        selected,
        template.response_template,
        question_tail,
        phrase_chance=phrase_chance,
        phrase_responses=phrase_responses,
        rng=rng,
    )
    reply_func(bot, message, response)
    return True


def find_question_match(
    text: str, templates: list[QuestionTemplate]
) -> tuple[QuestionTemplate, str] | None:
    for template in templates:
        keyword = f"быдлик {template.trigger_text}"
        start_index = text.find(keyword)
        if start_index == -1:
            continue
        question_tail = text[start_index + len(keyword) :]
        return template, question_tail
    return None


def format_question_response(
    selected: Union[UserRecord, str],
    template: str,
    question_tail: str,
    phrase_chance: float = 0.0,
    phrase_responses: list[str] | None = None,
    rng: random.Random | None = None,
) -> str:
    mention = "Быдлик"

    if selected != "bot":
        mention = selected.username or ""
        if mention and selected.tag:
            mention = f"@{mention}"

    normalized_question = question_tail.strip()
    if normalized_question:
        normalized_question = f" {normalized_question}"

    rng = rng or random
    number = rng.randint(1, 100)
    phrase_responses = phrase_responses or QUANTITY_RESPONSES
    use_phrase = (
        phrase_chance > 0
        and ("{number}" in template or "{percent}" in template)
        and rng.random() < phrase_chance
    )
    if use_phrase:
        phrase = rng.choice(phrase_responses)
        number_value = phrase
        percent_value = phrase
    else:
        number_value = number
        percent_value = f"{number}%"
    response = template.format(
        mention=mention,
        question=normalized_question,
        number=number_value,
        percent=percent_value,
    )
    return re.sub(r"[ ]{2,}", " ", response)

def reply_with_min_delay(bot, message, llm_func, min_seconds=2):
    target_delay = random.randint(min_seconds, min_seconds + 5)
    result = [None]

    def _run():
        result[0] = llm_func()

    thread = threading.Thread(target=_run)
    start = time.time()
    thread.start()

    while thread.is_alive() or (time.time() - start) < target_delay:
        _send_chat_action_safe(bot, message.chat.id)
        time.sleep(1)

    thread.join()
    return result[0]

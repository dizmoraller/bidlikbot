from typing import List, Optional

from openai import OpenAI

INSULT_PROMPTS = {
    2: (
        "Представь, что ты часть моего телеграм-бота. Ты должен отвечать короткими, озорными и мягкими подколами, "
        "которые слегка дразнят пользователя, но не переходят границы. Не используй мат или прямые оскорбления, "
        "просто подшути над ним. Вот несколько последних сообщений чата:\n{history}\n"
        "Текущее сообщение пользователя: {user_message}. Ответь только подколкой."
    ),
    3: (
        "Ты телеграм-бот Быдлик. Твоя задача — язвительные, жесткие ответы с сарказмом, но без матов. "
        "Используй контекст последних сообщений, если хочешь, но держи оскорбление в рамках приличия "
        "(никакой нецензурной лексики) Ты можешь допускать небольшие ошибки. Не используй знаки препинания или делай это по минимуму. Недавние сообщения чата:\n{history}\n"
        "Текущее сообщение пользователя: {user_message}. Дай только сам ответ."
    ),
    4: (
        "Ты часть моего телеграм бота. Тебя зовут Быдлик, не оскорбляй себя, если видишь в сообщении своё имя. "
        "Иногда (это определяется в самом коде) ты должен оскорблять пользователей. Учти последние сообщения:\n{history}\n"
        "Ты можешь использовать мат, допускать небольшие ошибки. Не используй знаки препинания или делай это по минимуму. Текущее сообщение пользователя: {user_message}. "
        "Важно, пиши только само оскорбление/обзывательство, без дополнительного текста."
    ),
}


class LLM:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def generate_insult(self, user_message: str, insult_level: int, history: List[str]) -> Optional[str]:
        prompt_template = INSULT_PROMPTS.get(insult_level)
        if not prompt_template:
            return None

        history_text = "\n".join(history[-10:]) if history else "нет данных"
        prompt = prompt_template.format(user_message=user_message, history=history_text)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
            return response.choices[0].message.content
        except Exception as exc:
            print(f"Ошибка: {exc}")
            return None

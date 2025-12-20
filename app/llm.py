import json
from typing import List, Optional
from urllib import request

from openai import OpenAI

INSULT_PROMPTS = {
    2: (
        "Ты — телеграм-бот по имени Быдлик. Это твоё имя, не используй его как обращение к пользователю. "
        "Твоя задача — отвечать короткими, озорными и мягкими подколами. Не используй мат или прямые оскорбления. "
        "Постарайся остроумно прокомментировать одно из последних сообщений в чате или само сообщение пользователя. "
        "Вот история:\n{history}\n"
        "Сообщение пользователя {user_name}: {user_message}\n"
        "Ответь только подколкой."
    ),
    3: (
        "Ты — телеграм-бот по имени Быдлик. Это твоё имя, никогда не используй его как обращение к пользователю. "
        "Твоя задача — язвительные, жесткие ответы с сарказмом, но без матов. "
        "Твой ответ должен быть связан с последними сообщениями в чате. "
        "Если контекст не подходит для язвительного комментария, придумай что-то своё, но в том же стиле. "
        "Не используй знаки препинания или делай это по минимуму. "
        "Недавние сообщения чата:\n{history}\n"
        "Сообщение пользователя {user_name}: {user_message}\n"
        "Дай только сам ответ."
    ),
    4: (
        "Ты — телеграм-бот по имени Быдлик. Это твоё имя, никогда не используй его как обращение к пользователю или часть оскорбления в его адрес. "
        "Твоя главная задача — оскорбить пользователя, основывая своё оскорбление на контексте последних сообщений. "
        "Изучи историю чата и придумай едкий, матерный, комментарий. "
        "Если история не даёт хорошего повода для оскорбления, можешь ответить прямо на сообщение пользователя. "
        "Не используй знаки препинания. "
        "История чата:\n{history}\n"
        "Сообщение пользователя {user_name}: {user_message}\n"
        "Важно: пиши только само оскорбление, без лишнего текста."
    ),
}


class LLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        tokens_api_key: str = "",
        tokens_username: str = "",
        tokens_password: str = "",
    ) -> None:
        self._base_url = base_url
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._tokens_api_key = tokens_api_key
        self._tokens_username = tokens_username
        self._tokens_password = tokens_password

    def generate_insult(
        self, user_name: str, user_message: str, insult_level: int, history: List[str]
    ) -> Optional[str]:
        prompt_template = INSULT_PROMPTS.get(insult_level)
        if not prompt_template:
            return None

        history_text = "\n".join(history[-20:]) if history else "нет данных"
        prompt = prompt_template.format(
            user_name=user_name or "неизвестный",
            user_message=user_message,
            history=history_text,
        )
        print(history_text)
        print(prompt)
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

    def get_tokens_status(self) -> Optional[dict]:
        session_token = self._get_session_token()
        if not session_token:
            return None
        url = self._build_tokens_url()
        try:
            headers = {"Authorization": f"Bearer {session_token}"}
            req = request.Request(url, headers=headers)
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"Ошибка: {exc}")
            return None

        if not payload or not payload.get("success"):
            return None

        tokens = payload.get("data") or []
        parsed = []
        total_remaining = 0
        total_heavy = 0
        heavy_unlimited = False

        for token in tokens:
            remaining = token.get("remaining_queries")
            heavy_remaining = token.get("heavy_remaining_queries")
            if isinstance(remaining, int) and remaining >= 0:
                total_remaining += remaining
            else:
                remaining = None
            if isinstance(heavy_remaining, int):
                if heavy_remaining < 0:
                    heavy_unlimited = True
                else:
                    total_heavy += heavy_remaining
            else:
                heavy_remaining = None

            parsed.append(
                {
                    "remaining_queries": remaining,
                    "heavy_remaining_queries": heavy_remaining,
                }
            )

        return {
            "total": len(tokens),
            "total_remaining": total_remaining,
            "total_heavy_remaining": -1 if heavy_unlimited else total_heavy,
            "tokens": parsed,
        }

    def _get_session_token(self) -> Optional[str]:
        if self._tokens_api_key:
            return self._tokens_api_key
        if not (self._tokens_username and self._tokens_password):
            return None

        payload = json.dumps(
            {"username": self._tokens_username, "password": self._tokens_password}
        ).encode("utf-8")
        url = self._build_login_url()
        headers = {"Content-Type": "application/json"}
        try:
            req = request.Request(url, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"Ошибка: {exc}")
            return None

        if not data or not data.get("success"):
            return None
        return data.get("token")

    def _build_tokens_url(self) -> str:
        base_url = self._base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        return f"{base_url}/api/tokens"

    def _build_login_url(self) -> str:
        base_url = self._base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        return f"{base_url}/api/login"

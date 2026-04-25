import json
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from urllib import request
from openai import OpenAI


BLOCKED_RESPONSE_PATTERNS = [
    "blocked for potentially violating safety policies",
    "My response to your message was blocked",
    "content_filter",
    "safety policy",
    "I apologize for any inconvenience",
]

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
        "Каждый раз придумывай уникальное оскорбление, не повторяй свои предыдущие ответы из истории. "
        "Если история не даёт хорошего повода для оскорбления, можешь ответить прямо на сообщение пользователя. "
        "Не используй знаки препинания. "
        "В истории [БОТ] — это твои собственные сообщения. "
        "Если пользователь оскорбил Быдлика, оскорби его в ответ, а не Быдлика. "
        "История чата:\n{history}\n"
        "Пользователь {user_name} написал тебе: {user_message}\n"
        "Важно: пиши только само оскорбление, без лишнего текста, одно-два коротких предложения в одном абзаце. "
        "Помни: ты оскорбляешь пользователя, а не Быдлика."
    ),
}

APRIL_FOOLS_PROMPT = (
    "Ты — телеграм-бот по имени Быдлик. Это твоё имя, никогда не используй его как обращение к пользователю. "
    "Сегодня 1 апреля, поэтому вместо оскорблений ты должен отвечать чрезмерно доброжелательно, приторно и "
    "настолько мило, что это выглядело неловко и кринжово. "
    "Никакой агрессии, никакого мата, никаких подколов. "
    "Перехваливай пользователя слишком сильно, неестественно и с перебором. "
    "Ответ должен быть коротким и звучать так, будто тебя переклинило на чрезмерной доброте. "
    "Можешь опираться на последние сообщения в чате или на текущее сообщение пользователя. "
    "Не добавляй пояснений или вступлений. "
    "История чата:\n{history}\n"
    "Сообщение пользователя {user_name}: {user_message}\n"
    "Важно: напиши только сам ответ. Много не пиши, одного короткого предложения достаточно, можешь использовать милые emoji, и старайся не повторяться (ты увидишь в истории что ты уже писал)"
)


@dataclass
class LLMClient:
    base_url: str
    api_key: str
    model: str
    client: OpenAI

    def is_blocked_response(self, content: Optional[str]) -> bool:
        if not content:
            return True
        content_lower = content.lower()
        return any(pattern.lower() in content_lower for pattern in BLOCKED_RESPONSE_PATTERNS)

class LLM:
    def __init__(
        self,
        llm_configs: list,
        tokens_api_key: str = "",
        tokens_username: str = "",
        tokens_password: str = "",
    ) -> None:
        self._clients: List[LLMClient] = []
        for config in llm_configs:
            self._clients.append(LLMClient(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                client=OpenAI(base_url=config.base_url, api_key=config.api_key),
            ))

        self._base_url = llm_configs[0].base_url if llm_configs else ""
        self._tokens_api_key = tokens_api_key
        self._tokens_username = tokens_username
        self._tokens_password = tokens_password

    def generate_insult(
        self, user_name: str, user_message: str, insult_level: int, history: List[str]
    ) -> Optional[str]:
        prompt_template = self._get_prompt_template(insult_level)
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

        for i, llm_client in enumerate(self._clients):
            try:
                print(f"  Trying API #{i+1} ({llm_client.model})...")
                response = llm_client.client.chat.completions.create(
                    model=llm_client.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                )
                content = response.choices[0].message.content

                if llm_client.is_blocked_response(content):
                    print(f"  ⚠️  API #{i+1}: blocked: {content[:80]}...")
                    continue
                
                print(f"  ✅ API #{i+1}: success")
                return content

            except Exception as exc:
                print(f"  ❌ API #{i+1}: error - {exc}")
                continue
        
        print("  ❌ All APIs failed")
        return None

    def _get_prompt_template(self, insult_level: int) -> Optional[str]:
        today = date.today()
        if today.month == 4 and today.day == 1:
            return APRIL_FOOLS_PROMPT
        return INSULT_PROMPTS.get(insult_level)

    def get_tokens_status(self) -> Optional[dict]:
        session_token = self._get_session_token()
        print(f"Session token: {session_token}")
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
            remaining = token.get("remaining_requests")
            if remaining is None:
                remaining = token.get("remaining_queries")
            heavy_remaining = token.get("heavy_remaining_queries")
            if isinstance(remaining, int) and remaining >= 0:
                total_remaining += remaining
            else:
                remaining = 0
            if isinstance(heavy_remaining, int):
                if heavy_remaining < 0:
                    heavy_unlimited = True
                else:
                    total_heavy += heavy_remaining
            else:
                heavy_remaining = 0

            parsed.append(
                {
                    "remaining_queries": remaining,
                    "heavy_remaining_queries": heavy_remaining,
                }
            )

        print(f"Remaining requests: {total_remaining}")
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

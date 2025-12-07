from openai import OpenAI
def request_grok(user_message):
    # Настраиваем клиент на локальный адрес
    client = OpenAI(
        base_url="http://host.containers.internal:8000/v1",
        api_key="unused"  # Заглушка, так как ключ проверяется внутри сервера через cookie
    )

    try:
        response = client.chat.completions.create(
            model="grok-3-fast",
            messages=[
                {"role": "user", "content": f"Ты часть моего телеграм бота. Тебя зовут Быдлик, не оскорбляй себя, если видишь в сообщении своё имя. Иногда(это определяется в самом коде) ты должен оскорблять пользователей, которые писали сообщения. Если это будет уместно, то ты можешь использовать контекст самого сообщения, но ты не обязан делать это всегда. Ты можешь использовать мат. Сообщение пользователя: {user_message}. Важно, пиши только само оскорбление/обзывательство, без дополнительного текста"}
            ],
            stream=False
        )

        # Клиент сам распаковывает JSON, обращаемся как к объекту
        content = response.choices[0].message.content

        return content

    except Exception as e:
        print(f"Ошибка: {e}")
        return None

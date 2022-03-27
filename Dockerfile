FROM python:alpine3.15

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "random_bot.py" ]


from re import split
from time import sleep
import telebot
import random
import psycopg2
from datetime import date
import os

DATABASE_URL = os.environ['DATABASE_URL']
TOKEN = os.environ['TOKEN']
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
db_cursor = conn.cursor()

bot = telebot.TeleBot(TOKEN)

days_list = ["день", "дня", "дней"]
mon_list = ["месяц", "месяца", "месяцев"]
years_list = ["год", "года", "лет"]
hours_list = ["час", "часа", "часов"]
min_list = ["минуту", "минуты", "минут"]
sec_list = ["секунду", "секунды", "секунд"]
first_list = ["Никогда", "Завтра", "Потом", "Когда-нибудь", "Сегодня", "Послезавтра", "Скоро", "Сейчас",
              "Скоро, но это не точно"]
second_list = [days_list, mon_list, years_list, hours_list, min_list, sec_list]
when_list = [first_list, second_list]
how_much_list = ["Много", "Нисколько", "Мало", "Очень много", "Жесть как мало", "Не мало"]

prikol_list = ["Не пиши сюда больше", "Ну и зачем ты это высрал?", "Чо случилось?", "Иди нахуй",
               "Ой, такая острая шутка! Я прям порезался!", "За такие шутки, в зубах бывают промежутки",
               "Заткнись", "От тебя говной воняет, даже по интернету чувствую", "Такой ты смешной(нет)",
               "Выйди с чата"]


def when(date_choice, numbers):
    if numbers % 10 == 1 and numbers != 11:
        result = "Через" + " " + str(numbers) + " " + date_choice[0]
    elif 1 < numbers % 10 < 5 and (numbers % 100 < 10 or numbers % 100 >= 20):
        result = "Через" + " " + str(numbers) + " " + date_choice[1]
    else:
        result = "Через" + " " + str(numbers) + " " + date_choice[2]
    return result


def generate_seed(que, id):
    uni_que = ""
    for i in range(len(que)):
        uni_que += str(ord(que[i]))
    current_date = str(date.today())
    res_date = current_date.replace("-", "")
    text_user_id = str(id)
    seed = res_date + text_user_id + uni_que
    return seed


@bot.message_handler(content_types=['text'])
def aboba(message):
    id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id
    text = message.text.lower()
    db_cursor.execute(f"SELECT id, chat_id FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
    db_result = db_cursor.fetchone()

    if not db_result:
        db_cursor.execute("INSERT INTO users.user(id, username, chat_id) VALUES (%s, %s, %s)", (id, username, chat_id))
        conn.commit()

    db_cursor.execute(f"SELECT username FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
    db_result = db_cursor.fetchone()
    if username != db_result:
        db_cursor.execute(f"UPDATE users.user SET username = {username} WHERE id = {id} AND chat_id = {chat_id}")

    if random.randint(1, 50) == 9:
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, random.choice(prikol_list))


    if "быдлик кто" in text:
        que_s = text.split("кто", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = select[1] + que
        if select[2]:
            result = "@" + result
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик кого" in text:
        que_s = text.split("кого", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = select[1] + "'а" + que
        if select[2]:
            result = "@" + result
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик у кого" in text:
        que_s = text.split("кого", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = "У " + select[1] + "'а" + que
        if select[2]:
            result = "У " + "@" + select[1] + "'а" + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик не тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
        db_result = db_cursor.fetchone()[0]
        if db_result:
            db_cursor.execute(f"UPDATE users.user SET tag = False WHERE id = {id} AND chat_id = {chat_id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message,
                         'Готово\nЕсли захочешь, чтобы я снова тебя тегал, просто напиши мне "Быдлик тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Ты уже просил, я тебя не тегаю')

    if "быдлик тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
        db_result = db_cursor.fetchone()[0]
        if not db_result:
            db_cursor.execute(f"UPDATE users.user SET tag = True WHERE id = {id} AND chat_id = {chat_id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message,
                         'Готово\nЕсли захочешь, чтобы я перестал тебя тегать, просто напиши мне "Быдлик не тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Я тебя и так тегаю')

    if "быдлик насколько" in text:
        que_s = text.split("насколько", 1)
        que = que_s[1]
        seed = generate_seed(que, id)
        random.seed(int(seed))
        result = str(random.randrange(1, 100) + 1)
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, "На" + " " + result + "%")

    if "быдлик когда" in text:
        list_choice = random.choice(when_list)
        if list_choice == second_list:
            date_choice = random.choice(second_list)
            numbers = random.randrange(1, 100)
            result = when(date_choice, numbers)
        elif list_choice == first_list:
            result = random.choice(first_list)
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик кому" in text:
        que_s = text.split("кому", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = select[1] + "'у" + que
        if select[2]:
            result = "@" + result
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик с кем" in text:
        que_s = text.split("кем", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = "С " + select[1] + "'ом" + que
        if select[2]:
            result = "С " + "@" + select[1] + "'ом" + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик в ком" in text:
        que_s = text.split("ком", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = "В " + select[1] + "'е" + que
        if select[2]:
            result = "В " + "@" + select[1] + "'е" + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик сколько" in text:
        que_s = text.split("сколько", 1)
        que = que_s[1]
        seed = generate_seed(que, id)
        random.seed(int(seed))
        if random.randint(1, 2) == 1:
            seed = generate_seed(que, id)
            random.seed(int(seed))
            result = str(random.randrange(1, 100) + 1)
        else:
            result = random.choice(how_much_list)
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик " and " или " in text:
        que_s = text.split("быдлик", 1)[1].split("или", 1)
        result = random.choice(que_s)
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)


bot.polling(none_stop=True)

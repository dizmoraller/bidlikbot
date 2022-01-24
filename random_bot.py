from re import split
from time import sleep
import telebot
import random
import psycopg2
from datetime import date
import os


DATABASE_URL = os.environ['DATABASE_URL']
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
db_cursor = conn.cursor()


bot = telebot.TeleBot("5011828394:AAHNPKq01NiqzYiXdA4NVgArJMGfkWHXZL4")


@bot.message_handler(content_types=['text'])
def aboba(message):
    id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id
    text = message.text.lower()
    members = []
    db_cursor.execute(f"SELECT id, chat_id FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
    db_result = db_cursor.fetchone()

    if not db_result:
        db_cursor.execute("INSERT INTO users.user(id, username, chat_id) VALUES (%s, %s, %s)", (id, username, chat_id))
        conn.commit()

    if "быдлик кто" in text:
        que_s = text.split("кто", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username, tag, chat_id FROM users.user WHERE chat_id = {chat_id}")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = select[1] + que
        if select[2] == True:
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
        result = "У " + select[1] + que
        if select[2] == True:
            result = "У " + "@" + select[1] + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик не тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
        db_result = db_cursor.fetchone()[0]
        if db_result == True:
            db_cursor.execute(f"UPDATE users.user SET tag = False WHERE id = {id} AND chat_id = {chat_id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Готово\nЕсли захочешь, чтобы я снова тебя тегал, просто напиши мне "Быдлик тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Ты уже просил, я тебя не тегаю')

    if "быдлик тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id} AND chat_id = {chat_id}")
        db_result = db_cursor.fetchone()[0]
        if db_result == False:
            db_cursor.execute(f"UPDATE users.user SET tag = True WHERE id = {id} AND chat_id = {chat_id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Готово\nЕсли захочешь, чтобы я перестал тебя тегать, просто напиши мне "Быдлик не тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Я тебя и так тегаю')   
            
    if "быдлик насколько я кринж" in text:
        current_date = str(date.today())
        res_date = current_date.replace("-", "")
        text_user_id = str(id)
        cringe_seed = res_date + text_user_id
        random.seed(int(cringe_seed))
        result = str(random.randrange(1, 100))
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, "Сегодня ты кринжовый на " + result + "%")   
    
    
    
    
bot.polling(none_stop=True) 

from re import split
from time import sleep
import telebot
import random
import psycopg2


conn = psycopg2.connect("postgres://sebpvdyzyozixc:b9fba55dfe23ccfaeb94b7e63799ae220f91af8032e80b1ae15abe348f01adc1@ec2-3-216-113-109.compute-1.amazonaws.com:5432/dc11rfbkcd0v46", sslmode='require')
db_cursor = conn.cursor()



bot = telebot.TeleBot("5011828394:AAHNPKq01NiqzYiXdA4NVgArJMGfkWHXZL4")


@bot.message_handler(content_types=['text'])
def aboba(message):
    id = message.from_user.id
    username = message.from_user.username
    text = message.text.lower()
    members = []
    db_cursor.execute(f"SELECT id FROM users.user WHERE id = {id}")
    db_result = db_cursor.fetchone()

    if not db_result:
        db_cursor.execute("INSERT INTO users.user(id, username) VALUES (%s, %s)", (id, username))
        conn.commit()

    if "быдлик кто" in text:
        que_s = text.split("кто", 1)
        que = que_s[1]
        db_cursor.execute(f"SELECT id, username,tag FROM users.user")
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
        db_cursor.execute(f"SELECT id, username,tag FROM users.user")
        members = db_cursor.fetchall()
        select = random.choice(members)
        result = "У " + select[1] + que
        if select[2] == True:
            result = "У " + "@" + select[1] + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(random.randint(2, 7))
        bot.reply_to(message, result)

    if "быдлик не тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id}")
        db_result = db_cursor.fetchone()[0]
        if db_result == True:
            db_cursor.execute(f"UPDATE users.user SET tag = False WHERE id = {id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Готово\nЕсли захочешь, чтобы я снова тебя тегал, просто напиши мне "Быдлик тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Ты уже просил, я тебя не тегаю')

    if "быдлик тегай меня" in text:
        db_cursor.execute(f"SELECT tag FROM users.user WHERE id = {id}")
        db_result = db_cursor.fetchone()[0]
        if db_result == False:
            db_cursor.execute(f"UPDATE users.user SET tag = True WHERE id = {id}")
            conn.commit()
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Готово\nЕсли захочешь, чтобы я перестал тебя тегать, просто напиши мне "Быдлик не тегай меня"')
        else:
            bot.send_chat_action(message.chat.id, "typing")
            sleep(random.randint(2, 7))
            bot.reply_to(message, 'Я тебя и так тегаю')   

            
    
    
    
    
    
    
bot.polling(none_stop=True) 

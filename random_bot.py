from re import split
from time import sleep
import telebot
import random


bot = telebot.TeleBot("5011828394:AAHNPKq01NiqzYiXdA4NVgArJMGfkWHXZL4")

@bot.message_handler(content_types=['text'])
def aboba(message):
    text = message.text.lower()
    members = ["@adelesow", "@dizmoraller", "@innerx", "@DrumYum", "@oh_danich", "@alexandernered69", "@theRealKockik", "@Teonatist", "@artemtes99", "@smirnowdenis"]
    if "быдлик кто" in text:
        que_s = text.split("кто", 1)
        que = que_s[1]
        result = random.choice(members) + que
        bot.send_chat_action(message.chat.id, "typing")
        sleep(5)
        bot.reply_to(message, result)

bot.polling(none_stop=True) 

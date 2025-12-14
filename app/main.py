from telebot import TeleBot

from app.admin import AdminService
from app.bot import register_handlers
from app.config import load_settings
from app.db import Database
from app.llm import LLM


def main():
    settings = load_settings()
    bot = TeleBot(settings.token)
    db = Database.init(settings.database_url)
    llm = LLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    admin_service = AdminService(db)

    try:
        register_handlers(bot, db, llm, admin_service)
        bot.polling(none_stop=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()

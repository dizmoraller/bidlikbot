import logging
import os

from telebot import TeleBot

from app.admin import AdminService
from app.bot import register_handlers
from app.config import load_settings
from app.db import Database
from app.llm import LLM

logger = logging.getLogger(__name__)

def main():
    settings = load_settings()
    db_dir = os.path.dirname(settings.database_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    bot = TeleBot(settings.token)
    db = Database.init(settings.database_path)
    llm = LLM(
        llm_configs=settings.llm_configs,
        image_config=settings.llm_image_config,
        tokens_username=settings.llm_tokens_username,
        tokens_password=settings.llm_tokens_password,
    )
    admin_service = AdminService(db)

    try:
        register_handlers(bot, db, llm, admin_service)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    finally:
        db.close()


if __name__ == "__main__":
    main()

import time
import logging

import requests.exceptions
from telebot import TeleBot

from app.admin import AdminService
from app.bot import register_handlers
from app.config import load_settings
from app.db import Database
from app.llm import LLM

logger = logging.getLogger(__name__)

# Max seconds to wait between polling retries
_MAX_BACKOFF_SECONDS = 300  # 5 minutes


def _polling_with_backoff(bot: TeleBot) -> None:
    """Run polling with automatic retry and exponential backoff on network errors."""
    backoff = 5  # initial backoff in seconds
    while True:
        try:
            logger.info("Starting polling…")
            bot.polling(
                none_stop=True,
                timeout=30,
                long_polling_timeout=30,
            )
            # polling exited normally (shouldn't happen with none_stop=True)
            break
        except requests.exceptions.ReadTimeout:
            logger.warning("Read timeout during polling, restarting in %ds…", backoff)
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error during polling, restarting in %ds…", backoff)
        except requests.exceptions.RequestException as exc:
            logger.warning("Request error during polling: %s, restarting in %ds…", exc, backoff)
        except Exception as exc:
            logger.error("Unexpected polling error: %s, restarting in %ds…", exc, backoff)

        time.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)


def main():
    settings = load_settings()
    bot = TeleBot(settings.token)
    db = Database.init(settings.database_url)
    llm = LLM(
        llm_configs=settings.llm_configs,
        tokens_username=settings.llm_tokens_username,
        tokens_password=settings.llm_tokens_password,
    )
    admin_service = AdminService(db)

    try:
        register_handlers(bot, db, llm, admin_service)
        _polling_with_backoff(bot)
    finally:
        db.close()


if __name__ == "__main__":
    main()

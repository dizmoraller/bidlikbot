import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Settings:
    token: str
    database_url: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_tokens_api_key: str
    llm_tokens_username: str
    llm_tokens_password: str


load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


def load_settings() -> Settings:
    return Settings(
        token=os.environ["TOKEN"],
        database_url=os.environ["DATABASE_URL"],
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", "unused"),
        llm_model=os.environ.get("LLM_MODEL", "grok-3-fast"),
        llm_tokens_api_key=os.environ.get("LLM_TOKENS_API_KEY", ""),
        llm_tokens_username=os.environ.get("LLM_TOKENS_USERNAME", ""),
        llm_tokens_password=os.environ.get("LLM_TOKENS_PASSWORD", ""),
    )

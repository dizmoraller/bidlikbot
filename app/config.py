import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str

@dataclass
class Settings:
    token: str
    database_url: str
    llm_configs: List[LLMConfig] = field(default_factory=list)
    llm_tokens_username: str = ""
    llm_tokens_password: str = ""


load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

def _load_llm_configs() -> List[LLMConfig]:
    configs = []
    
    index = 1
    while True:
        base_url = os.environ.get(f"LLM_BASE_URL_{index}")
        api_key = os.environ.get(f"LLM_API_KEY_{index}")
        model = os.environ.get(f"LLM_MODEL_{index}")
        
        if not base_url:
            break
            
        configs.append(LLMConfig(
            base_url=base_url,
            api_key=api_key or "unused",
            model=model or "grok-3-fast"
        ))
        index += 1
    
    if not configs:
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
        api_key = os.environ.get("LLM_API_KEY", "unused")
        model = os.environ.get("LLM_MODEL", "grok-3-fast")
        configs.append(LLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model
        ))
    
    return configs

def load_settings() -> Settings:
    return Settings(
        token=os.environ["TOKEN"],
        database_url=os.environ["DATABASE_URL"],
        llm_configs=_load_llm_configs(),
        llm_tokens_username=os.environ.get("LLM_TOKENS_USERNAME", ""),
        llm_tokens_password=os.environ.get("LLM_TOKENS_PASSWORD", ""),
    )

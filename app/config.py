import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    supports_images: bool = False

@dataclass
class Settings:
    token: str
    database_url: str
    llm_configs: List[LLMConfig] = field(default_factory=list)
    llm_image_config: Optional[LLMConfig] = None
    llm_tokens_username: str = ""
    llm_tokens_password: str = ""


load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

def _load_llm_configs() -> List[LLMConfig]:
    index_pattern = re.compile(r"^LLM_BASE_URL_(\d+)$")
    found_indices = []
    for key in os.environ:
        m = index_pattern.match(key)
        if m:
            found_indices.append(int(m.group(1)))

    configs = []
    for idx in sorted(found_indices):
        base_url = os.environ[f"LLM_BASE_URL_{idx}"]
        api_key = os.environ.get(f"LLM_API_KEY_{idx}")
        model = os.environ.get(f"LLM_MODEL_{idx}")
        supports_images = os.environ.get(f"LLM_SUPPORTS_IMAGES_{idx}", "false").lower() in ("true", "1", "yes")
        configs.append(LLMConfig(
            base_url=base_url,
            api_key=api_key or "unused",
            model=model or "grok-3-fast",
            supports_images=supports_images,
        ))

    if not configs:
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
        api_key = os.environ.get("LLM_API_KEY", "unused")
        model = os.environ.get("LLM_MODEL", "grok-3-fast")
        supports_images = os.environ.get("LLM_SUPPORTS_IMAGES", "false").lower() in ("true", "1", "yes")
        configs.append(LLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            supports_images=supports_images,
        ))

    return configs

def _load_image_llm_config() -> Optional[LLMConfig]:
    base_url = os.environ.get("LLM_IMAGE_BASE_URL")
    if not base_url:
        return None
    api_key = os.environ.get("LLM_IMAGE_API_KEY", "unused")
    model = os.environ.get("LLM_IMAGE_MODEL", "grok-3-fast")
    return LLMConfig(base_url=base_url, api_key=api_key, model=model, supports_images=True)

def load_settings() -> Settings:
    return Settings(
        token=os.environ["TOKEN"],
        database_url=os.environ["DATABASE_URL"],
        llm_configs=_load_llm_configs(),
        llm_image_config=_load_image_llm_config(),
        llm_tokens_username=os.environ.get("LLM_TOKENS_USERNAME", ""),
        llm_tokens_password=os.environ.get("LLM_TOKENS_PASSWORD", ""),
    )

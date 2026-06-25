from __future__ import annotations

import json
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    BOT_USERNAME: str = ""
    ADMIN_IDS: List[int] = []
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    DEFAULT_LANGUAGE: str = "fa"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [int(i) for i in parsed]
            except (json.JSONDecodeError, ValueError):
                return [int(i.strip()) for i in v.split(",") if i.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

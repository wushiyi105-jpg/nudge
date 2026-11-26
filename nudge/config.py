"""配置：全部有默认值，没有 .env 也能跑。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NUDGE_", extra="ignore")

    db_path: Path = Path("data/nudge.db")
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-flash"
    llm_timeout: float = 30.0
    llm_max_tokens: int = 1200
    webhook_url: str = ""
    currency: str = "CNY"
    # 催收档位阈值（天）
    stage2_days: int = 15
    stage3_days: int = 30
    # 重复催收的最小间隔（天）
    reminder_cooldown_days: int = 7

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()

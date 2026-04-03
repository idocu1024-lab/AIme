import os

from pydantic_settings import BaseSettings

# Use /data if it exists and is writable (Render persistent disk), else ./data
def _pick_data_dir() -> str:
    if os.environ.get("RENDER") == "true":
        try:
            os.makedirs("/data", exist_ok=True)
            # Test write permission
            test = "/data/.write_test"
            with open(test, "w") as f:
                f.write("ok")
            os.remove(test)
            return "/data"
        except (PermissionError, OSError):
            pass
    return "./data"

_DATA_DIR = _pick_data_dir()


class Settings(BaseSettings):
    app_name: str = "AI.me"
    debug: bool = False

    # Database — auto-uses /data on Render for persistent disk
    database_url: str = f"sqlite+aiosqlite:///{_DATA_DIR}/aime.db"

    # ChromaDB — auto-uses /data on Render for persistent disk
    chroma_persist_dir: str = f"{_DATA_DIR}/chroma"

    # LLM Provider: "openai" or "anthropic"
    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5-nano"
    openai_base_url: str = ""  # Leave empty for default, or set for proxy

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # LLM limits (reasoning models need higher budgets for internal reasoning)
    max_tokens_dialogue: int = 8000
    max_tokens_fusion: int = 8000
    max_tokens_social: int = 16000
    max_tokens_daily_log: int = 8000

    # Game
    daily_cycle_hour_utc: int = 0
    social_matching_hours_utc: str = "8,20"
    max_feed_length: int = 50000
    max_feeds_per_day: int = 10
    fusion_quant_weight: float = 0.4
    fusion_semantic_weight: float = 0.6

    # Admin
    admin_key: str = "aime-admin-2024"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

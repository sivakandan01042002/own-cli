import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

USER_CONFIG_DIR = Path.home() / ".querynest"
USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Application Settings
    # ---------------------------------------------------------
    PROJECT_NAME: str = "QueryNest Multi-Agent Coding Assistant"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Workspace Root Path (defaults to current working directory, or QUERYNEST_WORKSPACE_ROOT if set)
    WORKSPACE_ROOT: Path = Path(os.getenv("QUERYNEST_WORKSPACE_ROOT", Path.cwd()))

    # ---------------------------------------------------------
    # LLM API Keys & Provider Defaults
    # ---------------------------------------------------------
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    DEFAULT_PROVIDER: str = "gemini"  # "groq" or "gemini"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # ---------------------------------------------------------
    # 1. Cloud Redis (Upstash / Redis Cloud / Local)
    # ---------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_ENABLED: bool = True
    REDIS_CACHE_TTL_SECONDS: int = 3600

    # ---------------------------------------------------------
    # 2. Cloud MongoDB (MongoDB Atlas)
    # ---------------------------------------------------------
    MONGO_URI: str = ""
    MONGO_DB_NAME: str = "querynest"

    # ---------------------------------------------------------
    # 3. Cloud PostgreSQL / Supabase / Neon
    # ---------------------------------------------------------
    POSTGRES_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ---------------------------------------------------------
    # Execution & Self-Healing Limits
    # ---------------------------------------------------------
    MAX_RETRY_COUNT: int = 3
    COMMAND_TIMEOUT_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=[
            str(Path.cwd() / ".env"),
            str(USER_CONFIG_DIR / ".env"),
            str(Path(__file__).resolve().parent.parent.parent / ".env"),
        ],
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

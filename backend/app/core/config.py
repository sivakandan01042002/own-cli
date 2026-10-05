from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Application Settings
    # ---------------------------------------------------------
    PROJECT_NAME: str = "QueryNest Multi-Agent Coding Assistant"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Workspace Root Path (defaults to project root)
    WORKSPACE_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

    # ---------------------------------------------------------
    # LLM API Keys & Provider Defaults
    # ---------------------------------------------------------
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    DEFAULT_PROVIDER: str = "groq"  # "groq" or "gemini"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_MODEL: str = "gemini-3.8-flash"

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
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

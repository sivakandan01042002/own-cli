from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "QueryNest Multi-Agent Coding Assistant"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Workspace Root Path (defaults to project root)
    WORKSPACE_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

    # API Keys
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Default LLM configurations (Fast & Free)
    DEFAULT_PROVIDER: str = "groq"  # "groq" or "gemini"
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GEMINI_MODEL: str = "gemini-1.5-flash"


    # Execution limits
    MAX_RETRY_COUNT: int = 3
    COMMAND_TIMEOUT_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

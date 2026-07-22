from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/agent.db")
    analytics_db_path: str = Field(default="./data/agent-analytics.db")
    log_level: str = Field(default="INFO")

    # LLM provider — auto-detected from whichever key is set if left blank
    llm_provider: str = Field(default="")   # "anthropic" | "gemini"
    llm_model: str = Field(default="")      # uses provider default when blank

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # Analyst guardrails (spec/architecture.md → Security & Privacy Boundaries)
    max_upload_mb: int = Field(default=120)
    sql_timeout_s: float = Field(default=8.0)
    max_sql_iterations: int = Field(default=4)
    result_row_cap: int = Field(default=200)     # rows fetched/stored per result
    llm_result_rows: int = Field(default=50)     # rows serialized into LLM prompts
    history_turns: int = Field(default=10)

    @property
    def resolved_llm_provider(self) -> str:
        """Provider name with dirty .env values tolerated (inline comments, whitespace)."""
        raw = (self.llm_provider or "").split("#", 1)[0].strip().lower()
        if raw:
            return raw
        if self.anthropic_api_key.strip():
            return "anthropic"
        if self.gemini_api_key.strip():
            return "gemini"
        return ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

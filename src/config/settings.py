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

    # Phase 3 — MsSQL source (read-only) + nightly sync window (server local time)
    mssql_host: str = Field(default="")
    mssql_port: int = Field(default=1433)
    mssql_database: str = Field(default="")
    mssql_username: str = Field(default="")
    mssql_password: str = Field(default="")
    sync_hour: int = Field(default=2)            # 02:00 local — off-peak
    sync_batch_rows: int = Field(default=50_000)

    # Phase 4 — SMTP delivery + cost estimates (₹ per 1M tokens; label as estimates)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_tls: bool = Field(default=True)
    price_input_per_m: float = Field(default=26.0)
    price_output_per_m: float = Field(default=105.0)
    session_hours: int = Field(default=12)

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

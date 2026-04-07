"""Centralized application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Copy .env.example to .env for local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "query_scheduler"
    app_env: str = "development"
    app_debug: bool = False

    # Server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 1
    app_reload: bool = True

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/query_scheduler"
    )

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"  # "console" or "json"

    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = "PUBLIC"

    # Access Control
    query_access_enabled: bool = True
    allowed_capabilities: str = "start_query,get_status,get_results"

    # Query Limits
    max_query_length: int = 10_000
    query_result_max_rows: int = 10_000

    # OpenTelemetry
    otel_enabled: bool = False
    otel_service_name: str = "query_scheduler"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_traces_sampler: str = "parentbased_always_on"
    otel_traces_sampler_arg: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


settings = Settings()

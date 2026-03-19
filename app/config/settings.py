from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str

    # External APIs
    anthropic_api_key: str = ""
    coresignal_api_key: str = ""
    stripe_secret_key: str = ""

    # Webhooks
    supabase_webhook_secret: str = ""

    # Optional
    slack_alert_webhook_url: str | None = None

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:54322/postgres"

    # App
    environment: str = "dev"
    log_level: int = 20  # INFO

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

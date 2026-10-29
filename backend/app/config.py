from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    channel3_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./pactguard.db"
    replay_mode: bool = False  # deterministic replay fallback for demos


settings = Settings()

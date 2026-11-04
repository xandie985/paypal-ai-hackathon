from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_vault_id: str = ""
    channel3_api_key: str = ""
    channel3_base_url: str = "https://api.trychannel3.com"
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    ledger_path: str = "./ledger.db"
    gate_secret: str = "dev-only-gate-secret-change-me"
    # Deterministic replay of PayPal/Channel3/LLM so the demo never depends on sandbox uptime.
    replay_mode: bool = True

    @property
    def paypal_live(self) -> bool:
        return not self.replay_mode and bool(self.paypal_client_id and self.paypal_client_secret)


settings = Settings()

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("pactguard.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

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
    # Browser origins allowed to call the API from another host (Vite dev servers). The deployed app serves the
    # frontend from the same origin, so it needs none.
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    # Folder of the built frontend (frontend/dist). When set, the API serves it at "/" so one web service hosts both.
    frontend_dist: str = ""
    # Deterministic replay of PayPal/Channel3/LLM so the demo never depends on sandbox uptime.
    replay_mode: bool = True

    # Where a buyer ships a returned item (make-offer REFUND_WITH_RETURN). PayPal shows it to the buyer,
    # so it must be your real returns address in live mode.
    return_address_line_1: str = ""
    return_address_city: str = ""
    return_address_state: str = ""
    return_address_postal_code: str = ""
    return_address_country: str = "US"

    @property
    def return_address(self) -> dict | None:
        """PayPal address object, or None when unset in live mode (a refund-on-return offer is then refused).
        Replay uses an obviously fictional address so rehearsals work without configuration."""
        if self.return_address_line_1 and self.return_address_city and self.return_address_postal_code:
            return {
                "address_line_1": self.return_address_line_1,
                "admin_area_2": self.return_address_city,
                "admin_area_1": self.return_address_state,
                "postal_code": self.return_address_postal_code,
                "country_code": self.return_address_country,
            }
        if self.replay_mode:
            return {
                "address_line_1": "1 Replay Returns Dock (demo)",
                "admin_area_2": "Nowhere",
                "admin_area_1": "CA",
                "postal_code": "00000",
                "country_code": "US",
            }
        return None

    @property
    def paypal_live(self) -> bool:
        return not self.replay_mode and bool(self.paypal_client_id and self.paypal_client_secret)

    @model_validator(mode="after")
    def _validate_gate_secret(self) -> "Settings":
        placeholders = {"dev-only-gate-secret-change-me", "change-me-to-a-long-random-string"}
        if self.gate_secret in placeholders:
            msg = f"GATE_SECRET is set to placeholder '{self.gate_secret}'. Set a secure random secret in production/live environments."
            logger.warning(msg)
        return self


settings = Settings()

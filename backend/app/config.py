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
    llm_model: str = "claude-haiku-5-5"
    ledger_path: str = "./ledger.db"
    gate_secret: str = "dev-only-gate-secret-change-me"
    # Browser origins allowed to call the API from another host (Vite dev servers). The deployed app serves the
    # frontend from the same origin, so it needs none.
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    # Folder of the built frontend (frontend/dist). When set, the API serves it at "/" so one web service hosts both.
    frontend_dist: str = ""
    # Deterministic replay of PayPal/Channel3/LLM so the demo never depends on sandbox uptime.
    replay_mode: bool = True
    # A "sandbox run" is a per-run opt-in to the real PayPal sandbox from an otherwise replay deployment. Off unless set.
    allow_sandbox_runs: bool = False
    sandbox_run_budget_cap: float = 2500  # largest mandate budget a sandbox run accepts, in USD
    sandbox_runs_per_hour: int = 12  # across all clients

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

    @property
    def sandbox_runs_available(self) -> bool:
        return self.allow_sandbox_runs and bool(self.paypal_client_id and self.paypal_client_secret and self.paypal_vault_id)

    @model_validator(mode="after")
    def _validate_gate_secret(self) -> "Settings":
        placeholders = {"dev-only-gate-secret-change-me", "change-me-to-a-long-random-string"}
        if self.gate_secret in placeholders:
            msg = f"GATE_SECRET is set to placeholder '{self.gate_secret}'. Set a secure random secret in production/live environments."
            if not self.replay_mode:
                raise ValueError(msg)  # live money must never sit behind a published secret
            logger.warning(msg)
        return self


settings = Settings()

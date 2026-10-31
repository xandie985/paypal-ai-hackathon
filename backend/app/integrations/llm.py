"""Optional Claude layer. The loop's money decisions are deterministic; the LLM only
drafts language (seller messages, dispute narratives, Studio answers) and every
structured result it returns still goes through the same schema gate as any seller.
With no API key or in replay mode, callers get None and use their template."""

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLM:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def structured(self, system: str, prompt: str, schema: type[T], effort: str = "low") -> T | None:
        import anthropic

        try:
            resp = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError):
            return None
        if resp.stop_reason in ("refusal", "max_tokens"):
            return None
        return resp.parsed_output

    def text(self, system: str, prompt: str, effort: str = "low") -> str | None:
        import anthropic

        try:
            resp = self._client.beta.messages.create(
                model=self._model,
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError):
            return None
        if resp.stop_reason == "refusal":
            return None
        return "".join(b.text for b in resp.content if b.type == "text") or None


def make_llm(settings) -> LLM | None:
    if settings.replay_mode or not settings.anthropic_api_key:
        return None
    return LLM(settings.anthropic_api_key, settings.llm_model)

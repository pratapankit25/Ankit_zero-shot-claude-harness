import time
from collections.abc import Callable
from dataclasses import dataclass

from config.settings import get_settings


class LLMError(Exception):
    """Provider failure with a user-safe message."""


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


def _make_provider():
    s = get_settings()
    provider = s.resolved_llm_provider

    if not provider:
        raise RuntimeError(
            "No LLM provider configured. Set AGENT_ANTHROPIC_API_KEY or "
            "AGENT_GEMINI_API_KEY in .env, or set AGENT_LLM_PROVIDER explicitly."
        )

    if provider == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model)
    if provider == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=s.gemini_api_key, model=s.llm_model)

    raise RuntimeError(f"Unknown LLM provider: {provider!r}. Supported: anthropic, gemini")


_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "overloaded", "timeout", "temporarily")


class LLMClient:
    def __init__(self) -> None:
        self._provider = _make_provider()

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(prompt, system=system).text

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResult:
        return self._with_retry(lambda: self._provider.generate(prompt, system=system))

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        on_delta: Callable[[str], None],
    ) -> LLMResult:
        return self._with_retry(
            lambda: self._provider.generate_stream(prompt, system=system, on_delta=on_delta)
        )

    @staticmethod
    def _with_retry(fn):
        try:
            return fn()
        except Exception as exc:  # one retry on transient provider errors
            msg = str(exc).lower()
            if any(m in msg for m in _TRANSIENT_MARKERS):
                time.sleep(2)
                try:
                    return fn()
                except Exception as exc2:
                    raise LLMError(_friendly(exc2)) from exc2
            raise LLMError(_friendly(exc)) from exc


def _friendly(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "not_found" in low or "404" in low:
        return (
            "The configured model was not found — set AGENT_LLM_MODEL in .env to an "
            f"available model. Provider said: {msg[:200]}"
        )
    if any(k in low for k in ("api key", "api_key", "unauthorized", "401", "403", "permission")):
        return (
            "The LLM API rejected the key — check AGENT_GEMINI_API_KEY / "
            f"AGENT_ANTHROPIC_API_KEY in .env. Provider said: {msg[:200]}"
        )
    if any(k in low for k in ("connect", "network", "proxy", "dns", "unreachable", "timed out", "timeout")):
        return f"Could not reach the LLM API — check your network/proxy. Provider said: {msg[:200]}"
    return f"LLM call failed: {msg[:300]}"

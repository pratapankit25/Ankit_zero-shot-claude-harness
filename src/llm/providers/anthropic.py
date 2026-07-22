from collections.abc import Callable

import anthropic as _sdk


class AnthropicProvider:
    DEFAULT_MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 4096

    def __init__(self, api_key: str, model: str) -> None:
        self._client = _sdk.Anthropic(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def _kwargs(self, prompt: str, system: str | None) -> dict:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=self.MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        return kwargs

    def generate(self, prompt: str, *, system: str | None = None):
        from llm.client import LLMResult

        msg = self._client.messages.create(**self._kwargs(prompt, system))
        return LLMResult(
            text=msg.content[0].text if msg.content else "",
            input_tokens=int(msg.usage.input_tokens or 0),
            output_tokens=int(msg.usage.output_tokens or 0),
        )

    def generate_stream(
        self, prompt: str, *, system: str | None = None, on_delta: Callable[[str], None]
    ):
        from llm.client import LLMResult

        parts: list[str] = []
        with self._client.messages.stream(**self._kwargs(prompt, system)) as stream:
            for text in stream.text_stream:
                parts.append(text)
                on_delta(text)
            final = stream.get_final_message()
        return LLMResult(
            text="".join(parts),
            input_tokens=int(final.usage.input_tokens or 0),
            output_tokens=int(final.usage.output_tokens or 0),
        )

    # kept for baseline compatibility
    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(prompt, system=system).text

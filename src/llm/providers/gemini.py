from collections.abc import Callable

from google import genai
from google.genai import types


def _usage(meta) -> tuple[int, int]:
    if meta is None:
        return 0, 0
    return int(meta.prompt_token_count or 0), int(meta.candidates_token_count or 0)


class GeminiProvider:
    DEFAULT_MODEL = "gemini-3.1-pro"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def _config(self, system: str | None):
        return types.GenerateContentConfig(system_instruction=system) if system else None

    def generate(self, prompt: str, *, system: str | None = None):
        from llm.client import LLMResult

        response = self._client.models.generate_content(
            model=self._model, contents=prompt, config=self._config(system)
        )
        inp, out = _usage(getattr(response, "usage_metadata", None))
        return LLMResult(text=response.text or "", input_tokens=inp, output_tokens=out)

    def generate_stream(
        self, prompt: str, *, system: str | None = None, on_delta: Callable[[str], None]
    ):
        from llm.client import LLMResult

        parts: list[str] = []
        usage_meta = None
        for chunk in self._client.models.generate_content_stream(
            model=self._model, contents=prompt, config=self._config(system)
        ):
            if getattr(chunk, "usage_metadata", None) is not None:
                usage_meta = chunk.usage_metadata
            text = chunk.text or ""
            if text:
                parts.append(text)
                on_delta(text)
        inp, out = _usage(usage_meta)
        return LLMResult(text="".join(parts), input_tokens=inp, output_tokens=out)

    # kept for baseline compatibility
    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(prompt, system=system).text

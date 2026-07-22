import re
from collections.abc import Callable

from google import genai
from google.genai import types

from observability.events import get_logger

log = get_logger("llm.gemini")

_EXCLUDE = ("embedding", "imagen", "image", "tts", "audio", "live", "veo", "aqa", "learnlm")


def pick_best_model(names: list[str]) -> str | None:
    """Choose the best generateContent-capable Gemini model from `names`.

    Preference: newest version first; at equal version, flash (cheap/fast) over
    pro — this project's cost constraint (spec/roadmap.md → Key Constraints);
    stable names over preview/exp. Pure function, unit-tested.
    """
    def version(n: str) -> float:
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0

    candidates = [
        n for n in names
        if n.startswith("gemini") and version(n) > 0 and not any(x in n for x in _EXCLUDE)
    ]
    if not candidates:
        return None

    def rank(n: str) -> tuple:
        stable = 0 if ("preview" in n or "exp" in n) else 1
        flash = 1 if "flash" in n else 0
        return (version(n), stable, flash, -len(n))

    return max(candidates, key=rank)


def _usage(meta) -> tuple[int, int]:
    if meta is None:
        return 0, 0
    return int(meta.prompt_token_count or 0), int(meta.candidates_token_count or 0)


# requested model -> working model, discovered once per process (a provider is
# constructed per node call; without this cache every call would re-pay the 404+list)
_MODEL_CACHE: dict[str, str] = {}


class GeminiProvider:
    DEFAULT_MODEL = "gemini-3.1-pro"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._requested = model or self.DEFAULT_MODEL
        self._model = _MODEL_CACHE.get(self._requested, self._requested)
        self._fallback_tried = False

    def _config(self, system: str | None):
        return types.GenerateContentConfig(system_instruction=system) if system else None

    def _available_models(self) -> list[str]:
        names: list[str] = []
        for m in self._client.models.list():
            name = (getattr(m, "name", "") or "").removeprefix("models/")
            actions = (
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            if not actions or "generateContent" in actions:
                names.append(name)
        return names

    def _with_model_fallback(self, fn):
        """On NOT_FOUND for the configured model, discover what this key CAN use,
        switch to the best available model once, and retry (tech-stack rule:
        never trust a hardcoded model name)."""
        try:
            return fn()
        except Exception as exc:
            msg = str(exc)
            if self._fallback_tried or not ("NOT_FOUND" in msg or "404" in msg):
                raise
            self._fallback_tried = True
            try:
                best = pick_best_model(self._available_models())
            except Exception:
                raise exc
            if not best or best == self._model:
                raise
            log.info("gemini.model_fallback", requested=self._model, using=best)
            self._model = best
            _MODEL_CACHE[self._requested] = best
            return fn()

    def generate(self, prompt: str, *, system: str | None = None):
        from llm.client import LLMResult

        def call():
            return self._client.models.generate_content(
                model=self._model, contents=prompt, config=self._config(system)
            )

        response = self._with_model_fallback(call)
        inp, out = _usage(getattr(response, "usage_metadata", None))
        return LLMResult(text=response.text or "", input_tokens=inp, output_tokens=out)

    def generate_stream(
        self, prompt: str, *, system: str | None = None, on_delta: Callable[[str], None]
    ):
        from llm.client import LLMResult

        def call():
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
            return parts, usage_meta

        parts, usage_meta = self._with_model_fallback(call)
        inp, out = _usage(usage_meta)
        return LLMResult(text="".join(parts), input_tokens=inp, output_tokens=out)

    # kept for baseline compatibility
    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(prompt, system=system).text

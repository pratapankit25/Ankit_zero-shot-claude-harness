import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = FIXTURES / "samples"


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    import config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _isolated_analytics(tmp_path, monkeypatch):
    """Every test gets its own analytics store file; no background scheduler."""
    monkeypatch.setenv("AGENT_ANALYTICS_DB_PATH", str(tmp_path / "analytics.db"))
    monkeypatch.setenv("AGENT_SCHEDULER", "0")
    yield


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.models import Base
    import db.session as session_module

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield engine
    engine.dispose()


@pytest.fixture
def _require_llm_key():
    """Skip real-LLM tests when no key is set, or when explicitly disabled.

    AGENT_SKIP_LLM_TESTS=1 exists for environments that cannot reach the
    provider (e.g. the sandbox this was authored in). The Phase-1 gate on the
    user's machine runs WITHOUT this flag — skipped is not passed.
    """
    if os.environ.get("AGENT_SKIP_LLM_TESTS") == "1":
        pytest.skip("AGENT_SKIP_LLM_TESTS=1 — real-LLM tests disabled in this environment")
    from config.settings import get_settings
    s = get_settings()
    if not s.anthropic_api_key and not s.gemini_api_key:
        pytest.skip("No LLM key set in .env (AGENT_ANTHROPIC_API_KEY or AGENT_GEMINI_API_KEY)")


@pytest.fixture
def api_client(_isolated_db):
    """FastAPI test client with isolated DBs."""
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def expected():
    return json.loads((FIXTURES / "expected_answers.json").read_text(encoding="utf-8"))


@pytest.fixture
def load_samples(api_client):
    """Upload the three sample CSVs; returns the dataset records."""
    files = []
    for name in ("fir_records.csv", "dial112_calls.csv", "personnel.csv"):
        files.append(("files", (name, (SAMPLES / name).read_bytes(), "text/csv")))
    r = api_client.post("/datasets", files=files)
    assert r.status_code == 200, r.text
    datasets = r.json()["data"]
    assert all(d["status"] == "ready" for d in datasets), datasets
    return datasets


class FakeLLMResult:
    def __init__(self, text: str):
        self.text = text
        self.input_tokens = 10
        self.output_tokens = 20


class FakeLLM:
    """Scripted stand-in for LLMClient in offline graph tests.

    script: list of strings returned in order by generate/generate_stream.
    """

    script: list[str] = []
    calls: list[dict] = []
    _index = 0

    def __init__(self) -> None:
        pass

    @classmethod
    def reset(cls, script: list[str]) -> None:
        cls.script = script
        cls.calls = []
        cls._index = 0

    def _next(self, prompt: str, system: str | None) -> FakeLLMResult:
        cls = type(self)
        if cls._index >= len(cls.script):
            raise AssertionError(f"FakeLLM script exhausted at call {cls._index}")
        text = cls.script[cls._index]
        cls.calls.append({"prompt": prompt, "system": system, "reply": text})
        cls._index += 1
        return FakeLLMResult(text)

    def generate(self, prompt: str, *, system: str | None = None) -> FakeLLMResult:
        return self._next(prompt, system)

    def generate_stream(self, prompt: str, *, system: str | None = None, on_delta):
        result = self._next(prompt, system)
        mid = max(1, len(result.text) // 2)
        on_delta(result.text[:mid])
        on_delta(result.text[mid:])
        return result

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(prompt, system=system).text


@pytest.fixture
def fake_llm(monkeypatch):
    import graph.nodes as nodes_module
    monkeypatch.setattr(nodes_module, "LLMClient", FakeLLM)
    return FakeLLM

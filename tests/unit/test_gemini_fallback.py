"""Model-fallback ranking — pure, no network."""
from llm.providers.gemini import pick_best_model


def test_prefers_newest_then_flash():
    names = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    assert pick_best_model(names) == "gemini-2.5-flash"


def test_newer_generation_beats_flash_of_older():
    names = ["gemini-2.5-flash", "gemini-3.0-pro"]
    assert pick_best_model(names) == "gemini-3.0-pro"


def test_stable_beats_preview_same_version():
    names = ["gemini-2.5-flash-preview-0514", "gemini-2.5-flash"]
    assert pick_best_model(names) == "gemini-2.5-flash"


def test_excludes_non_text_models():
    names = ["gemini-2.5-flash-image", "gemini-embedding-001", "gemini-2.5-flash-tts", "gemini-2.0-flash"]
    assert pick_best_model(names) == "gemini-2.0-flash"


def test_empty_and_foreign_names():
    assert pick_best_model([]) is None
    assert pick_best_model(["chat-bison", "text-unicorn"]) is None

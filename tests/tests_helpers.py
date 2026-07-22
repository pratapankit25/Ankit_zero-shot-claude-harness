from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def samples_path(name: str) -> Path:
    return FIXTURES / "samples" / name


def read_sample(name: str) -> bytes:
    return samples_path(name).read_bytes()

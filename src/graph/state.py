from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    conversation_id: str
    user_id: str             # phase 4: attribution
    user_district: str       # phase 4: set only for district-scoped viewers

    # Input
    question: str
    history: list            # [{question, answer, sql}], newest last, ≤ settings.history_turns
    datasets: list           # registry snapshot for prompts

    # Pipeline
    language: str            # "en" | "hi" | "hinglish"
    mode: str                # "answer" | "clarify"
    plan: dict               # {approach, dataset_ids, steps}
    sql: str
    sql_attempts: list       # [{sql, error | row_count}]
    iterations: int
    empty_retries: int
    result: dict             # {columns, rows, row_count, truncated}
    steps: list              # user-facing ticker log

    # Output
    answer: str
    caveats: list
    followups: list
    chart: dict | None       # {type, x, y, points[]} — deterministic, may be absent
    flags: list              # [{kind, message}] computed anomaly flags
    usage: dict              # {input_tokens, output_tokens}

    # Control
    error: str | None
    status: str              # completed | failed | clarification

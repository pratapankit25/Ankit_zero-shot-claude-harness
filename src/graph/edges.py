from config.settings import get_settings
from graph.state import AgentState


def after_prepare(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "plan"


def after_plan(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("mode") == "clarify":
        return "finalize"
    return "write_sql"


def after_write_sql(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "execute_sql"


def check_result(state: AgentState) -> str:
    """Retry loop: SQL error or empty result → another write_sql attempt (bounded).

    Edge functions must be read-only (LangGraph ignores their state writes), so
    all counters are derived from sql_attempts; handle_error composes the
    exhaustion message from the same trace.
    """
    if state.get("error"):
        return "handle_error"
    max_iter = get_settings().max_sql_iterations
    attempts = state.get("sql_attempts", [])
    last = attempts[-1] if attempts else {}

    if last.get("error"):
        return "write_sql" if state.get("iterations", 0) < max_iter else "handle_error"

    result = state.get("result") or {}
    empty_attempts = sum(1 for a in attempts if a.get("row_count") == 0)
    if result.get("row_count", 0) == 0 and empty_attempts < 2 \
            and state.get("iterations", 0) < max_iter:
        return "write_sql"
    return "compose_answer"


def after_compose(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "finalize"

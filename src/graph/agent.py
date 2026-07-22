from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    compose_answer,
    execute_sql,
    finalize,
    handle_error,
    plan,
    prepare_context,
    write_sql,
)
from graph.edges import after_compose, after_plan, after_prepare, after_write_sql, check_result


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("prepare_context", prepare_context)
    g.add_node("plan", plan)
    g.add_node("write_sql", write_sql)
    g.add_node("execute_sql", execute_sql)
    g.add_node("compose_answer", compose_answer)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("prepare_context")
    g.add_conditional_edges("prepare_context", after_prepare,
                            {"plan": "plan", "handle_error": "handle_error"})
    g.add_conditional_edges("plan", after_plan,
                            {"write_sql": "write_sql", "finalize": "finalize", "handle_error": "handle_error"})
    g.add_conditional_edges("write_sql", after_write_sql,
                            {"execute_sql": "execute_sql", "handle_error": "handle_error"})
    g.add_conditional_edges("execute_sql", check_result,
                            {"write_sql": "write_sql", "compose_answer": "compose_answer",
                             "handle_error": "handle_error"})
    g.add_conditional_edges("compose_answer", after_compose,
                            {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()

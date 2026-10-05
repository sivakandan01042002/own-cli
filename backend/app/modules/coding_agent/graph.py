from langgraph.graph import StateGraph, START, END
from app.modules.coding_agent.state import CodingAgentState
from app.modules.coding_agent.nodes import (
    planner_node,
    coder_node,
    tool_node,
    validator_node,
    fixer_node,
    summarizer_node,
)
from app.modules.coding_agent.edges import (
    should_continue_coder,
    should_retry_or_finish,
)

# 1. Initialize the StateGraph with the CodingAgentState schema
workflow = StateGraph(CodingAgentState)

# 2. Register all agent and tool nodes
workflow.add_node("planner", planner_node)
workflow.add_node("coder", coder_node)
workflow.add_node("tools", tool_node)
workflow.add_node("validator", validator_node)
workflow.add_node("fixer", fixer_node)
workflow.add_node("summarizer", summarizer_node)

# 3. Initial flow: START -> planner -> coder
workflow.add_edge(START, "planner")
workflow.add_edge("planner", "coder")

# 4. Coder tool execution loop (Decision 1)
workflow.add_conditional_edges(
    "coder",
    should_continue_coder,
    {
        "tools": "tools",
        "validator": "validator",
    },
)
workflow.add_edge("tools", "coder")

# 5. Validation & self-healing retry loop (Decision 2)
workflow.add_conditional_edges(
    "validator",
    should_retry_or_finish,
    {
        "fixer": "fixer",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("fixer", "coder")

# 6. Complete task after summary
workflow.add_edge("summarizer", END)

# 7. Compile the runnable LangGraph application
coding_agent_app = workflow.compile()

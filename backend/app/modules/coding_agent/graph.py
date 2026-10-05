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
    route_initial_intent,
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

# 3. Smart Initial Routing: START -> (planner OR coder directly for questions)
workflow.add_conditional_edges(
    START,
    route_initial_intent,
    {
        "planner": "planner",
        "coder": "coder",
    },
)

# 4. Planner always hands off to Coder
workflow.add_edge("planner", "coder")

# 5. Coder tool execution or completion decision
workflow.add_conditional_edges(
    "coder",
    should_continue_coder,
    {
        "tools": "tools",
        "validator": "validator",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("tools", "coder")

# 6. Validation & self-healing retry loop
workflow.add_conditional_edges(
    "validator",
    should_retry_or_finish,
    {
        "fixer": "fixer",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("fixer", "coder")

# 7. Complete task after summary
workflow.add_edge("summarizer", END)

# 8. Compile the runnable LangGraph application
coding_agent_app = workflow.compile()

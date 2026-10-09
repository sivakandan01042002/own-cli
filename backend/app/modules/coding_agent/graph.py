from langgraph.graph import StateGraph, START, END
from app.modules.coding_agent.state import CodingAgentState
from app.modules.coding_agent.nodes import (
    classifier_node,
    conversation_node,
    tool_agent_node,
    direct_action_tool_node,
    code_inspector_node,
    read_only_tool_node,
    planner_node,
    coder_node,
    coder_tool_node,
    dedicated_test_runner_node,
    validation_node,
    fixer_node,
    summarizer_node,
)
from app.modules.coding_agent.edges import (
    route_classified_intent,
    should_continue_tool_agent,
    should_continue_code_inspector,
    should_continue_coder,
    should_retry_or_finish,
)

# 1. Initialize the StateGraph with the CodingAgentState schema
workflow = StateGraph(CodingAgentState)

# 2. Register all agent and tool execution nodes
workflow.add_node("classifier", classifier_node)
workflow.add_node("conversation", conversation_node)
workflow.add_node("tool_agent", tool_agent_node)
workflow.add_node("direct_action_tools", direct_action_tool_node)
workflow.add_node("code_inspector", code_inspector_node)
workflow.add_node("read_only_tools", read_only_tool_node)
workflow.add_node("planner", planner_node)
workflow.add_node("coder", coder_node)
workflow.add_node("coder_tools", coder_tool_node)
workflow.add_node("dedicated_test_runner", dedicated_test_runner_node)
workflow.add_node("validator", validation_node)
workflow.add_node("fixer", fixer_node)
workflow.add_node("summarizer", summarizer_node)

# 3. Graph Entry -> Classifier (Snapshot & Intent Selection)
workflow.add_edge(START, "classifier")

# 4. Classifier -> Specialized Agent Nodes
workflow.add_conditional_edges(
    "classifier",
    route_classified_intent,
    {
        "conversation": "conversation",
        "tool_agent": "tool_agent",
        "code_inspector": "code_inspector",
        "planner": "planner",
        "dedicated_test_runner": "dedicated_test_runner",
    },
)

# 5. Conversation Path -> Direct to Summarizer
workflow.add_edge("conversation", "summarizer")

# 6. Direct Action Tool Loop (Media / Web / Browser)
workflow.add_conditional_edges(
    "tool_agent",
    should_continue_tool_agent,
    {
        "direct_action_tools": "direct_action_tools",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("direct_action_tools", "tool_agent")

# 7. Read-Only Code Inspector Loop
workflow.add_conditional_edges(
    "code_inspector",
    should_continue_code_inspector,
    {
        "read_only_tools": "read_only_tools",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("read_only_tools", "code_inspector")

# 8. Code Change Workflow: Planner -> Coder
workflow.add_edge("planner", "coder")

# 9. Coder Modification & Verification Loop
workflow.add_conditional_edges(
    "coder",
    should_continue_coder,
    {
        "coder_tools": "coder_tools",
        "validator": "validator",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("coder_tools", "coder")

# 10. Dedicated Test Runner -> Summarizer
workflow.add_edge("dedicated_test_runner", "summarizer")

# 11. Validation & Repair Retry Loop
workflow.add_conditional_edges(
    "validator",
    should_retry_or_finish,
    {
        "fixer": "fixer",
        "summarizer": "summarizer",
    },
)
workflow.add_edge("fixer", "coder")

# 12. Terminal Completion
workflow.add_edge("summarizer", END)

# 13. Compile the runnable LangGraph application
coding_agent_app = workflow.compile()

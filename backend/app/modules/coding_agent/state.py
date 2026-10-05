from typing import Annotated, TypedDict, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CodingAgentState(TypedDict):
    """
    Central memory state dedicated to the Coding Agent workflow.
    Provides a strongly-typed contract across all specialized agent nodes.
    """
    # 1. User Request & Conversation History (with LangGraph append reducer)
    task: str
    messages: Annotated[List[BaseMessage], add_messages]

    # 2. Repository & Workspace Context
    workspace_root: str
    repository_tree: Optional[str]

    # 3. Planning & Architecture Blueprint
    plan: Optional[str]

    # 4. Coding & Inspection Findings
    coder_findings: List[str]
    modified_files: List[str]

    # 5. Testing, Verification & Self-Healing
    test_command: Optional[str]
    test_results: Optional[str]
    test_passed: bool
    fixer_analysis: Optional[str]
    retry_count: int

    # 6. Final User Completion Report
    final_summary: Optional[str]

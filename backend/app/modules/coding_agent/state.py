from typing import Annotated, TypedDict, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CodingAgentState(TypedDict):
    """
    Central memory state dedicated to the Coding Agent workflow.
    """
    # Message history with automatic appending reducer (like Redux append)
    messages: Annotated[List[BaseMessage], add_messages]

    # Task definition & architectural plan
    task: str
    plan: Optional[str]

    # Tracking generated / modified files
    modified_files: List[str]

    # Testing & Verification
    test_command: Optional[str]
    test_results: Optional[str]
    test_passed: bool
    retry_count: int

    # Final summary for the user
    final_summary: Optional[str]

from typing import Annotated, TypedDict, Optional, List, Dict, Any, Literal
try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

TaskType = Literal[
    "conversation",
    "image_generation",
    "web_search",
    "code_question",
    "code_change",
    "test_request",
]

FollowUpCategory = Literal[
    "new_request",
    "follow_up_question",
    "inspect_previous_result",
    "refine_previous_result",
    "retry_previous_action",
    "status_question",
]

TaskExecutionStatus = Literal["completed", "failed", "blocked", "incomplete"]
ManifestStatus = Literal["complete", "partial", "failed"]


class ToolExecutionRecord(TypedDict):
    """Authoritative physical record of a single tool execution."""
    task_id: str
    intent: TaskType
    tool_name: str
    input_args: Dict[str, Any]
    status: Literal["pending", "running", "success", "failed", "cancelled"]
    output_preview: str
    error: Optional[str]
    artifact_path: Optional[str]
    artifact_verified: bool
    timestamp: float
    retry_attempt: int


class WorkspaceManifest(TypedDict):
    """Snapshot of repository state at workflow start to verify actual modifications."""
    is_git_repo: bool
    manifest_status: ManifestStatus
    initial_git_status: List[str]
    initial_tracked_files: List[str]
    initial_file_hashes: Dict[str, str]  # relative_path -> sha256
    skipped_files: List[str]             # files >5MB or external symlinks
    manifest_error: Optional[str]


class VerificationResult(TypedDict):
    """Structured result from comparing live filesystem against baseline manifest."""
    verified: bool
    source_changed: bool
    config_changed: bool
    changed_files: List[str]
    unverified_files: List[str]
    error: Optional[str]


class CodingAgentState(TypedDict):
    """
    Central memory state for the QueryNest multi-agent workflow.
    Provides a strongly-typed contract across all specialized agent nodes.
    """
    # 1. User Request & Multi-turn Conversation Context (with append reducer)
    task: str
    messages: Annotated[List[BaseMessage], add_messages]

    # 2. Workspace & Hardened Baseline Snapshot
    workspace_root: str
    repository_tree: Optional[str]
    workspace_manifest: NotRequired[WorkspaceManifest]

    # 3. Intent, Follow-Up Classification & Task Context
    task_type: NotRequired[TaskType]
    follow_up_category: NotRequired[FollowUpCategory]
    active_task_context: NotRequired[Optional[str]]
    active_task_intent: NotRequired[Optional[TaskType]]
    active_task_id: NotRequired[Optional[str]]
    execution_status: NotRequired[TaskExecutionStatus]
    direct_tool_iterations: NotRequired[int]
    inspector_tool_iterations: NotRequired[int]
    coder_tool_iterations: NotRequired[int]
    tool_result: NotRequired[Optional[Dict[str, Any]]]

    # 4. Authoritative Tool Execution History
    tool_execution_history: NotRequired[List[ToolExecutionRecord]]

    # 5. Architecture Blueprint (Only for code_change)
    plan: NotRequired[Optional[str]]

    # 6. Inspection & Modification Findings
    coder_findings: NotRequired[List[str]]
    modified_files: NotRequired[List[str]]
    verification_result: NotRequired[Optional[VerificationResult]]

    # 7. Testing, Verification & Self-Healing
    detected_test_runner: NotRequired[Optional[str]]
    test_command: NotRequired[Optional[str]]
    test_results: NotRequired[Optional[str]]
    test_passed: NotRequired[bool]
    fixer_analysis: NotRequired[Optional[str]]
    retry_count: NotRequired[int]

    # 8. Final Completion Report
    final_summary: NotRequired[Optional[str]]

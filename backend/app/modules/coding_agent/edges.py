import json
import re
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage

from app.core.config import settings
from app.core.llm import get_cached_llm
from app.constants import (
    MAX_TOOL_CALLS_PER_TURN,
    MAX_DIRECT_TOOL_ITERATIONS,
    MAX_INSPECTOR_TOOL_ITERATIONS,
    MAX_CODER_TOOL_ITERATIONS,
    MAX_REPAIR_RETRIES,
)
from app.modules.coding_agent.state import CodingAgentState, TaskType, FollowUpCategory, ToolExecutionRecord
from app.modules.coding_agent.manifest import verify_code_changes
from app.modules.coding_agent.prompts import INTENT_CLASSIFIER_PROMPT


class IntentClassification(BaseModel):
    category: FollowUpCategory = Field(default="new_request", description="The follow-up interaction category.")
    intent: TaskType = Field(default="conversation", description="The target workflow intent.")
    resolved_task: str = Field(default="", description="The concrete resolved task description.")
    reasoning: str = Field(default="", description="Brief 1-sentence reasoning for the intent decision.")


def classify_intent_deterministic_fallback(
    task: str,
    active_task: Optional[str] = None,
    active_intent: Optional[TaskType] = None,
) -> Tuple[FollowUpCategory, TaskType, str]:
    """
    Deterministic, context-aware fallback classifier when LLM call is unavailable or fails.
    Returns (category, intent, resolved_task).
    """
    t = task.strip().lower()

    # 1. Status Questions (e.g. 'have you tried?', 'did it run?')
    status_keywords = ("have you tried", "did you try", "did it run", "is it done", "was it created", "did it execute")
    if any(kw in t for kw in status_keywords):
        return ("status_question", "conversation", task)

    # 2. Follow-Up Questions (e.g. 'what prompt did you use?', 'where is the file?')
    follow_up_keywords = ("what prompt", "which prompt", "what was the prompt", "where was it saved", "what parameters")
    if any(kw in t for kw in follow_up_keywords):
        return ("follow_up_question", "conversation", task)

    # 3. Inspect / Critique Previous Result
    inspect_keywords = ("doesn't look like", "does not look like", "doesn't look right", "why did that fail", "show me the result")
    if any(kw in t for kw in inspect_keywords):
        return ("inspect_previous_result", "conversation", task)

    # 4. Retry Previous Action (e.g. 'try it once', 'give it a try', 'do it again')
    retry_keywords = ("try it once", "try it again", "give it a try", "give it an try", "do it again", "try generating", "try it", "retry", "please try", "go ahead")
    if any(t == kw or t.startswith(f"{kw} ") or f" {kw}" in t for kw in retry_keywords):
        target_intent = active_intent or "image_generation"
        resolved = active_task or task
        return ("retry_previous_action", target_intent, resolved)

    # 4b. Refinement of Previous Action (e.g. 'make it with daylight', 'add sunglasses', 'change it to blue')
    refine_keywords = ("make it", "change it", "modify it", "redo it", "add to it", "with ", "instead of", "render it")
    if active_task and any(kw in t for kw in refine_keywords):
        target_intent = active_intent or "image_generation"
        resolved = f"{active_task} - {task}"
        return ("refine_previous_result", target_intent, resolved)

    # 5. Direct Media Generation
    image_keywords = (
        "create an image", "create image", "generate an image", "generate image",
        "draw an image", "draw ", "make an image", "picture of", "photo of", "image of",
        "generate a picture", "create a picture", "generate illustration", "create illustration"
    )
    if any(kw in t for kw in image_keywords):
        return ("new_request", "image_generation", task)

    # 6. Web Search
    web_keywords = ("search web", "search the web", "search online", "google ", "duckduckgo")
    if any(kw in t for kw in web_keywords):
        return ("new_request", "web_search", task)

    # 7. Explicit Test Requests
    test_keywords = ("run pytest", "run test", "run the tests", "execute tests", "run pytest ")
    if any(t.startswith(kw) or f" {kw}" in t for kw in test_keywords):
        return ("new_request", "test_request", task)

    # 8. Code Modification Verbs
    code_build_verbs = ("build ", "implement ", "refactor ", "scaffold ", "create a file", "write a file", "patch ", "fix the bug", "fix bug")
    if any(verb in t for verb in code_build_verbs):
        return ("new_request", "code_change", task)

    # 9. Repository Questions
    code_question_keywords = ("what is the purpose of", "how does", "explain the function", "explain class", "where is", "list directory", "inspect file")
    if any(kw in t for kw in code_question_keywords):
        return ("new_request", "code_question", task)

    # 10. Default / Conversation
    return ("new_request", "conversation", task)


def validate_and_reconcile_classification(
    task: str,
    category: FollowUpCategory,
    intent: TaskType,
    resolved_task: str,
    active_task: Optional[str] = None,
    active_intent: Optional[TaskType] = None,
    tool_history: Optional[List[ToolExecutionRecord]] = None,
) -> Tuple[FollowUpCategory, TaskType, str]:
    """
    Authoritative reconciliation step: validates and corrects LLM classification.
    Ensures unambiguous follow-up actions (retries, refinements) route to tools with active context,
    while status questions and prompt inquiries route safely to conversation without triggering tools.
    """
    t = task.strip().lower()

    # Derive effective active intent from tool records if missing
    effective_active_intent = active_intent
    if not effective_active_intent and tool_history:
        for rec in reversed(tool_history):
            if rec.get("intent") and rec["intent"] != "conversation":
                effective_active_intent = rec["intent"]
                break

    # Derive effective active task context from tool records if missing
    effective_active_task = active_task
    if not effective_active_task and tool_history:
        for rec in reversed(tool_history):
            args = rec.get("input_args", {})
            if args.get("prompt"):
                effective_active_task = args["prompt"]
                break
            elif args.get("query"):
                effective_active_task = args["query"]
                break

    # 1. Unambiguous Status Questions -> ALWAYS conversation (0 tools)
    status_phrases = ("have you tried", "did you try", "did it run", "is it done", "was it created", "did it execute", "have you run")
    if any(sp in t for sp in status_phrases):
        return ("status_question", "conversation", task)

    # 2. Unambiguous Follow-up Questions -> ALWAYS conversation (0 tools)
    follow_up_phrases = ("what prompt", "which prompt", "what was the prompt", "where was it saved", "where is it saved", "what parameters", "show prompt")
    if any(fp in t for fp in follow_up_phrases):
        return ("follow_up_question", "conversation", task)

    # 3. Unambiguous Result Inspection / Critique -> ALWAYS conversation (0 tools)
    inspect_phrases = ("doesn't look like", "does not look like", "doesn't look right", "why did that fail", "not what i wanted")
    if any(ip in t for ip in inspect_phrases):
        return ("inspect_previous_result", "conversation", task)

    # 4. Unambiguous Retry Requests (e.g. 'try it once', 'give it a try', 'do it again')
    retry_phrases = ("try it once", "try it again", "give it a try", "give it an try", "do it again", "try generating", "try it", "retry", "please try", "go ahead")
    is_retry_phrase = any(t == rp or t.startswith(f"{rp} ") or f" {rp}" in t for rp in retry_phrases)
    if is_retry_phrase:
        target_intent = effective_active_intent or (intent if intent != "conversation" else "image_generation")
        resolved = effective_active_task or resolved_task or task
        return ("retry_previous_action", target_intent, resolved)

    # 5. Unambiguous Refinements (e.g. 'make it with daylight', 'add sunglasses')
    refine_phrases = ("make it", "change it", "update it", "modify it", "redo it", "add to it", "with daylight", "with studio", "render it")
    if effective_active_task and any(rp in t for rp in refine_phrases):
        target_intent = effective_active_intent or (intent if intent != "conversation" else "image_generation")
        resolved = f"{effective_active_task} - {task}" if effective_active_task not in task else task
        return ("refine_previous_result", target_intent, resolved)

    # 6. Reconcile contradictory LLM outputs:
    # If category is retry/refine but intent was returned as conversation -> restore target tool intent
    if category in ("retry_previous_action", "refine_previous_result") and intent == "conversation":
        target_intent = effective_active_intent or "image_generation"
        resolved = effective_active_task or resolved_task or task
        return (category, target_intent, resolved)

    # If category is status/follow_up/inspect but intent was a tool -> force conversation
    if category in ("status_question", "follow_up_question", "inspect_previous_result"):
        return (category, "conversation", task)

    return (category, intent, resolved_task)


def classify_intent_with_fallback(
    task: str,
    messages: List[BaseMessage],
    workspace_root: str,
    active_task: Optional[str] = None,
    active_intent: Optional[TaskType] = None,
    tool_history: Optional[List[ToolExecutionRecord]] = None,
) -> Tuple[FollowUpCategory, TaskType, str]:
    """
    Classifies user intent using structured LLM call with multi-turn context,
    reconciles against authoritative rules, and falls back gracefully.
    Returns (category, intent, resolved_task).
    """
    try:
        llm = get_cached_llm()

        # Build compact history summary for the classifier
        history_snippets = []
        for msg in messages[-6:]:
            m_type = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                prefix = "User: " if m_type == "human" else "Assistant: "
                clean_c = content.split("User Task:\n")[-1].strip() if "User Task:\n" in content else content
                history_snippets.append(f"{prefix}{clean_c[:200]}")

        context_block = "\n".join(history_snippets) if history_snippets else "None"

        # Build tool execution history summary
        tool_records_summary = "None"
        if tool_history:
            recent_records = []
            for rec in tool_history[-4:]:
                tool_name = rec.get("tool_name", "tool")
                status = rec.get("status", "unknown")
                args_str = json.dumps(rec.get("input_args", {}))[:150]
                art = rec.get("artifact_path") or "none"
                recent_records.append(f"- Tool: {tool_name}, Status: {status}, Args: {args_str}, Artifact: {art}")
            tool_records_summary = "\n".join(recent_records)

        prompt = f"""Recent Conversation Context:
{context_block}

Active Task Context:
{active_task or 'None'} (Previous Intent: {active_intent or 'None'})

Recent Tool Execution Records:
{tool_records_summary}

Current User Message:
{task}"""

        response = llm.invoke([
            SystemMessage(content=INTENT_CLASSIFIER_PROMPT),
            HumanMessage(content=prompt),
        ])

        raw_text = response.content if isinstance(response.content, str) else str(response.content)

        # Parse JSON
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            raw_category = data.get("category", "new_request").strip().lower()
            raw_intent = data.get("intent", "conversation").strip().lower()
            raw_resolved = data.get("resolved_task", "").strip() or task

            valid_categories = {"new_request", "follow_up_question", "inspect_previous_result", "refine_previous_result", "retry_previous_action", "status_question"}
            valid_intents = {"conversation", "image_generation", "web_search", "code_question", "code_change", "test_request"}

            category = raw_category if raw_category in valid_categories else "new_request"
            intent = raw_intent if raw_intent in valid_intents else "conversation"

            # Authoritative context-aware validation & reconciliation step
            return validate_and_reconcile_classification(
                task,
                category=category,  # type: ignore
                intent=intent,      # type: ignore
                resolved_task=raw_resolved,
                active_task=active_task,
                active_intent=active_intent,
                tool_history=tool_history,
            )

    except Exception:
        pass

    fallback_cat, fallback_intent, fallback_res = classify_intent_deterministic_fallback(task, active_task=active_task, active_intent=active_intent)
    return validate_and_reconcile_classification(
        task,
        category=fallback_cat,
        intent=fallback_intent,
        resolved_task=fallback_res,
        active_task=active_task,
        active_intent=active_intent,
        tool_history=tool_history,
    )


def route_classified_intent(state: CodingAgentState) -> str:
    """Routes state from classifier to specialized agent node based on validated task_type and follow_up_category."""
    category = state.get("follow_up_category", "new_request")
    task_type = state.get("task_type", "conversation")

    # If the user is asking a status question or inspecting/asking about past results -> Conversation (no tools executed)
    if category in ("follow_up_question", "status_question", "inspect_previous_result"):
        return "conversation"

    # If retrying or refining an action -> route to the appropriate execution node
    if category in ("retry_previous_action", "refine_previous_result"):
        if task_type in ("image_generation", "web_search"):
            return "tool_agent"
        elif task_type == "code_question":
            return "code_inspector"
        elif task_type == "code_change":
            return "planner"
        elif task_type == "test_request":
            return "dedicated_test_runner"

    # Standard new request routing
    if task_type in ("image_generation", "web_search"):
        return "tool_agent"
    elif task_type == "code_question":
        return "code_inspector"
    elif task_type == "code_change":
        return "planner"
    elif task_type == "test_request":
        return "dedicated_test_runner"

    return "conversation"


def should_continue_tool_agent(state: CodingAgentState) -> str:
    """Decides whether tool_agent executes direct action tools or terminates."""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    iterations = state.get("direct_tool_iterations", 0)

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        if len(last_msg.tool_calls) > MAX_TOOL_CALLS_PER_TURN or iterations >= MAX_DIRECT_TOOL_ITERATIONS:
            return "summarizer"
        return "direct_action_tools"

    return "summarizer"


def should_continue_code_inspector(state: CodingAgentState) -> str:
    """Decides whether code_inspector executes read-only tools or terminates."""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    iterations = state.get("inspector_tool_iterations", 0)

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        if len(last_msg.tool_calls) > MAX_TOOL_CALLS_PER_TURN or iterations >= MAX_INSPECTOR_TOOL_ITERATIONS:
            return "summarizer"
        return "read_only_tools"

    return "summarizer"


def should_continue_coder(state: CodingAgentState) -> str:
    """Decides whether coder executes modification tools or proceeds to verification & validation."""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    iterations = state.get("coder_tool_iterations", 0)

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        if len(last_msg.tool_calls) > MAX_TOOL_CALLS_PER_TURN or iterations >= MAX_CODER_TOOL_ITERATIONS:
            return "summarizer"
        return "coder_tools"

    # No tool calls: verify source code and config changes against manifest
    verification = verify_code_changes(
        state.get("workspace_root", str(settings.WORKSPACE_ROOT)),
        state.get("workspace_manifest"),
        state.get("modified_files", []),
    )

    if verification.get("source_changed") or verification.get("config_changed"):
        return "validator"

    return "summarizer"


def should_retry_or_finish(state: CodingAgentState) -> str:
    """Centralized retry gate: strictly enforces MAX_REPAIR_RETRIES invariant."""
    if state.get("test_passed", False):
        return "summarizer"

    max_retries = getattr(settings, "MAX_RETRY_COUNT", MAX_REPAIR_RETRIES)
    if state.get("retry_count", 0) >= max_retries:
        return "summarizer"

    return "fixer"


# Compatibility function for start edge
def route_initial_intent(state: CodingAgentState) -> str:
    return route_classified_intent(state)

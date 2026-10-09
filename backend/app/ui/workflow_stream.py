from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from langchain_core.messages import HumanMessage

import app.ui.markdown_stream  # Ensures boxed rounded tables are registered globally
from app.core.config import settings
from app.core.exceptions import format_error_for_user
from app.core.redis_client import save_session_thread
from app.core.theme import (
    create_banner_panel,
    print_planner_header,
    print_error_badge,
    RICH_THEME,
)
from app.integrations.tools.file_tools import list_directory
from app.modules.coding_agent.nodes import extract_text
from app.ui.shimmer import ShimmerLoader

console = Console(theme=RICH_THEME)



def print_banner():
    """Renders the top welcome banner."""
    active_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
    console.print(create_banner_panel(settings.WORKSPACE_ROOT, settings.DEFAULT_PROVIDER, active_model))


def _format_full_path(path_str: str) -> str:
    """Formats path to normalized full absolute path with forward slashes."""
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.is_absolute():
        p = (settings.WORKSPACE_ROOT / p).resolve()
    else:
        p = p.resolve()
    return str(p).replace("\\", "/")


def _get_shimmer_message_for_tool(name: str, args: Dict[str, Any]) -> str:
    """Generates clean in-progress text for the active tool without redundant path clutter."""
    if name == "read_file":
        return "Reading file..."
    elif name == "write_file":
        return "Writing file..."
    elif name == "patch_file":
        return "Patching file..."
    elif name == "delete_file":
        return "Deleting file..."
    elif name == "list_directory":
        return "Listing files..."
    elif name == "search_code":
        q = args.get("query", "")
        return f"Searching codebase for '{q}'..." if q else "Searching codebase..."
    elif name == "search_web":
        query = args.get("query", "")
        if query:
            return f"Searching web for '{query}'..."
        return "Searching web..."
    elif name == "read_doc_url":
        url = args.get("url", "")
        return f"Fetching docs from {url}..." if url else "Fetching documentation..."
    elif name == "run_git_command":
        return "Running git command..."
    elif name == "run_terminal_command":
        return "Running command..."
    elif name == "inspect_image":
        return "Inspecting image..."
    elif name == "generate_image":
        return "Generating image with Flux/AI..."
    return "Executing action..."


def execute_workflow(
    task: str,
    test_path: Optional[str] = None,
    interactive: bool = True,
    session_id: Optional[str] = None,
    history_messages: Optional[List[Any]] = None,
) -> List[Any]:
    """
    Executes the multi-agent graph stream with green animated shimmer text,
    renders live badges upon completion of each tool, streams LLM markdown responses token-by-token,
    and automatically persists threaded sessions to Redis.
    """
    from app.modules.coding_agent.graph import coding_agent_app
    from app.modules.coding_agent.commands import record_task_in_history
    from app.core.guardrails import extract_prompt_images, extract_prompt_files
    from app.integrations.tools.image_tools import _resolve_safe_image_path, _optimize_and_encode_image
    from app.core.user_config import get_active_mode, get_active_model_name, get_active_provider
    from app.core.redis_client import save_session_thread

    session_auto_accept = (get_active_mode() in ("accept-edits", "auto"))

    try:
        repo_tree = list_directory.invoke({"dir_path": "."})
    except Exception:
        repo_tree = "Unable to retrieve repository file listing."

    clean_task, image_paths = extract_prompt_images(task)
    clean_task, pinned_files = extract_prompt_files(clean_task)

    pinned_context_str = ""
    if pinned_files:
        sections = []
        for pf in pinned_files:
            console.print(f"[bold green]Pinned context:[/] [dim]{pf['path']}[/dim]")
            sections.append(f"--- Pinned {pf['type'].capitalize()}: {pf['path']} ---\n{pf['content']}")
        pinned_context_str = "\n\n" + "\n\n".join(sections)

    attached_images_payload = []
    
    if image_paths:
        for img_p in image_paths:
            resolved_p = _resolve_safe_image_path(img_p)
            if resolved_p.exists():
                try:
                    mime_type, b64_data, meta = _optimize_and_encode_image(resolved_p)
                    attached_images_payload.append({
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{b64_data}",
                        "filename": resolved_p.name,
                        "meta": meta,
                    })
                except Exception:
                    pass

    if attached_images_payload:
        image_summaries = ", ".join([f"{img['filename']} ({img['meta']['original_dimensions']})" for img in attached_images_payload])
        text_content = (
            f"Workspace Root: {settings.WORKSPACE_ROOT}\n\n"
            f"User Task:\n{clean_task}{pinned_context_str}\n\n"
            f"[Attached Image(s): {image_summaries}]"
        )
        msg_parts = [{"type": "text", "text": text_content}]
        for img in attached_images_payload:
            msg_parts.append({
                "type": "image_url",
                "image_url": img["image_url"],
            })
        current_human_msg = HumanMessage(content=msg_parts)
    else:
        current_human_msg = HumanMessage(
            content=(
                f"Workspace Root: {settings.WORKSPACE_ROOT}\n\n"
                f"Repository Structure:\n{repo_tree}\n\n"
                f"User Task:\n{clean_task}{pinned_context_str}"
            )
        )

    # Prepend conversation history and restore tool execution records if resuming
    prior_messages = list(history_messages) if history_messages else []
    initial_messages = prior_messages + [current_human_msg]

    prior_tool_history = []
    prior_active_task = None
    prior_active_intent = None
    prior_active_task_id = None
    if session_id:
        from app.core.redis_client import get_session_thread
        thread_info = get_session_thread(session_id)
        if thread_info:
            meta = thread_info.get("meta", {}) if "meta" in thread_info else thread_info
            prior_tool_history = meta.get("tool_execution_history", [])
            prior_active_task = meta.get("active_task_context")
            prior_active_intent = meta.get("active_task_intent")
            prior_active_task_id = meta.get("active_task_id")

            # Derive active intent from latest tool record if not explicitly stored
            if not prior_active_intent and prior_tool_history:
                for rec in reversed(prior_tool_history):
                    if rec.get("intent") and rec["intent"] != "conversation":
                        prior_active_intent = rec["intent"]
                        break

    initial_state = {
        "task": clean_task,
        "messages": initial_messages,
        "workspace_root": str(settings.WORKSPACE_ROOT),
        "repository_tree": repo_tree,
        "plan": None,
        "coder_findings": [],
        "modified_files": [],
        "tool_execution_history": prior_tool_history,
        "active_task_context": prior_active_task,
        "active_task_intent": prior_active_intent,
        "active_task_id": prior_active_task_id,
        "test_command": test_path or "",
        "test_results": None,
        "test_passed": False,
        "fixer_analysis": None,
        "retry_count": 0,
        "final_summary": None,
    }

    record_task_in_history(task)
    final_messages: List[Any] = list(initial_messages)
    final_test_passed = True
    final_retries = 0
    final_summary_text = ""
    pending_tool_calls: List[Dict[str, Any]] = []

    loader = ShimmerLoader(console=console)
    loader.start("Analyzing task...")

    from app.core.storage import WorkspaceLock
    from app.integrations.tools.terminal_tools import cancel_active_subprocess

    # Concurrency Guard: Acquire atomic workspace lock
    lock_sid = session_id or "default_session"
    ws_lock = WorkspaceLock(settings.WORKSPACE_ROOT)
    if not ws_lock.acquire(lock_sid):
        console.print("[bold yellow]Notice:[/] Another QueryNest session is currently operating on this workspace. Execution queued/prevented.")
        return final_messages

    latest_tool_history = list(prior_tool_history)
    latest_active_task = prior_active_task
    latest_active_intent = prior_active_intent
    latest_active_task_id = prior_active_task_id

    try:
        for payload in coding_agent_app.stream(initial_state, stream_mode="updates"):
            if not isinstance(payload, dict):
                continue

            for node_name, state_update in payload.items():
                if isinstance(state_update, dict):
                    if "tool_execution_history" in state_update:
                        latest_tool_history = state_update["tool_execution_history"]
                    if "active_task_context" in state_update:
                        latest_active_task = state_update["active_task_context"]
                    if "active_task_intent" in state_update:
                        latest_active_intent = state_update["active_task_intent"]
                    if "active_task_id" in state_update:
                        latest_active_task_id = state_update["active_task_id"]

                if node_name == "classifier":
                    loader.start("Routing task...")

                elif node_name == "planner":
                    loader.stop()
                    plan_content = state_update.get("plan", "Plan generated.")
                    print_planner_header(console)
                    console.print(Markdown(plan_content))
                    console.print()

                    # Modular human-in-the-loop permission & confirmation gate
                    if interactive and not session_auto_accept:
                        from app.ui.dialogs import prompt_plan_permission
                        action, feedback = prompt_plan_permission()

                        if action == "cancel":
                            console.print("[#a0a0a0]Workflow cancelled.[/#a0a0a0]")
                            return final_messages
                        elif action == "all":
                            session_auto_accept = True

                    loader.start("Analyzing codebase...")

                elif node_name in ("coder", "tool_agent", "code_inspector"):
                    messages = state_update.get("messages", [])
                    has_tool_calls = False

                    for msg in messages:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            has_tool_calls = True
                            pending_tool_calls = msg.tool_calls
                            loader.stop()

                            if interactive and not session_auto_accept:
                                from app.ui.dialogs import prompt_tool_permission
                                action, feedback = prompt_tool_permission(pending_tool_calls)

                                if action == "cancel":
                                    console.print("[#a0a0a0]Tool execution cancelled.[/#a0a0a0]")
                                    return final_messages
                                elif action == "all":
                                    session_auto_accept = True

                            # Start shimmering with clean action text (e.g. "Reading file...")
                            first_tc = pending_tool_calls[0]
                            action_text = _get_shimmer_message_for_tool(
                                first_tc.get("name", ""),
                                first_tc.get("args", {}),
                            )
                            loader.start(action_text)

                    if not has_tool_calls:
                        loader.start("Analyzing findings...")

                elif node_name in ("tools", "direct_action_tools", "read_only_tools", "coder_tools"):
                    loader.stop()
                    if not interactive or session_auto_accept:
                        from app.ui.renderers import render_action_badge
                        for tc in pending_tool_calls:
                            render_action_badge(tc.get("name", ""), tc.get("args", {}))
                    pending_tool_calls = []
                    loader.start("Analyzing findings...")

                elif node_name in ("validator", "dedicated_test_runner"):
                    passed = state_update.get("test_passed", False)
                    test_results = state_update.get("test_results", "")
                    final_test_passed = passed
                    loader.stop()
                    if passed:
                        console.print("[white]Verification Passed (Exit Code 0)[/white]")
                    else:
                        console.print("[#a0a0a0]Verification Failed[/#a0a0a0]")
                        if test_results:
                            console.print(f"[dim]{test_results[:300]}...[/dim]")
                        loader.start("Diagnosing bug & self-healing...")

                elif node_name == "fixer":
                    retry = state_update.get("retry_count", 1)
                    final_retries = retry
                    loader.stop()
                    console.print(f"[#a0a0a0]Self-Healing Attempt {retry} in progress...[/#a0a0a0]")
                    loader.start("Applying fixes...")

                elif node_name == "summarizer":
                    loader.stop()
                    final_summary_text = state_update.get("final_summary", "")
                    if final_summary_text:
                        from langchain_core.messages import AIMessage
                        final_messages.append(AIMessage(content=final_summary_text))

        # Determine thread title
        thread_title = clean_task[:60] if clean_task else "Session"
        if history_messages and len(history_messages) > 0:
            first_m = history_messages[0]
            first_c = getattr(first_m, "content", "")
            if isinstance(first_c, str) and first_c:
                thread_title = first_c.splitlines()[-1][:60] if "\n" in first_c else first_c[:60]

        if session_id:
            save_session_thread(
                session_id=session_id,
                title=thread_title,
                messages=final_messages,
                meta={
                    "model": get_active_model_name(),
                    "provider": get_active_provider(),
                    "test_passed": final_test_passed,
                    "tool_execution_history": latest_tool_history,
                    "active_task_context": latest_active_task,
                    "active_task_intent": latest_active_intent,
                    "active_task_id": latest_active_task_id,
                },
            )

        return final_messages

    except KeyboardInterrupt:
        loader.stop()
        cancel_active_subprocess()
        console.print("\n[yellow]Execution cancelled by user. Session checkpointed.[/yellow]")
        if session_id:
            try:
                save_session_thread(
                    session_id=session_id,
                    title=clean_task[:60] if clean_task else "Cancelled Session",
                    messages=final_messages,
                )
            except Exception:
                pass
        return final_messages
    except Exception as e:
        loader.stop()
        cancel_active_subprocess()
        err_msg = format_error_for_user(e)
        print_error_badge(console, err_msg)
        return final_messages
    finally:
        loader.stop()
        ws_lock.release(lock_sid)


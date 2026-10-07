from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from langchain_core.messages import HumanMessage

import app.ui.markdown_stream  # Ensures boxed rounded tables are registered globally
from app.core.config import settings
from app.core.exceptions import format_error_for_user
from app.core.redis_client import save_session_record
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
    elif name == "delete_file":
        return "Deleting file..."
    elif name == "list_directory":
        return "Listing files..."
    elif name == "search_web":
        query = args.get("query", "")
        if query:
            return f"Searching web for '{query}'..."
        return "Searching web..."
    elif name == "run_git_command":
        return "Running git command..."
    elif name == "run_terminal_command":
        return "Running command..."
    elif name == "inspect_image":
        return "Inspecting image..."
    return "Executing action..."


def execute_workflow(task: str, test_path: Optional[str] = None, interactive: bool = True):
    """
    Executes the multi-agent graph stream with green animated shimmer text,
    renders live badges upon completion of each tool, streams LLM markdown responses token-by-token,
    and automatically persists sessions to Redis.
    """
    from app.modules.coding_agent.graph import coding_agent_app
    from app.modules.coding_agent.commands import record_task_in_history
    from app.core.guardrails import extract_prompt_images
    from app.integrations.tools.image_tools import _resolve_safe_image_path, _optimize_and_encode_image

    try:
        repo_tree = list_directory.invoke({"dir_path": "."})
    except Exception:
        repo_tree = "Unable to retrieve repository file listing."

    clean_task, image_paths = extract_prompt_images(task)
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
            f"User Task:\n{clean_task}\n\n"
            f"[Attached Image(s): {image_summaries}]"
        )
        msg_parts = [{"type": "text", "text": text_content}]
        for img in attached_images_payload:
            msg_parts.append({
                "type": "image_url",
                "image_url": img["image_url"],
            })
        initial_human_msg = HumanMessage(content=msg_parts)
    else:
        initial_human_msg = HumanMessage(
            content=(
                f"Workspace Root: {settings.WORKSPACE_ROOT}\n\n"
                f"Repository Structure:\n{repo_tree}\n\n"
                f"User Task:\n{task}"
            )
        )

    initial_state = {
        "task": task,
        "messages": [initial_human_msg],
        "workspace_root": str(settings.WORKSPACE_ROOT),
        "repository_tree": repo_tree,
        "plan": None,
        "coder_findings": [],
        "modified_files": [],
        "test_command": test_path or "",
        "test_results": None,
        "test_passed": False,
        "fixer_analysis": None,
        "retry_count": 0,
        "final_summary": None,
    }

    record_task_in_history(task)
    final_test_passed = True
    final_retries = 0
    final_summary_text = ""
    pending_tool_calls: List[Dict[str, Any]] = []

    loader = ShimmerLoader(console=console)
    loader.start("Analyzing task...")

    try:
        for payload in coding_agent_app.stream(initial_state, stream_mode="updates"):
            if not isinstance(payload, dict):
                continue

            for node_name, state_update in payload.items():

                if node_name == "planner":
                    loader.stop()
                    plan_content = state_update.get("plan", "Plan generated.")
                    print_planner_header(console)
                    console.print(Markdown(plan_content))
                    console.print()

                    # Modular human-in-the-loop permission & confirmation gate
                    if interactive:
                        from app.ui.dialogs import prompt_plan_permission
                        action, feedback = prompt_plan_permission()

                        if action == "cancel":
                            console.print("[#a0a0a0]Workflow cancelled.[/#a0a0a0]")
                            return
                        elif action == "adjust" and feedback:
                            console.print("[#a0a0a0]Updating plan with instructions...[/#a0a0a0]")
                            return execute_workflow(
                                f"{task}\n\nUser Adjustments/Instructions: {feedback}",
                                test_path=test_path,
                                interactive=interactive,
                            )

                    loader.start("Analyzing codebase...")

                elif node_name == "coder":
                    messages = state_update.get("messages", [])
                    has_tool_calls = False

                    for msg in messages:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            has_tool_calls = True
                            pending_tool_calls = msg.tool_calls
                            loader.stop()

                            if interactive:
                                from app.ui.dialogs import prompt_tool_permission
                                action, feedback = prompt_tool_permission(pending_tool_calls)

                                if action == "cancel":
                                    console.print("[#a0a0a0]Tool execution cancelled.[/#a0a0a0]")
                                    return
                                elif action == "adjust" and feedback:
                                    console.print("[#a0a0a0]Updating workflow with instructions...[/#a0a0a0]")
                                    return execute_workflow(
                                        f"{task}\n\nUser Adjustments/Instructions: {feedback}",
                                        test_path=test_path,
                                        interactive=interactive,
                                    )

                            # Start shimmering with clean action text (e.g. "Reading file...")
                            first_tc = pending_tool_calls[0]
                            action_text = _get_shimmer_message_for_tool(
                                first_tc.get("name", ""),
                                first_tc.get("args", {}),
                            )
                            loader.start(action_text)

                    if not has_tool_calls:
                        loader.stop()

                elif node_name == "tools":
                    loader.stop()
                    if not interactive:
                        from app.ui.renderers import render_action_badge
                        for tc in pending_tool_calls:
                            render_action_badge(tc.get("name", ""), tc.get("args", {}))
                    pending_tool_calls = []
                    loader.start("Analyzing findings...")

                elif node_name == "validator":
                    passed = state_update.get("test_passed", False)
                    test_results = state_update.get("test_results", "")
                    final_test_passed = passed
                    loader.stop()
                    if passed:
                        console.print("\n[white]Pytest Verification Passed (Exit Code 0)[/white]\n")
                    else:
                        console.print("\n[#a0a0a0]Pytest Verification Failed[/#a0a0a0]")
                        if test_results:
                            console.print(f"[dim]{test_results[:300]}...[/dim]\n")
                        loader.start("Diagnosing bug & self-healing...")

                elif node_name == "fixer":
                    retry = state_update.get("retry_count", 1)
                    final_retries = retry
                    loader.stop()
                    console.print(f"\n[#a0a0a0]Self-Healing Attempt {retry} in progress...[/#a0a0a0]\n")
                    loader.start("Applying fixes...")

                elif node_name == "summarizer":
                    loader.stop()
                    final_summary_text = state_update.get("final_summary", "")
                    if final_summary_text:
                        console.print()
                        console.print(Markdown(final_summary_text))
                        console.print()

        # Record completed session to Redis
        save_session_record({
            "task": task,
            "model": settings.DEFAULT_PROVIDER,
            "test_passed": final_test_passed,
            "retries": final_retries,
            "summary": final_summary_text[:300] if final_summary_text else "Completed",
        })

    except Exception as e:
        loader.stop()
        err_msg = format_error_for_user(e)
        print_error_badge(console, err_msg)
    finally:
        loader.stop()

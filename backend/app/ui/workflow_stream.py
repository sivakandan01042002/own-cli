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
)
from app.integrations.tools.file_tools import list_directory
from app.modules.coding_agent.nodes import extract_text
from app.ui.shimmer import ShimmerLoader

console = Console()


def print_banner():
    """Renders the top welcome banner."""
    active_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
    console.print(create_banner_panel(settings.WORKSPACE_ROOT, settings.DEFAULT_PROVIDER, active_model))


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
    elif name == "run_terminal_command":
        return "Running command..."
    return "Executing action..."


def _print_completed_tool_badge(name: str, args: Dict[str, Any]):
    """Prints the permanent flush-left action badge upon tool execution completion."""
    if name == "read_file":
        path = args.get("file_path", "")
        console.print(f"[bold yellow]Read:[/] [bold white]{path}[/bold white]")
    elif name == "write_file":
        path = args.get("file_path", "")
        console.print(f"[bold yellow]Write:[/] [bold white]{path}[/bold white]")
    elif name == "delete_file":
        path = args.get("file_path", "")
        console.print(f"[bold yellow]Delete:[/] [bold white]{path}[/bold white]")
    elif name == "list_directory":
        path = args.get("dir_path", ".")
        console.print(f"[bold yellow]List:[/] [bold white]{path}[/bold white]")
    elif name == "run_terminal_command":
        cmd = args.get("command", "")
        console.print(f"[bold yellow]Bash:[/] [bold white]{cmd}[/bold white]")


def execute_workflow(task: str, test_path: Optional[str] = None):
    """
    Executes the multi-agent graph stream with green animated shimmer text,
    renders live badges upon completion of each tool, streams LLM markdown responses token-by-token,
    and automatically persists sessions to Redis.
    """
    from app.modules.coding_agent.graph import coding_agent_app
    from app.modules.coding_agent.commands import record_task_in_history

    try:
        repo_tree = list_directory.invoke({"dir_path": "."})
    except Exception:
        repo_tree = "Unable to retrieve repository file listing."

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

    summarizer_live: Optional[Live] = None
    accumulated_summary = ""

    loader = ShimmerLoader(console=console)
    loader.start("Analyzing task...")

    try:
        for mode, payload in coding_agent_app.stream(initial_state, stream_mode=["updates", "messages"]):
            if mode == "messages":
                msg, metadata = payload
                node = metadata.get("langgraph_node")
                if node == "summarizer":
                    if summarizer_live is None:
                        loader.stop()
                        console.print()
                        summarizer_live = Live(Markdown(""), console=console, refresh_per_second=15, transient=False)
                        summarizer_live.start()
                    token = extract_text(getattr(msg, "content", ""))
                    if token:
                        accumulated_summary += token
                        summarizer_live.update(Markdown(accumulated_summary))

            elif mode == "updates":
                for node_name, state_update in payload.items():

                    if node_name == "planner":
                        loader.stop()
                        plan_content = state_update.get("plan", "Plan generated.")
                        print_planner_header(console)
                        console.print(Markdown(plan_content))
                        console.print()
                        loader.start("Analyzing codebase...")

                    elif node_name == "coder":
                        messages = state_update.get("messages", [])
                        has_tool_calls = False

                        for msg in messages:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                has_tool_calls = True
                                pending_tool_calls = msg.tool_calls
                                # Start shimmering with clean action text (e.g. "Reading file...")
                                first_tc = pending_tool_calls[0]
                                action_text = _get_shimmer_message_for_tool(
                                    first_tc.get("name", ""),
                                    first_tc.get("args", {}),
                                )
                                loader.start(action_text)

                        if not has_tool_calls:
                            # Stop loader cleanly before Summarizer node streams tokens to stdout
                            loader.stop()

                    elif node_name == "tools":
                        # Tool physically completed execution -> Print permanent badges
                        loader.stop()
                        for tc in pending_tool_calls:
                            _print_completed_tool_badge(tc.get("name", ""), tc.get("args", {}))
                        pending_tool_calls = []
                        # Resume with contextual "Analyzing findings..." while Coder processes outputs
                        loader.start("Analyzing findings...")

                    elif node_name == "validator":
                        passed = state_update.get("test_passed", False)
                        test_results = state_update.get("test_results", "")
                        final_test_passed = passed
                        loader.stop()
                        if passed:
                            console.print("\n[bold green]✅ Pytest Verification Passed (Exit Code 0)[/bold green]\n")
                        else:
                            console.print("\n[bold red]❌ Pytest Verification Failed[/bold red]")
                            if test_results:
                                console.print(f"[dim red]{test_results[:300]}...[/dim red]\n")
                            loader.start("Diagnosing bug & self-healing...")

                    elif node_name == "fixer":
                        retry = state_update.get("retry_count", 1)
                        final_retries = retry
                        loader.stop()
                        console.print(f"[bold magenta]🔄 Self-Healing Attempt {retry} in progress...[/bold magenta]")
                        loader.start("Applying fixes...")

                    elif node_name == "summarizer":
                        loader.stop()
                        summary = state_update.get("final_summary", "")
                        final_summary_text = summary or accumulated_summary
                        if summarizer_live is not None:
                            summarizer_live.update(Markdown(final_summary_text))
                            summarizer_live.stop()
                            summarizer_live = None
                            console.print()
                        elif final_summary_text:
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
        if summarizer_live is not None:
            summarizer_live.stop()
            summarizer_live = None
        err_msg = format_error_for_user(e)
        print_error_badge(console, err_msg)
    finally:
        loader.stop()
        if summarizer_live is not None:
            summarizer_live.stop()
            summarizer_live = None

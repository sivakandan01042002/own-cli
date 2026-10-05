from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.exceptions import format_error_for_user
from app.core.redis_client import save_session_record
from app.core.theme import (
    create_banner_panel,
    print_planner_header,
    print_error_badge,
)
from app.integrations.tools.file_tools import list_directory
from app.modules.coding_agent import (
    coding_agent_app,
    record_task_in_history,
)
from app.ui.shimmer import ShimmerLoader

console = Console()


def print_banner():
    """Renders the top welcome banner."""
    active_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
    console.print(create_banner_panel(settings.WORKSPACE_ROOT, settings.DEFAULT_PROVIDER, active_model))


def execute_workflow(task: str, test_path: Optional[str] = None):
    """
    Executes the multi-agent graph stream with animated cement/shimmer text,
    renders live badges upon completion, and automatically persists sessions to Redis.
    """
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

    loader = ShimmerLoader(console=console)
    loader.start("Thinking...")

    try:
        for event in coding_agent_app.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in event.items():

                if node_name == "planner":
                    loader.stop()
                    plan_content = state_update.get("plan", "Plan generated.")
                    print_planner_header(console)
                    console.print(Markdown(plan_content))
                    console.print()
                    loader.start("Thinking...")

                elif node_name == "coder":
                    messages = state_update.get("messages", [])
                    has_tool_calls = False
                    next_shimmer = "Thinking..."

                    for msg in messages:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            has_tool_calls = True
                            loader.stop()
                            for tc in msg.tool_calls:
                                name = tc.get("name", "")
                                args = tc.get("args", {})
                                if name == "read_file":
                                    path = args.get("file_path", "")
                                    console.print(f"[bold yellow]Read:[/] [bold white]{path}[/bold white]")
                                    next_shimmer = f"Reading {path}..."
                                elif name == "write_file":
                                    path = args.get("file_path", "")
                                    console.print(f"[bold yellow]Write:[/] [bold white]{path}[/bold white]")
                                    next_shimmer = f"Writing {path}..."
                                elif name == "delete_file":
                                    path = args.get("file_path", "")
                                    console.print(f"[bold yellow]Delete:[/] [bold white]{path}[/bold white]")
                                    next_shimmer = f"Deleting {path}..."
                                elif name == "list_directory":
                                    path = args.get("dir_path", ".")
                                    console.print(f"[bold yellow]List:[/] [bold white]{path}[/bold white]")
                                    next_shimmer = f"Listing files in {path}..."
                                elif name == "search_web":
                                    query = args.get("query", "")
                                    console.print(f"[bold yellow]Search:[/] [bold white]{query}[/bold white]")
                                    next_shimmer = f"Searching web for {query}..."
                                elif name == "run_terminal_command":
                                    cmd = args.get("command", "")
                                    console.print(f"[bold yellow]Bash:[/] [bold white]{cmd}[/bold white]")
                                    next_shimmer = f"Running {cmd}..."
                            loader.start(next_shimmer)

                    if not has_tool_calls:
                        # Stop loader cleanly before Summarizer node streams tokens to stdout
                        loader.stop()

                elif node_name == "tools":
                    loader.start("Thinking...")

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
                        loader.start("🩹 Diagnosing bug & self-healing...")

                elif node_name == "fixer":
                    retry = state_update.get("retry_count", 1)
                    final_retries = retry
                    loader.stop()
                    console.print(f"[bold magenta]🔄 Self-Healing Attempt {retry} in progress...[/bold magenta]")
                    loader.start("Applying fixes...")

                elif node_name == "summarizer":
                    loader.stop()
                    summary = state_update.get("final_summary", "")
                    final_summary_text = summary

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

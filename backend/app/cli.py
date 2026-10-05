import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from langchain_core.messages import HumanMessage
from prompt_toolkit.layout.containers import HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer, Completion

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.core.config import settings
from app.core.guardrails import triage_user_input
from app.core.exceptions import format_error_for_user
from app.core.redis_client import save_session_record
from app.core.theme import (
    CLI_STYLE,
    DIVIDER,
    create_banner_panel,
    create_planner_panel,
    create_summary_panel,
    create_error_panel,
)
from app.integrations.tools.file_tools import list_directory
from app.modules.coding_agent import (
    coding_agent_app,
    dispatch_command,
    record_task_in_history,
)

# CLI Application & Console Setup
app = typer.Typer(help="QueryNest Multi-Agent Coding CLI", add_completion=False)
console = Console()


class SlashCommandCompleter(Completer):
    """Autocomplete for slash commands with rich metadata descriptions."""
    COMMANDS = [
        ("/help", "Display command guide"),
        ("/session", "List past coding sessions stored in Redis"),
        ("/sessions", "List past coding sessions stored in Redis"),
        ("/model", "Show active LLM provider"),
        ("/model gemini", "Switch to Google Gemini 3.8 Flash"),
        ("/model groq", "Switch to Groq GPT-OSS 120B"),
        ("/tools", "Inspect registered agent tools"),
        ("/history", "View session task history"),
        ("/clear", "Clear terminal screen"),
        ("/exit", "Quit QueryNest"),
    ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd, desc in self.COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)


class FramedPromptSession:
    """Interactive prompt that dynamically wraps and expands with text while keeping framing dividers locked."""
    def __init__(self, completer: Optional[Completer] = None, style=None):
        self.completer = completer
        self.style = style

    def prompt(self) -> str:
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            event.app.exit(result=event.app.current_buffer.text)

        @kb.add("c-c")
        @kb.add("c-d")
        def _(event):
            event.app.exit(exception=KeyboardInterrupt)

        all_kb = merge_key_bindings([load_key_bindings(), kb])

        buf = Buffer(
            completer=self.completer,
            complete_while_typing=True,
        )

        def _get_line_prefix(line_no: int, wrap_count: int):
            if line_no == 0 and wrap_count == 0:
                return [("class:prompt", "❯ ")]
            return [("class:prompt", "  ")]

        root = HSplit([
            Window(FormattedTextControl([("class:divider", DIVIDER)]), height=1, dont_extend_height=True),
            FloatContainer(
                content=Window(
                    BufferControl(buffer=buf),
                    get_line_prefix=_get_line_prefix,
                    wrap_lines=True,
                    dont_extend_height=True,
                ),
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=8, scroll_offset=1),
                    )
                ],
            ),
            Window(FormattedTextControl([("class:divider", DIVIDER)]), height=1, dont_extend_height=True),
        ])

        app = Application(
            layout=Layout(root),
            key_bindings=all_kb,
            style=self.style,
            full_screen=False,
            erase_when_done=False,
        )

        return app.run()


def _print_banner():
    active_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
    console.print(create_banner_panel(settings.WORKSPACE_ROOT, settings.DEFAULT_PROVIDER, active_model))


def execute_workflow(task: str, test_path: Optional[str] = None):
    """Executes the multi-agent graph, streams updates, and saves session in Redis."""
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

    with console.status("[bold green]Thinking...[/bold green]", spinner="dots") as status:
        try:
            for event in coding_agent_app.stream(initial_state, stream_mode="updates"):
                for node_name, state_update in event.items():

                    if node_name == "planner":
                        status.stop()
                        plan_content = state_update.get("plan", "Plan generated.")
                        console.print(create_planner_panel(plan_content))
                        status.start()
                        status.update("[bold yellow]💻 Coder is inspecting project & writing code...[/bold yellow]")

                    elif node_name == "coder":
                        messages = state_update.get("messages", [])
                        for msg in messages:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    name = tc.get("name", "")
                                    args = tc.get("args", {})
                                    if name == "read_file":
                                        path = args.get("file_path", "")
                                        console.print(f"  📖 [dim cyan]Read file:[/] [bold]{path}[/bold]")
                                    elif name == "write_file":
                                        path = args.get("file_path", "")
                                        console.print(f"  📝 [dim green]Created/Updated file:[/] [bold]{path}[/bold]")
                                    elif name == "delete_file":
                                        path = args.get("file_path", "")
                                        console.print(f"  🗑️ [dim red]Deleted file:[/] [bold]{path}[/bold]")
                                    elif name == "list_directory":
                                        path = args.get("dir_path", ".")
                                        console.print(f"  📁 [dim cyan]Inspected directory:[/] [bold]{path}[/bold]")
                                    elif name == "search_web":
                                        query = args.get("query", "")
                                        console.print(f"  🔍 [dim yellow]Searched web:[/] [bold]{query}[/bold]")
                                    elif name == "run_terminal_command":
                                        cmd = args.get("command", "")
                                        console.print(f"  ⚡ [dim magenta]Executed command:[/] [bold]{cmd}[/bold]")

                    elif node_name == "tools":
                        status.update("[bold cyan]Processing tool results...[/bold cyan]")

                    elif node_name == "validator":
                        passed = state_update.get("test_passed", False)
                        test_results = state_update.get("test_results", "")
                        final_test_passed = passed
                        if passed:
                            console.print("\n  [bold green]✅ Pytest Verification Passed (Exit Code 0)[/bold green]")
                        else:
                            console.print("\n  [bold red]❌ Pytest Verification Failed[/bold red]")
                            if test_results:
                                console.print(f"  [dim red]{test_results[:300]}...[/dim red]")
                            status.update("[bold magenta]🩹 Fixer is diagnosing bug & self-healing...[/bold magenta]")

                    elif node_name == "fixer":
                        retry = state_update.get("retry_count", 1)
                        final_retries = retry
                        console.print(f"  [bold magenta]🔄 Self-Healing Attempt {retry} in progress...[/bold magenta]")
                        status.update("[bold yellow]💻 Coder is applying fixes...[/bold yellow]")

                    elif node_name == "summarizer":
                        status.stop()
                        summary = state_update.get("final_summary", "Task Completed.")
                        final_summary_text = summary
                        console.print(create_summary_panel(summary))
                        status.start()

            # Record completed session to Redis
            save_session_record({
                "task": task,
                "model": settings.DEFAULT_PROVIDER,
                "test_passed": final_test_passed,
                "retries": final_retries,
                "summary": final_summary_text[:300] if final_summary_text else "Completed",
            })

        except Exception as e:
            status.stop()
            err_msg = format_error_for_user(e)
            console.print(create_error_panel(err_msg))


@app.command()
def chat():
    """Starts the interactive QueryNest CLI session."""
    _print_banner()
    session = FramedPromptSession(
        completer=SlashCommandCompleter(),
        style=CLI_STYLE,
    )

    while True:
        try:
            print()
            user_input = session.prompt()
            if user_input is None:
                continue
            user_input = user_input.strip()

            if not user_input:
                continue

            category, payload = triage_user_input(user_input)

            if category == "command":
                dispatch_command(payload)
            elif category == "greeting":
                console.print(Panel(Markdown(payload), border_style="cyan", title="[bold]QueryNest[/bold]"))
            elif category == "unsafe":
                console.print(Panel(Markdown(payload), border_style="red", title="[bold]Safety Guardrail[/bold]"))
            elif category == "task":
                execute_workflow(payload)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]👋 Session closed. Goodbye![/bold yellow]")
            break


@app.command()
def run(
    task: str = typer.Argument(..., help="The coding task description to execute"),
    test_path: Optional[str] = typer.Option(None, "--test-path", "-t", help="Specific pytest path to target"),
):
    """Executes a single coding task from the command line and exits."""
    _print_banner()
    category, payload = triage_user_input(task)
    if category == "task":
        execute_workflow(payload, test_path=test_path)
    else:
        console.print(payload)


if __name__ == "__main__":
    app()

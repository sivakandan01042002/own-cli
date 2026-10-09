import sys
import warnings

# Suppress library deprecation and AFC runtime notices globally
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console


# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.core.guardrails import triage_user_input
from app.core.theme import CLI_STYLE, RICH_THEME
from app.modules.coding_agent import dispatch_command
from app.ui import (
    FramedPromptSession,
    SlashCommandCompleter,
    execute_workflow,
    print_banner,
)

import os
import uuid
from datetime import datetime
from app.core.redis_client import get_session_thread, deserialize_message
from app.ui.dialogs import ensure_workspace_trusted_gate

# CLI Application & Console Setup
app = typer.Typer(help="QueryNest Multi-Agent Coding CLI", add_completion=False)
console = Console(theme=RICH_THEME)


def ensure_default_environment():
    """Creates default workspace folders and global user config if missing."""
    try:
        (Path.cwd() / "assets").mkdir(parents=True, exist_ok=True)
        (Path.cwd() / ".querynest_cache").mkdir(parents=True, exist_ok=True)

        user_config_dir = Path.home() / ".querynest"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        user_env = user_config_dir / ".env"
        if not user_env.exists() and not (Path.cwd() / ".env").exists():
            user_env.write_text(
                "# QueryNest Global Configuration\n"
                "GEMINI_API_KEY=\n"
                "GROQ_API_KEY=\n"
                "DEFAULT_PROVIDER=gemini\n"
                "REDIS_URL=redis://localhost:6379/0\n",
                encoding="utf-8"
            )
    except Exception:
        pass


@app.callback(invoke_without_command=True)
def default_entrypoint(ctx: typer.Context):
    """Default invocation: running 'querynest' without subcommands launches interactive chat."""
    ensure_default_environment()
    if ctx.invoked_subcommand is None:
        chat()


def _generate_session_id() -> str:
    """Generates a clean timestamped session ID."""
    return f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


@app.command()
def chat():
    """Starts the interactive QueryNest CLI session with multi-turn memory."""
    ensure_default_environment()
    ensure_workspace_trusted_gate()
    print_banner()

    session = FramedPromptSession(
        completer=SlashCommandCompleter(),
        style=CLI_STYLE,
    )

    current_session_id = _generate_session_id()
    current_session_messages = []
    prefill_text = ""

    while True:
        try:
            user_input = session.prompt(default=prefill_text)
            prefill_text = ""
            if user_input is None:
                continue
            user_input = user_input.strip()
            if not user_input:
                continue

            category, payload = triage_user_input(user_input)

            if category == "command":
                action = dispatch_command(payload)
                if action == "__new_session__":
                    current_session_id = _generate_session_id()
                    current_session_messages = []
                    console.print("[bold green]Started a new conversation session.[/bold green]")
                elif action and action.startswith("__restore_session__:"):
                    target_sid = action.split(":", 1)[1]
                    thread_data = get_session_thread(target_sid)
                    if thread_data:
                        current_session_id = target_sid
                        raw_msgs = thread_data.get("messages", [])
                        current_session_messages = [deserialize_message(m) for m in raw_msgs]
                        from rich.markdown import Markdown
                        cols = console.size.width or 80
                        divider = "─" * min(cols, 100)
                        for m in current_session_messages:
                            m_type = getattr(m, "type", "")
                            m_cls = m.__class__.__name__
                            if m_type == "human" or m_cls == "HumanMessage":
                                raw_c = m.content if isinstance(m.content, str) else str(m.content)
                                if "User Task:\n" in raw_c:
                                    clean_c = raw_c.split("User Task:\n")[-1].strip()
                                elif "User Task:" in raw_c:
                                    clean_c = raw_c.split("User Task:")[-1].strip()
                                else:
                                    clean_c = raw_c.strip()
                                console.print(f"[#404040]{divider}[/#404040]")
                                console.print(f"[bold #0099ff]❯[/] [white]{clean_c}[/white]")
                                console.print(f"[#404040]{divider}[/#404040]")
                            elif m_type == "ai" or m_cls == "AIMessage":
                                raw_c = m.content if isinstance(m.content, str) else str(m.content)
                                if raw_c.strip():
                                    console.print(Markdown(raw_c.strip()))
                                    console.print()
                elif action:
                    prefill_text = action
            elif category == "greeting":
                console.print(f"{payload}")
            elif category == "unsafe":
                console.print(f"[bold red]Safety Guardrail:[/] {payload}")
            elif category == "task":
                result_messages = execute_workflow(
                    payload,
                    interactive=True,
                    session_id=current_session_id,
                    history_messages=current_session_messages,
                )
                if result_messages:
                    current_session_messages = result_messages

        except (KeyboardInterrupt, EOFError):
            break



@app.command()
def run(
    task: str = typer.Argument(..., help="The coding task description to execute"),
    test_path: Optional[str] = typer.Option(None, "--test-path", "-t", help="Specific pytest path to target"),
):
    """Executes a single coding task from the command line and exits."""
    ensure_workspace_trusted_gate()
    print_banner()
    category, payload = triage_user_input(task)

    if category == "task":
        execute_workflow(payload, test_path=test_path, interactive=False)
    else:
        console.print(payload)


def main():
    """Main entrypoint for pip package console_scripts."""
    app()


if __name__ == "__main__":
    main()

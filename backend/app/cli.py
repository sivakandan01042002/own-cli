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

# CLI Application & Console Setup
app = typer.Typer(help="QueryNest Multi-Agent Coding CLI", add_completion=False)
console = Console(theme=RICH_THEME)



@app.command()
def chat():
    """Starts the interactive QueryNest CLI session."""
    print_banner()
    session = FramedPromptSession(
        completer=SlashCommandCompleter(),
        style=CLI_STYLE,
    )

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
                selected = dispatch_command(payload)
                if selected:
                    prefill_text = selected
            elif category == "greeting":
                console.print(f"{payload}")
            elif category == "unsafe":
                console.print(f"[bold red]⚠️ Safety Guardrail:[/] {payload}")
            elif category == "task":
                execute_workflow(payload, interactive=True)

        except (KeyboardInterrupt, EOFError):
            break



@app.command()
def run(
    task: str = typer.Argument(..., help="The coding task description to execute"),
    test_path: Optional[str] = typer.Option(None, "--test-path", "-t", help="Specific pytest path to target"),
):
    """Executes a single coding task from the command line and exits."""
    print_banner()
    category, payload = triage_user_input(task)
    if category == "task":
        execute_workflow(payload, test_path=test_path, interactive=False)
    else:
        console.print(payload)


if __name__ == "__main__":
    app()

"""
main.py
FieldAgent entry point.
Initializes the database and runs the agent loop.

Usage:
    python main.py              # Run agent loop (respects DRY_RUN setting)
    python main.py --seed       # Seed database with sample data then exit
    python main.py --dry-run    # Force dry run (generate but don't send)
"""

import sys
from rich.console import Console
from rich.panel import Panel
from core.config import config
from core.database import init_db

console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold green]FieldAgent[/bold green]\n"
        "[dim]AI-powered reengagement platform for field service contractors[/dim]\n\n"
        f"  Environment: [yellow]{config.APP_ENV}[/yellow]\n"
        f"  Dry Run:     [yellow]{config.DRY_RUN}[/yellow]\n"
        f"  Model:       [yellow]{config.CLAUDE_MODEL}[/yellow]",
        border_style="green"
    ))


def main():
    args = sys.argv[1:]

    print_banner()

    # Validate config
    try:
        config.validate()
    except EnvironmentError as e:
        console.print(f"[red]❌ Config error: {e}[/red]")
        console.print("[dim]Copy .env.example to .env and fill in your API keys.[/dim]")
        sys.exit(1)

    # Initialize database
    init_db()

    # Seed mode
    if "--seed" in args:
        from data.seed import seed
        seed()
        return

    # Force dry run override
    if "--dry-run" in args:
        config.DRY_RUN = True
        console.print("[yellow]⚠️  Dry run mode forced via CLI flag.[/yellow]")

    if config.DRY_RUN:
        console.print("[yellow]📋 DRY RUN — messages will be generated but not sent.[/yellow]")

    console.print("\n[bold]Agents available:[/bold]")
    console.print("  [dim]Phase 2: tone_profiler — coming soon[/dim]")
    console.print("  [dim]Phase 3: reactivation  — coming soon[/dim]")
    console.print("  [dim]Phase 4: follow_up     — coming soon[/dim]")
    console.print("\n[green]✅ FieldAgent initialized. Build Phase 1 complete.[/green]")
    console.print("[dim]See PROJECT_PLAN.md for next steps.[/dim]")


if __name__ == "__main__":
    main()

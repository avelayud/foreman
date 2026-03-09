"""
agents/tone_profiler.py
Analyzes an operator's Gmail sent mail to extract their writing voice,
stores the profile on the Operator record, and generates 3 sample
reactivation emails written in that voice.

Usage:
    python -m agents.tone_profiler --operator-id 1
"""

import argparse
import json
import sys
from rich.console import Console
from rich.panel import Panel
from rich.pretty import pprint

import anthropic
from core.config import config
from core.database import get_db
from core.models import Operator
from integrations.gmail import get_sent_emails

console = Console()

# ── Prompts ──────────────────────────────────────────────────────────────────

VOICE_EXTRACTION_SYSTEM = """
You are an expert writing-style analyst. You will be given a set of real emails
written by a small business owner. Your job is to extract a detailed voice profile
that captures how this person naturally communicates in writing.

Respond ONLY with a valid JSON object — no markdown, no commentary, no code fences.

The JSON must have exactly these keys:
{
  "formality": "casual" | "semi-formal" | "formal",
  "greeting_style": "<example greeting they use, e.g. 'Hey [name],' or 'Hi there,'>",
  "signoff_style": "<example signoff they use, e.g. 'Thanks, Mike' or 'Best,'>",
  "sentence_length": "short" | "medium" | "long" | "mixed",
  "humor": true | false,
  "emoji_usage": "none" | "occasional" | "frequent",
  "regional_phrases": ["<phrase1>", "<phrase2>"],
  "characteristic_phrases": ["<phrase1>", "<phrase2>", "<phrase3>"],
  "punctuation_style": "<description, e.g. 'minimal punctuation, rarely uses commas'>",
  "summary": "<2-3 sentence plain-English summary of this person's writing style>"
}
""".strip()

VOICE_EXTRACTION_USER = """
Here are {n} emails written by this business owner. Analyze them and return the voice profile JSON.

--- EMAILS START ---
{emails}
--- EMAILS END ---
""".strip()

SAMPLE_EMAIL_SYSTEM = """
You are a ghostwriter for a small field service business owner.
You write reactivation emails exactly in the owner's voice — using their natural tone,
greeting style, signoff, sentence length, and characteristic phrases.

The goal of each email is to re-engage a past customer who hasn't booked service in over a year.
Emails should feel personal and genuine, never salesy or pushy.
Each email should be short (3–5 sentences max), direct, and end with a soft call to action.

Voice profile to follow:
{voice_profile_json}
""".strip()

SAMPLE_EMAIL_USER = """
Write 3 distinct reactivation emails for a past HVAC customer named {customer_name},
whose last service was a "{last_service}" about {months_ago} months ago.
The emails should vary in approach: one warm check-in, one seasonal angle, one value reminder.

Return a JSON array of 3 objects, each with keys "subject" and "body".
No markdown, no code fences — only the JSON array.
""".strip()


# ── Core logic ────────────────────────────────────────────────────────────────

def extract_voice_profile(emails: list[str]) -> dict:
    """Send emails to Claude and extract a voice profile dict."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Cap at 25 emails, 800 chars each to stay within context limits
    sample = emails[:25]
    combined = "\n\n---\n\n".join(e[:800] for e in sample)

    console.print(f"[dim]Sending {len(sample)} emails to Claude for voice analysis...[/dim]")

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1024,
        system=VOICE_EXTRACTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": VOICE_EXTRACTION_USER.format(
                    n=len(sample),
                    emails=combined
                )
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse voice profile JSON: {e}[/red]")
        console.print(f"[dim]Raw response: {raw[:500]}[/dim]")
        raise

    return profile


def generate_sample_emails(voice_profile: dict, customer_name: str = "Sarah", last_service: str = "AC tune-up", months_ago: int = 14) -> list[dict]:
    """Generate 3 sample reactivation emails using the extracted voice profile."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    console.print(f"[dim]Generating 3 sample reactivation emails in your voice...[/dim]")

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2048,
        system=SAMPLE_EMAIL_SYSTEM.format(
            voice_profile_json=json.dumps(voice_profile, indent=2)
        ),
        messages=[
            {
                "role": "user",
                "content": SAMPLE_EMAIL_USER.format(
                    customer_name=customer_name,
                    last_service=last_service,
                    months_ago=months_ago
                )
            }
        ]
    )

    raw = message.content[0].text.strip()

    try:
        samples = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse sample emails JSON: {e}[/red]")
        console.print(f"[dim]Raw response: {raw[:500]}[/dim]")
        raise

    return samples


def run(operator_id: int):
    """Full tone profiler pipeline for the given operator."""

    # 1. Load operator from DB
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=operator_id).first()
        if not operator:
            console.print(f"[red]Operator ID {operator_id} not found in database.[/red]")
            sys.exit(1)
        operator_name = operator.name
        business_name = operator.business_name

    console.print(Panel.fit(
        f"[bold green]Tone Profiler[/bold green]\n"
        f"Operator: [yellow]{operator_name}[/yellow] — {business_name}\n"
        f"[dim]Reading Gmail → Extracting voice → Generating samples[/dim]",
        border_style="green"
    ))

    # 2. Fetch sent emails from Gmail
    console.print("\n[bold]Step 1:[/bold] Fetching sent emails from Gmail...")
    emails = get_sent_emails(max_results=25)

    if not emails:
        console.print("[red]No sent emails found. Make sure your Gmail is connected and has sent mail.[/red]")
        sys.exit(1)

    console.print(f"  [green]✓[/green] {len(emails)} emails fetched.")

    # 3. Extract voice profile
    console.print("\n[bold]Step 2:[/bold] Extracting voice profile with Claude...")
    voice_profile = extract_voice_profile(emails)

    console.print("  [green]✓[/green] Voice profile extracted:")
    console.print(Panel(
        json.dumps(voice_profile, indent=2),
        title="Voice Profile",
        border_style="blue"
    ))

    # 4. Store profile on Operator
    console.print("\n[bold]Step 3:[/bold] Saving voice profile to database...")
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=operator_id).first()
        operator.tone_profile = voice_profile
        operator.onboarding_complete = True

    console.print("  [green]✓[/green] Saved to Operator record.")

    # 5. Generate sample reactivation emails
    console.print("\n[bold]Step 4:[/bold] Generating 3 sample reactivation emails...")
    sample_emails = generate_sample_emails(voice_profile)

    console.print("\n[bold yellow]Sample Reactivation Emails (written in your voice):[/bold yellow]")
    for i, email in enumerate(sample_emails, 1):
        console.print(Panel(
            f"[bold]Subject:[/bold] {email.get('subject', '')}\n\n{email.get('body', '')}",
            title=f"Sample {i}",
            border_style="yellow"
        ))

    console.print("\n[bold green]✅ Tone profiler complete.[/bold green]")
    console.print(f"[dim]Voice profile stored on Operator ID {operator_id}. "
                  "All future outreach will be written in this voice.[/dim]")

    return voice_profile, sample_emails


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tone profiler for an operator")
    parser.add_argument("--operator-id", type=int, default=1, help="Operator ID to profile (default: 1)")
    args = parser.parse_args()

    run(args.operator_id)

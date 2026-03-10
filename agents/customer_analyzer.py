"""
agents/customer_analyzer.py
Customer Correspondence Analyzer.

Fires BEFORE initial outreach and after every reply is detected.
Reads all prior Gmail correspondence with a customer, uses Claude to build
a relationship profile, and stores it on Customer.customer_profile.

The profile is passed into every draft prompt — giving Claude full context
on who this person is and how to approach them, rather than writing cold.

Profile schema:
  {
    "relationship_history":  str,   # narrative summary of prior interaction
    "topics_discussed":      list,  # service topics, concerns, questions raised
    "customer_tone":         str,   # how they write (brief/chatty/formal/etc.)
    "prior_concerns":        list,  # price, timing, specific issues mentioned
    "response_patterns":     str,   # how quickly they reply, how engaged
    "interest_signals":      str,   # any expressed interest or intent
    "context_notes":         str,   # personal details that add color
    "analyzed_at":           str,   # ISO timestamp
    "email_count":           int,   # number of emails analyzed
  }

Usage:
    python -m agents.customer_analyzer --operator-id 1 --customer-id 5
    python -m agents.customer_analyzer --operator-id 1 --all
"""

import argparse
import json
from datetime import datetime, timezone

import anthropic

from core.config import config
from core.database import get_db
from core.models import Customer, Operator

try:
    from integrations.gmail import get_correspondence
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


ANALYZER_SYSTEM = """You are analyzing email correspondence between a field service
business owner and one of their customers. Extract a structured relationship profile
that will help craft personalized outreach.

Be concise and specific. If there is no prior correspondence, say so clearly.
Return ONLY a JSON object matching the schema — no markdown, no code fences."""

ANALYZER_USER = """Analyze the following email correspondence between the operator
and customer {name} ({email}).

Emails ({count} messages):
{emails}

Return a JSON object with these exact keys:
{{
  "relationship_history": "narrative of the prior relationship and any key interactions",
  "topics_discussed": ["list", "of", "topics"],
  "customer_tone": "how the customer communicates (brief, chatty, formal, warm, etc.)",
  "prior_concerns": ["any concerns, objections, or friction points they raised"],
  "response_patterns": "how quickly and consistently they replied",
  "interest_signals": "any signals of interest, intent, or openness to future work",
  "context_notes": "personal details or context useful for personalization"
}}"""

NO_HISTORY_PROFILE = {
    "relationship_history": "No prior email correspondence found.",
    "topics_discussed": [],
    "customer_tone": "unknown",
    "prior_concerns": [],
    "response_patterns": "unknown — no prior correspondence",
    "interest_signals": "none detected",
    "context_notes": "",
}


def analyze_customer(operator_id: int, customer_id: int, verbose: bool = True) -> dict:
    """
    Build or refresh the CustomerProfile for a single customer.

    Returns the profile dict (also stored to DB).
    """
    with get_db() as db:
        customer = db.query(Customer).filter_by(
            id=customer_id, operator_id=operator_id
        ).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found for operator {operator_id}")
        cust_name = customer.name
        cust_email = customer.email

    if verbose:
        print(f"  [analyzer] {cust_name} <{cust_email}>")

    # Fetch prior correspondence from Gmail
    correspondence = []
    if GMAIL_AVAILABLE and cust_email:
        try:
            correspondence = get_correspondence(cust_email, max_results=30)
            if verbose:
                print(f"  [analyzer] Found {len(correspondence)} prior emails")
        except Exception as e:
            if verbose:
                print(f"  [analyzer] Gmail unavailable: {e}")

    if not correspondence:
        profile = dict(NO_HISTORY_PROFILE)
        profile["analyzed_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        profile["email_count"] = 0
        _save_profile(operator_id, customer_id, profile)
        return profile

    # Format emails for Claude
    email_snippets = []
    for msg in correspondence:
        direction = "INBOUND" if msg.get("is_inbound") else "SENT"
        date = msg.get("sent_at", "")
        body = (msg.get("body") or "")[:400]
        if body:
            email_snippets.append(f"[{direction} {date}]\n{body}")

    emails_text = "\n\n---\n\n".join(email_snippets)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=ANALYZER_SYSTEM,
            messages=[{
                "role": "user",
                "content": ANALYZER_USER.format(
                    name=cust_name,
                    email=cust_email,
                    count=len(correspondence),
                    emails=emails_text,
                ),
            }],
        )
        raw = message.content[0].text.strip()
        profile = json.loads(raw)
    except json.JSONDecodeError:
        profile = dict(NO_HISTORY_PROFILE)
    except Exception as e:
        if verbose:
            print(f"  [analyzer] Claude error: {e}")
        profile = dict(NO_HISTORY_PROFILE)

    profile["analyzed_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    profile["email_count"] = len(correspondence)

    _save_profile(operator_id, customer_id, profile)

    if verbose:
        print(f"  [analyzer] Profile built — tone: {profile.get('customer_tone')}, "
              f"signals: {profile.get('interest_signals', '')[:60]}")

    return profile


def _save_profile(operator_id: int, customer_id: int, profile: dict):
    with get_db() as db:
        customer = db.query(Customer).filter_by(
            id=customer_id, operator_id=operator_id
        ).first()
        if customer:
            customer.customer_profile = profile


def format_profile_for_prompt(profile: dict) -> str:
    """
    Format a CustomerProfile as a readable block for injection into Claude prompts.
    Returns empty string if no meaningful history.
    """
    if not profile or not profile.get("relationship_history"):
        return ""
    if profile.get("relationship_history") == NO_HISTORY_PROFILE["relationship_history"]:
        return ""

    parts = [f"Prior relationship context for this customer:"]
    parts.append(f"  History: {profile['relationship_history']}")

    if profile.get("topics_discussed"):
        parts.append(f"  Topics discussed: {', '.join(profile['topics_discussed'])}")
    if profile.get("customer_tone") and profile["customer_tone"] != "unknown":
        parts.append(f"  Their communication style: {profile['customer_tone']}")
    if profile.get("prior_concerns"):
        parts.append(f"  Prior concerns: {', '.join(profile['prior_concerns'])}")
    if profile.get("interest_signals") and profile["interest_signals"] != "none detected":
        parts.append(f"  Interest signals: {profile['interest_signals']}")
    if profile.get("context_notes"):
        parts.append(f"  Context: {profile['context_notes']}")

    return "\n".join(parts) + "\n\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman customer analyzer")
    parser.add_argument("--operator-id", type=int, default=1)
    parser.add_argument("--customer-id", type=int, default=None)
    parser.add_argument("--all", action="store_true", help="Analyze all customers for operator")
    args = parser.parse_args()

    if args.all:
        with get_db() as db:
            customers = db.query(Customer).filter_by(operator_id=args.operator_id).all()
            ids = [(c.id, c.name) for c in customers]
        print(f"\n[customer_analyzer] Analyzing {len(ids)} customers for operator {args.operator_id}")
        for cid, name in ids:
            print(f"\n→ {name} (id={cid})")
            analyze_customer(args.operator_id, cid)
    elif args.customer_id:
        profile = analyze_customer(args.operator_id, args.customer_id)
        print(f"\nProfile:\n{json.dumps(profile, indent=2, default=str)}")
    else:
        print("Provide --customer-id N or --all")

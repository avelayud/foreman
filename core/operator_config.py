"""
core/operator_config.py
Operator configuration: getter, setter, and agent context injection helper.

Config is stored as JSON on Operator._operator_config. Defaults are always
merged in so agents always have something to work with even before the
operator visits /settings.
"""

import json
from core.database import get_db

DEFAULT_CONFIG = {
    "tone": 3,
    "salesy": 2,
    "job_priority": ["maintenance", "repair", "install", "inspection", "other"],
    "estimate_ranges": {
        "maintenance": {"min": 89, "max": 199},
        "repair": {"min": 150, "max": 800},
        "install": {"min": 3500, "max": 12000},
        "inspection": {"min": 79, "max": 149},
        "other": {"min": 100, "max": 500},
    },
    "seasonal_focus": {},
    "business_context": "",
}

_TONE_LABELS = {
    1: "Consultative and warm",
    2: "Leaning consultative",
    3: "Balanced",
    4: "Leaning direct",
    5: "Direct and no-frills",
}

_SALESY_LABELS = {
    1: "Low-key, relationship-first",
    2: "Mostly low-key",
    3: "Balanced",
    4: "Mostly assertive",
    5: "Confident push for the booking",
}

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def get_config(operator_id: int) -> dict:
    """Return the operator's config dict, with DEFAULT_CONFIG values filled in for missing keys."""
    with get_db() as db:
        from core.models import Operator
        op = db.query(Operator).filter_by(id=operator_id).first()
        stored = op.operator_config if op else {}

    merged = dict(DEFAULT_CONFIG)
    merged.update(stored)

    # Deep merge estimate_ranges (stored may be partial)
    merged_ranges = dict(DEFAULT_CONFIG["estimate_ranges"])
    merged_ranges.update(stored.get("estimate_ranges", {}))
    merged["estimate_ranges"] = merged_ranges

    return merged


def save_config(operator_id: int, cfg: dict) -> None:
    """Persist the config dict to Operator._operator_config."""
    with get_db() as db:
        from core.models import Operator
        op = db.query(Operator).filter_by(id=operator_id).first()
        if op:
            op.operator_config = cfg


def get_agent_context(operator_id: int) -> str:
    """
    Return a formatted string block for injection at the top of every agent system prompt.

    Format:
        BUSINESS CONTEXT:
        - Tone: Direct and no-frills (5/5)
        - Sales approach: Low-key, relationship-first (1/5)
        - Job priority (highest first): Maintenance > Repair > Install
        - Estimate ranges: Maintenance $89–199 | Repair $150–800 | Install $3,500–12,000
        - Seasonal focus: Push maintenance in Apr, May, Jun
        - Context: [operator free text]
    """
    cfg = get_config(operator_id)

    tone_val = int(cfg.get("tone", 3))
    salesy_val = int(cfg.get("salesy", 2))
    tone_label = _TONE_LABELS.get(tone_val, "Balanced")
    salesy_label = _SALESY_LABELS.get(salesy_val, "Balanced")

    priority = cfg.get("job_priority", DEFAULT_CONFIG["job_priority"])
    priority_str = " > ".join(j.capitalize() for j in priority)

    ranges = cfg.get("estimate_ranges", {})
    range_parts = []
    for job_type in priority:
        r = ranges.get(job_type)
        if r:
            lo = r.get("min", 0)
            hi = r.get("max", 0)
            lo_fmt = f"${lo:,.0f}" if lo < 1000 else f"${lo/1000:.0f}k" if lo % 1000 == 0 else f"${lo:,}"
            hi_fmt = f"${hi:,.0f}" if hi < 1000 else f"${hi/1000:.0f}k" if hi % 1000 == 0 else f"${hi:,}"
            range_parts.append(f"{job_type.capitalize()} {lo_fmt}–{hi_fmt}")
    range_str = " | ".join(range_parts) if range_parts else "Not configured"

    seasonal = cfg.get("seasonal_focus", {})
    seasonal_parts = []
    for job_type, months in seasonal.items():
        if months:
            month_names = ", ".join(_MONTH_NAMES[m - 1] for m in sorted(months) if 1 <= m <= 12)
            seasonal_parts.append(f"Push {job_type} in {month_names}")
    seasonal_str = "; ".join(seasonal_parts) if seasonal_parts else "None set"

    context_text = (cfg.get("business_context") or "").strip()

    lines = [
        "BUSINESS CONTEXT:",
        f"- Tone: {tone_label} ({tone_val}/5)",
        f"- Sales approach: {salesy_label} ({salesy_val}/5)",
        f"- Job priority (highest first): {priority_str}",
        f"- Estimate ranges: {range_str}",
        f"- Seasonal focus: {seasonal_str}",
    ]
    if context_text:
        lines.append(f"- Context: {context_text}")

    return "\n".join(lines)

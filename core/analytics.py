"""
core/analytics.py
Server-side aggregation functions for the /analytics dashboard.
All functions receive an open db session and return plain dicts/lists
with no SQLAlchemy objects.
"""

from datetime import datetime, timedelta
from collections import defaultdict

from core.models import Customer, OutreachLog, Booking, Job


def get_customer_snapshot(db, operator_id: int) -> dict:
    """4 headline stats for the Customer Insights tab (all-time)."""
    customers = (
        db.query(
            Customer.id,
            Customer.total_spend,
            Customer.total_jobs,
            Customer.last_service_date,
        )
        .filter(Customer.operator_id == operator_id)
        .all()
    )

    total = len(customers)
    if total == 0:
        return {
            "total_customers": 0,
            "avg_ltv": 0.0,
            "avg_days_dormant": 0,
            "customers_3plus_jobs": 0,
        }

    now = datetime.utcnow()
    total_spend = sum(c.total_spend or 0.0 for c in customers)
    avg_ltv = round(total_spend / total, 2)

    days_dormant_list = []
    for c in customers:
        if c.last_service_date:
            days_dormant_list.append((now - c.last_service_date).days)

    avg_days_dormant = (
        round(sum(days_dormant_list) / len(days_dormant_list))
        if days_dormant_list
        else 0
    )

    customers_3plus = sum(1 for c in customers if (c.total_jobs or 0) >= 3)

    return {
        "total_customers": total,
        "avg_ltv": avg_ltv,
        "avg_days_dormant": avg_days_dormant,
        "customers_3plus_jobs": customers_3plus,
    }


def get_value_tier_breakdown(db, operator_id: int) -> list:
    """Count customers in High / Mid / Low LTV tiers."""
    customers = (
        db.query(Customer.total_spend)
        .filter(Customer.operator_id == operator_id)
        .all()
    )

    high = mid = low = 0
    for c in customers:
        spend = c.total_spend or 0.0
        if spend >= 2000:
            high += 1
        elif spend >= 500:
            mid += 1
        else:
            low += 1

    return [
        {"tier": "High (>$2k)", "count": high},
        {"tier": "Mid ($500-$2k)", "count": mid},
        {"tier": "Low (<$500)", "count": low},
    ]


def get_dormancy_distribution(db, operator_id: int) -> list:
    """Count customers in Active / Priority / Cold dormancy buckets."""
    customers = (
        db.query(Customer.last_service_date)
        .filter(Customer.operator_id == operator_id)
        .all()
    )

    now = datetime.utcnow()
    active = priority = cold = 0
    for c in customers:
        if not c.last_service_date:
            cold += 1
            continue
        days = (now - c.last_service_date).days
        if days < 180:
            active += 1
        elif days < 548:  # ~18 months
            priority += 1
        else:
            cold += 1

    return [
        {"label": "Active (<6mo)", "count": active},
        {"label": "Priority (6-18mo)", "count": priority},
        {"label": "Cold (18mo+)", "count": cold},
    ]


def get_outreach_funnel(db, operator_id: int) -> dict:
    """Dormant → Contacted → Replied → Booked funnel with conversion rates."""
    now = datetime.utcnow()
    six_months_ago = now - timedelta(days=180)

    # Dormant = customers whose last service was >180 days ago
    all_customers = (
        db.query(Customer.id, Customer.last_service_date, Customer.reactivation_status)
        .filter(Customer.operator_id == operator_id)
        .all()
    )

    dormant_ids = {
        c.id for c in all_customers
        if c.last_service_date and c.last_service_date < six_months_ago
    }
    dormant = len(dormant_ids)

    contacted_statuses = {
        "outreach_sent", "sequence_step_2", "sequence_step_3",
        "sequence_complete", "replied", "booked",
    }
    contacted = sum(
        1 for c in all_customers
        if c.reactivation_status in contacted_statuses
    )
    replied = sum(
        1 for c in all_customers
        if c.reactivation_status in {"replied", "booked", "sequence_complete"}
    )
    booked = sum(
        1 for c in all_customers
        if c.reactivation_status == "booked"
    )

    def _rate(num, denom):
        if not denom:
            return "—"
        return f"{round(num / denom * 100)}%"

    return {
        "dormant_identified": dormant,
        "contacted": contacted,
        "replied": replied,
        "booked": booked,
        "contact_rate": _rate(contacted, dormant),
        "reply_rate": _rate(replied, contacted),
        "book_rate": _rate(booked, replied),
    }


def get_revenue_stats(db, operator_id: int) -> dict:
    """Revenue Generated, Pipeline Value, Jobs Booked, Avg Job Value."""
    # Revenue generated: converted OutreachLog entries
    converted_logs = (
        db.query(OutreachLog.converted_job_value)
        .filter(
            OutreachLog.operator_id == operator_id,
            OutreachLog.converted_to_job == True,
            OutreachLog.converted_job_value.isnot(None),
        )
        .all()
    )
    revenue_generated = sum(r.converted_job_value or 0 for r in converted_logs)
    jobs_booked = len(converted_logs)
    avg_job_value = (
        round(revenue_generated / jobs_booked, 2) if jobs_booked else 0.0
    )

    # Pipeline value: customers in active outreach × their estimated job value
    pipeline_customers = (
        db.query(Customer.estimated_job_value)
        .filter(
            Customer.operator_id == operator_id,
            Customer.reactivation_status.in_(
                ["outreach_sent", "sequence_step_2", "sequence_step_3", "replied"]
            ),
        )
        .all()
    )
    pipeline_value = sum(c.estimated_job_value or 0.0 for c in pipeline_customers)

    return {
        "revenue_generated": round(revenue_generated, 2),
        "pipeline_value": round(pipeline_value, 2),
        "jobs_booked": jobs_booked,
        "avg_job_value": avg_job_value,
    }


def get_activity_over_time(db, operator_id: int, days: int | None = 90) -> list:
    """Weekly aggregation of outreach sent vs replies. days=None means all-time."""
    now = datetime.utcnow()
    cutoff = (now - timedelta(days=days)) if days else None

    query = (
        db.query(
            OutreachLog.sent_at,
            OutreachLog.direction,
        )
        .filter(
            OutreachLog.operator_id == operator_id,
            OutreachLog.dry_run == False,
        )
    )
    if cutoff:
        query = query.filter(OutreachLog.sent_at >= cutoff)

    logs = query.all()

    # Group by ISO week
    week_data: dict[str, dict] = defaultdict(lambda: {"sent": 0, "replies": 0})
    for log in logs:
        if not log.sent_at:
            continue
        week_key = log.sent_at.strftime("%Y-W%W")
        if log.direction == "outbound":
            week_data[week_key]["sent"] += 1
        else:
            week_data[week_key]["replies"] += 1

    return [
        {"week": week, "sent": v["sent"], "replies": v["replies"]}
        for week, v in sorted(week_data.items())
    ]


def get_recent_conversions(db, operator_id: int, limit: int = 10) -> list:
    """Last N customers who were marked as booked via outreach."""
    logs = (
        db.query(
            OutreachLog.customer_id,
            OutreachLog.sent_at,
            OutreachLog.converted_at,
            OutreachLog.converted_job_value,
        )
        .filter(
            OutreachLog.operator_id == operator_id,
            OutreachLog.converted_to_job == True,
        )
        .order_by(OutreachLog.converted_at.desc())
        .limit(limit)
        .all()
    )

    customer_ids = [l.customer_id for l in logs]
    customers_by_id = {}
    if customer_ids:
        customers = (
            db.query(Customer.id, Customer.name)
            .filter(Customer.id.in_(customer_ids))
            .all()
        )
        customers_by_id = {c.id: c.name for c in customers}

    result = []
    for log in logs:
        sent_at = log.sent_at
        converted_at = log.converted_at
        days_to_book = None
        if sent_at and converted_at:
            days_to_book = (converted_at - sent_at).days

        # Find the reply event
        reply_log = (
            db.query(OutreachLog.sent_at)
            .filter(
                OutreachLog.customer_id == log.customer_id,
                OutreachLog.direction == "inbound",
                OutreachLog.operator_id == operator_id,
            )
            .order_by(OutreachLog.sent_at.desc())
            .first()
        )
        replied_at = reply_log.sent_at if reply_log else None

        result.append({
            "name": customers_by_id.get(log.customer_id, "Unknown"),
            "sent_at": sent_at.strftime("%-m/%-d/%y") if sent_at else "—",
            "replied_at": replied_at.strftime("%-m/%-d/%y") if replied_at else "—",
            "job_value": log.converted_job_value or 0.0,
            "days_to_book": days_to_book if days_to_book is not None else "—",
        })

    return result


def get_revenue_pipeline(db, operator_id: int) -> dict:
    """
    Foreman-attributed revenue pipeline funnel.
    Booked → Visit Confirmed → Quote Given → Job Won
    Only counts bookings linked to operator's customers.
    """
    from core.models import Booking  # already imported at top, safe to re-reference

    bookings = (
        db.query(Booking)
        .join(Customer, Booking.customer_id == Customer.id)
        .filter(Customer.operator_id == operator_id)
        .all()
    )

    total_booked = len(bookings)
    total_estimated = sum(b.estimated_value or 0 for b in bookings if b.estimated_value)

    visit_confirmed = [b for b in bookings if (b.visit_outcome or "pending") in ("confirmed", "no_show") or b.quote_given]
    confirmed_count = len(visit_confirmed)
    show_rate = f"{round(confirmed_count / total_booked * 100)}%" if total_booked else "—"

    quote_given = [b for b in bookings if b.quote_given]
    quote_count = len(quote_given)
    total_quotes = sum(b.quote_given or 0 for b in quote_given)

    jobs_won = [b for b in bookings if b.job_won]
    won_count = len(jobs_won)
    total_revenue = sum(b.final_invoice_value or 0 for b in jobs_won)
    close_rate = f"{round(won_count / quote_count * 100)}%" if quote_count else "—"

    return {
        "booked_count": total_booked,
        "booked_estimated": round(total_estimated, 2),
        "confirmed_count": confirmed_count,
        "show_rate": show_rate,
        "quote_count": quote_count,
        "total_quotes": round(total_quotes, 2),
        "won_count": won_count,
        "total_revenue": round(total_revenue, 2),
        "close_rate": close_rate,
    }


def get_engagement_by_status(db, operator_id: int) -> list:
    """Count customers per reactivation_status bucket."""
    from sqlalchemy import func
    rows = (
        db.query(Customer.reactivation_status, func.count(Customer.id).label("count"))
        .filter(Customer.operator_id == operator_id)
        .group_by(Customer.reactivation_status)
        .all()
    )
    total = sum(r.count for r in rows)
    result = []
    for r in rows:
        result.append({
            "status": r.reactivation_status or "unknown",
            "count": r.count,
            "pct": round(r.count / total * 100) if total else 0,
        })
    result.sort(key=lambda x: x["count"], reverse=True)
    return result

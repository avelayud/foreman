"""
core/scoring.py
Customer scoring engine for Foreman.
Scores each customer on 5 signals and writes results to the Customer model.
"""

import json
from datetime import datetime, timedelta


class CustomerScorer:
    """Rules-based customer scoring (v1)."""

    MAINTENANCE_KEYWORDS = (
        "maintenance", "tune-up", "tune up", "seasonal", "inspection",
        "annual", "check-up", "checkup", "service plan",
    )
    POSITIVE_REPLY_KEYWORDS = (
        "schedule", "book", "appointment", "yes", "please", "call me",
        "interested", "available", "when can", "sounds good", "go ahead",
    )

    def score(self, customer, jobs: list, outreach_logs: list, job_priority: list = None) -> dict:
        """
        Score a customer on 5 signals.
        Returns {total, breakdown, priority_tier}.
        job_priority: ordered list of job type names (highest priority first).
        """
        recency = self._recency_score(customer)
        lifetime_value = self._lifetime_value_score(customer)
        frequency = self._frequency_score(jobs)
        job_type = self._job_type_score(jobs, job_priority=job_priority)
        engagement = self._engagement_score(outreach_logs)

        total = recency + lifetime_value + frequency + job_type + engagement

        if total >= 70:
            priority_tier = "high"
        elif total >= 40:
            priority_tier = "medium"
        else:
            priority_tier = "low"

        return {
            "total": total,
            "breakdown": {
                "recency": recency,
                "lifetime_value": lifetime_value,
                "frequency": frequency,
                "job_type": job_type,
                "engagement": engagement,
            },
            "priority_tier": priority_tier,
        }

    def _recency_score(self, customer) -> int:
        """Max 40 pts. >365 days dormant = 40. Linear below that."""
        if not customer.last_service_date:
            return 40
        days = (datetime.utcnow() - customer.last_service_date).days
        if days >= 365:
            return 40
        return max(0, int(days * 40 / 365))

    def _lifetime_value_score(self, customer) -> int:
        """Max 20 pts. >$2000 = 20, >$500 = 10, else 5."""
        spend = float(customer.total_spend or 0)
        if spend >= 2000:
            return 20
        elif spend >= 500:
            return 10
        return 5

    def _frequency_score(self, jobs: list) -> int:
        """Max 15 pts. count * 3, capped at 15."""
        return min(len(jobs) * 3, 15)

    def _job_type_score(self, jobs: list, job_priority: list = None) -> int:
        """
        Max 15 pts. Uses operator's job_priority list when available.
        Top-priority job type in customer's history = 15. Second = 10. Rest = 8. Single job = 4.
        Falls back to maintenance-keyword logic when no priority list is provided.
        """
        if not jobs or len(jobs) == 1:
            return 4

        if job_priority:
            # Find the highest-ranked job type in the customer's history
            svc_types = [(job.service_type or "").lower() for job in jobs]
            for rank, ptype in enumerate(job_priority):
                if any(ptype in svc for svc in svc_types):
                    if rank == 0:
                        return 15
                    elif rank == 1:
                        return 10
                    else:
                        return 8

        # Fallback: keyword-based maintenance detection
        for job in jobs:
            svc = (job.service_type or "").lower()
            if any(kw in svc for kw in self.MAINTENANCE_KEYWORDS):
                return 15
        return 8

    def _engagement_score(self, outreach_logs: list) -> int:
        """Max 10 pts. Positive reply = 10, any reply = 5, no history = 0."""
        if not outreach_logs:
            return 0
        has_any_reply = False
        for log in outreach_logs:
            if log.direction == "inbound":
                has_any_reply = True
                content = (log.reply_content or log.content or "").lower()
                if any(kw in content for kw in self.POSITIVE_REPLY_KEYWORDS):
                    return 10
        return 5 if has_any_reply else 0


def score_all_customers(db_session, operator_id: int = 1) -> int:
    """
    Score every customer for the given operator and persist results.
    Also computes estimated_job_value, service_interval_days, predicted_next_service.
    Returns count of customers scored.
    """
    from core.models import Customer, Job, OutreachLog

    # Load job priority from operator config (graceful fallback if config not set)
    job_priority = None
    try:
        from core.operator_config import get_config
        cfg = get_config(operator_id)
        job_priority = cfg.get("job_priority")
    except Exception:
        pass

    scorer = CustomerScorer()
    customers = db_session.query(Customer).filter_by(operator_id=operator_id).all()

    for customer in customers:
        jobs = db_session.query(Job).filter_by(customer_id=customer.id).all()
        outreach_logs = db_session.query(OutreachLog).filter_by(
            customer_id=customer.id, operator_id=operator_id
        ).all()

        result = scorer.score(customer, jobs, outreach_logs, job_priority=job_priority)

        customer.score = result["total"]
        customer.score_breakdown = json.dumps(result["breakdown"])
        customer.priority_tier = result["priority_tier"]

        # Estimated job value: mean of actual job amounts (fallback to total_spend / jobs)
        amounts = [j.amount for j in jobs if j.amount and j.amount > 0]
        if amounts:
            customer.estimated_job_value = round(sum(amounts) / len(amounts), 2)
        elif customer.total_jobs and customer.total_jobs > 0:
            customer.estimated_job_value = round(
                float(customer.total_spend or 0) / customer.total_jobs, 2
            )
        else:
            customer.estimated_job_value = 0.0

        # Service interval: mean gap between consecutive completed jobs
        completed = sorted(
            [j for j in jobs if j.completed_at],
            key=lambda j: j.completed_at,
        )
        if len(completed) >= 2:
            gaps = [
                (completed[i].completed_at - completed[i - 1].completed_at).days
                for i in range(1, len(completed))
            ]
            customer.service_interval_days = max(1, int(sum(gaps) / len(gaps)))
        else:
            customer.service_interval_days = 365  # sensible default

        # Predicted next service
        if customer.last_service_date and customer.service_interval_days:
            customer.predicted_next_service = (
                customer.last_service_date
                + timedelta(days=customer.service_interval_days)
            )

    db_session.commit()
    return len(customers)

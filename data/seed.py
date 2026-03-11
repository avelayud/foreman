"""
data/seed.py
Seeds the database with a realistic HVAC contractor dataset.
200 customers · 5 years of job history · realistic dormancy distribution.

Run: python -m data.seed   (idempotent — clears and reseeds each time)
"""

import random
from datetime import datetime, timedelta

from core.database import init_db, get_db
from core.models import Operator, Customer, Job, OutreachLog

# ── Reproducible randomness ────────────────────────────────────────────────────
random.seed(42)

# ── Realistic name pool ────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Tom", "Sandra", "Rick", "Maria", "James", "Donna", "Brian", "Linda",
    "Kevin", "Cheryl", "Dave", "Anita", "Greg", "Faye", "Earl", "Patty",
    "Wayne", "Josie", "Carl", "Sheila", "Mike", "Carol", "Jeff", "Nancy",
    "Bob", "Patricia", "Dan", "Barbara", "Paul", "Susan", "Mark", "Dorothy",
    "Steve", "Lisa", "Gary", "Karen", "Larry", "Betty", "Frank", "Helen",
    "Ken", "Sharon", "Ron", "Deborah", "Ray", "Ruth", "Scott", "Anna",
    "Jack", "Kathleen", "Harold", "Christine", "Walter", "Samantha", "Alan",
    "Melissa", "Chris", "Catherine", "Dennis", "Frances", "Jerry", "Janet",
    "Joe", "Carolyn", "Arthur", "Virginia", "Clarence", "Martha", "Barry",
    "Diane", "Rodney", "Amy", "Clifford", "Jean", "Dale", "Alice", "Todd",
    "Brenda", "Brett", "Pamela", "Keith", "Emma", "Nathan", "Evelyn",
    "Calvin", "Olivia", "Patrick", "Judith", "Sean", "Lori", "Derek",
    "Angela", "Leon", "Mildred", "Brent", "Gladys", "Nicholas", "Norma",
]

LAST_NAMES = [
    "Harrington", "Patel", "Deluca", "Gonzalez", "Whitfield", "Kowalski",
    "Nguyen", "Foster", "Okafor", "Banks", "Marchetti", "Russo", "Tillman",
    "Chambers", "Hutchinson", "Simmons", "Brennan", "Larkin", "Estrada",
    "Morgan", "Sullivan", "Rivera", "Peterson", "Turner", "Collins",
    "Stewart", "Morris", "Rogers", "Reed", "Cook", "Bailey", "Bell",
    "Cooper", "Richardson", "Cox", "Ward", "Torres", "Gray", "Hughes",
    "Price", "Flores", "Butler", "Simmons", "Sanders", "Jenkins", "Perry",
    "Powell", "Patterson", "Hughes", "Ross", "Henderson", "Coleman",
    "Bryant", "Alexander", "Russell", "Griffin", "Diaz", "Hayes", "Myers",
    "Ford", "Hamilton", "Graham", "Sullivan", "Wallace", "Woods", "Cole",
    "West", "Jordan", "Owens", "Reynolds", "Fisher", "Chandler", "Dixon",
    "Lawson", "Watts", "Burke", "Stone", "Warren", "Harper", "Garza",
    "Mendoza", "Vargas", "Castillo", "George", "Greene", "Webb", "Walsh",
    "Duncan", "Armstrong", "Garrett", "Hawkins", "Erickson", "Hicks",
    "Horton", "Hunter", "Fleming", "Lambert", "Barton", "Whitney", "York",
]

STREETS = [
    "Oak St", "Maple Ave", "Pine Rd", "Birch Ln", "Cedar Dr", "Elm St",
    "Spruce Ct", "Walnut Blvd", "Aspen Way", "Hickory Pl", "Poplar St",
    "Willow Way", "Magnolia Dr", "Cypress Ln", "Sycamore Rd", "Dogwood Ave",
    "Redwood Ct", "Chestnut Blvd", "Linden St", "Juniper Dr", "Foxwood Ln",
    "Clover Hill Rd", "Summit Dr", "Valley View Ct", "Ridgemont Ave",
    "Brookside Dr", "Lakewood Blvd", "Fairview St", "Greenfield Rd",
    "Hillcrest Ave", "Meadow Ln", "River Rd", "Forest Dr", "Sunrise Blvd",
    "Sunset Ave", "Clearwater Ct", "Rocky Rd", "Canyon Dr", "Timber Ln",
]

# ── Job types + revenue ranges ─────────────────────────────────────────────────
JOB_TYPES = {
    "Seasonal Tune-Up":    (89,   149),
    "Annual Maintenance":  (99,   149),
    "AC Repair":           (200,  800),
    "Furnace Repair":      (200,  800),
    "Emergency Service":   (350, 1200),
    "New AC Install":      (2500, 8000),
    "New Furnace Install": (2500, 8000),
    "Duct Cleaning":       (300,  700),
    "Thermostat Install":  (150,  350),
    "Refrigerant Recharge":(180,  400),
}

MAINTENANCE_TYPES = {"Seasonal Tune-Up", "Annual Maintenance"}

# ── Simulated reply text ───────────────────────────────────────────────────────
POSITIVE_REPLIES = [
    "Yes please schedule me, next week works.",
    "I'd like to book an appointment. When are you available?",
    "Sounds good, please give me a call to discuss.",
    "Yes! We've been meaning to get this done. Call me.",
    "Go ahead and schedule something, Tuesday or Thursday works.",
]
NEUTRAL_REPLIES = [
    "How much would that cost?",
    "Call me to discuss, I have some questions.",
    "Can you send me more information first?",
    "What does this include exactly?",
]
NEGATIVE_REPLIES = [
    "Not interested at this time, thanks.",
    "Please remove me from your list.",
    "We went with another company, sorry.",
]

NOW = datetime.utcnow()
FIVE_YEARS_AGO = NOW - timedelta(days=5 * 365)


def _random_name(used: set) -> tuple[str, str]:
    for _ in range(200):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        if (first, last) not in used:
            used.add((first, last))
            return first, last
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def _random_address(index: int) -> str:
    num = random.randint(10, 999)
    street = STREETS[index % len(STREETS)]
    return f"{num} {street}"


def _random_job_value(service_type: str) -> float:
    lo, hi = JOB_TYPES[service_type]
    return round(random.uniform(lo, hi), 2)


def _build_job_history(
    operator_id: int,
    customer_id: int,
    num_jobs: int,
    last_job_date: datetime,
    value_tier: str,
) -> list[Job]:
    """
    Build a realistic sequence of completed jobs, ending at last_job_date.
    Job types are chosen to match the customer's value tier.
    """
    # Choose job type mix by tier
    if value_tier == "high":
        type_pool = (
            ["Annual Maintenance"] * 3
            + ["Seasonal Tune-Up"] * 2
            + ["AC Repair", "Furnace Repair"]
            + ["New AC Install"]
        )
    elif value_tier == "mid":
        type_pool = (
            ["Seasonal Tune-Up"] * 3
            + ["Annual Maintenance"] * 2
            + ["AC Repair", "Furnace Repair"]
            + ["Duct Cleaning", "Thermostat Install"]
        )
    else:  # low
        type_pool = (
            ["Seasonal Tune-Up"] * 2
            + ["AC Repair", "Refrigerant Recharge", "Thermostat Install"]
        )

    jobs = []
    current_date = last_job_date
    for _ in range(num_jobs):
        service_type = random.choice(type_pool)
        amount = _random_job_value(service_type)
        jobs.append(
            Job(
                operator_id=operator_id,
                customer_id=customer_id,
                service_type=service_type,
                scheduled_at=current_date,
                completed_at=current_date,
                status="complete",
                amount=amount,
            )
        )
        # Walk backwards in time: 6–14 month intervals
        interval = random.gauss(270, 90)  # ~9 months, stddev 3 months
        interval = max(60, min(interval, 600))  # clamp 2–20 months
        current_date = current_date - timedelta(days=int(interval))
        if current_date < FIVE_YEARS_AGO:
            break

    return jobs


def _build_outreach(
    operator_id: int,
    customer_id: int,
    num_attempts: int,
    last_job_date: datetime,
) -> list[OutreachLog]:
    logs = []
    send_date = last_job_date + timedelta(days=random.randint(180, 360))
    if send_date > NOW:
        return []

    for step in range(num_attempts):
        reply_type = random.choices(
            ["none", "positive", "neutral", "negative"],
            weights=[60, 15, 15, 10],
            k=1,
        )[0]

        log = OutreachLog(
            operator_id=operator_id,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            content=f"Hi, it's been a while since your last service. We'd love to schedule your next visit.",
            subject=f"Time for your HVAC check-up?",
            sent_at=send_date,
            dry_run=False,
            sequence_step=step,
            approval_status="sent",
            replied=(reply_type != "none"),
        )
        logs.append(log)

        if reply_type != "none":
            if reply_type == "positive":
                reply_text = random.choice(POSITIVE_REPLIES)
            elif reply_type == "neutral":
                reply_text = random.choice(NEUTRAL_REPLIES)
            else:
                reply_text = random.choice(NEGATIVE_REPLIES)

            reply_log = OutreachLog(
                operator_id=operator_id,
                customer_id=customer_id,
                channel="email",
                direction="inbound",
                content=reply_text,
                subject="Re: Time for your HVAC check-up?",
                sent_at=send_date + timedelta(days=random.randint(1, 4)),
                dry_run=False,
                sequence_step=step,
                approval_status="sent",
            )
            logs.append(reply_log)
            break  # Stop sequence after a reply

        send_date = send_date + timedelta(days=random.randint(7, 21))
        if send_date > NOW:
            break

    return logs


def seed():
    init_db()

    with get_db() as db:
        # ── Wipe existing data ──────────────────────────────────────────────
        db.query(OutreachLog).delete()
        db.query(Job).delete()
        db.query(Customer).delete()
        db.query(Operator).delete()
        db.commit()

        # ── Create operator ────────────────────────────────────────────────
        operator = Operator(
            name="Arjuna Velayudam",
            business_name="Premier HVAC Solutions",
            email="arjuna@premierhvac.com",
            phone="555-800-1234",
            niche="hvac",
            onboarding_complete=True,
            outreach_mode="dry_run",
            _tone_profile='{"formality":"casual","greeting_style":"Hey [name],","signoff":"Best, Arjuna","humor":false,"emoji":false,"sample_phrases":["Hope you had a great weekend","Just confirming","Could we please","Appreciate anything you can do"]}',
            _voice_profiles='[{"id":"vp_001","name":"Arjuna","role":"Owner"},{"id":"vp_002","name":"Sarah","role":"Office Manager"}]',
        )
        db.add(operator)
        db.flush()

        op_id = operator.id

        # ── Dormancy targets ────────────────────────────────────────────────
        # ~30% active: 0–180 days
        # ~40% priority dormant: 181–540 days (6–18 months)
        # ~30% cold: 541–1825 days (18m–5y)
        dormancy_buckets = (
            [(0, 180)] * 60        # 30%
            + [(181, 540)] * 80    # 40%
            + [(541, 1095)] * 40   # 20%
            + [(1096, 1825)] * 20  # 10%
        )
        random.shuffle(dormancy_buckets)

        # ── Value tiers ─────────────────────────────────────────────────────
        # ~20% high (4–8 jobs, $2000+)
        # ~50% mid  (2–4 jobs, $500–2000)
        # ~30% low  (1–2 jobs, <$500)
        value_tiers = ["high"] * 40 + ["mid"] * 100 + ["low"] * 60
        random.shuffle(value_tiers)

        used_names: set = set()
        all_customers = []

        for i in range(200):
            first, last = _random_name(used_names)
            name = f"{first} {last}"
            slug = f"{first.lower()}.{last.lower()}"
            email = f"{slug}{random.randint(1,99)}@example.com"
            phone = f"555-{random.randint(200,999):03d}-{random.randint(1000,9999):04d}"
            address = _random_address(i)

            days_lo, days_hi = dormancy_buckets[i]
            days_dormant = random.randint(days_lo, days_hi)
            last_job_date = NOW - timedelta(days=days_dormant)

            tier = value_tiers[i]
            if tier == "high":
                num_jobs = random.randint(4, 8)
            elif tier == "mid":
                num_jobs = random.randint(2, 4)
            else:
                num_jobs = random.randint(1, 2)

            customer = Customer(
                operator_id=op_id,
                name=name,
                email=email,
                phone=phone,
                address=address,
                reactivation_status="never_contacted",
            )
            db.add(customer)
            db.flush()

            # Build job history
            jobs = _build_job_history(op_id, customer.id, num_jobs, last_job_date, tier)
            for job in jobs:
                db.add(job)
            db.flush()

            # Compute denormalized fields
            total_spend = round(sum(j.amount for j in jobs), 2)
            customer.last_service_date = last_job_date
            customer.last_service_type = jobs[0].service_type if jobs else "Unknown"
            customer.total_jobs = len(jobs)
            customer.total_spend = total_spend

            # Determine reactivation status based on dormancy + tier
            if days_dormant < 180:
                status = "never_contacted"
            elif days_dormant < 540:
                # Priority dormant: some have been contacted
                r = random.random()
                if r < 0.35:
                    # Build outreach history
                    num_attempts = random.randint(1, 3)
                    out_logs = _build_outreach(op_id, customer.id, num_attempts, last_job_date)
                    for ol in out_logs:
                        db.add(ol)
                    # Determine resulting status
                    inbound = [l for l in out_logs if l.direction == "inbound"]
                    if inbound:
                        reply_text = (inbound[-1].content or "").lower()
                        positive_kw = ("schedule", "book", "yes", "call me", "go ahead", "sounds good")
                        negative_kw = ("not interested", "remove me", "another company")
                        if any(kw in reply_text for kw in positive_kw):
                            status = "replied"
                        elif any(kw in reply_text for kw in negative_kw):
                            status = "unsubscribed"
                        else:
                            status = "replied"
                    else:
                        status = "outreach_sent"
                else:
                    status = "never_contacted"
            else:
                # Cold: rarely contacted
                r = random.random()
                if r < 0.15:
                    num_attempts = random.randint(1, 2)
                    out_logs = _build_outreach(op_id, customer.id, num_attempts, last_job_date)
                    for ol in out_logs:
                        db.add(ol)
                    inbound = [l for l in out_logs if l.direction == "inbound"]
                    if inbound:
                        reply_text = (inbound[-1].content or "").lower()
                        if "not interested" in reply_text or "remove" in reply_text:
                            status = "unsubscribed"
                        else:
                            status = "replied"
                    else:
                        status = "outreach_sent"
                else:
                    status = "never_contacted"

            customer.reactivation_status = status
            all_customers.append(customer)

        db.commit()

        # ── Score all customers ─────────────────────────────────────────────
        from core.scoring import score_all_customers
        score_all_customers(db, operator_id=op_id)

        # ── Print summary ───────────────────────────────────────────────────
        customers = db.query(Customer).filter_by(operator_id=op_id).all()
        total = len(customers)
        active = sum(1 for c in customers if c.last_service_date and (NOW - c.last_service_date).days < 180)
        priority_dormant = sum(1 for c in customers if c.last_service_date and 180 <= (NOW - c.last_service_date).days < 540)
        cold = sum(1 for c in customers if c.last_service_date and (NOW - c.last_service_date).days >= 540)
        total_revenue = sum(c.total_spend or 0 for c in customers)
        high_tier = sum(1 for c in customers if c.priority_tier == "high")
        med_tier = sum(1 for c in customers if c.priority_tier == "medium")
        low_tier = sum(1 for c in customers if c.priority_tier == "low")
        contacted = sum(1 for c in customers if c.reactivation_status not in ("never_contacted",))

        print("\n" + "=" * 58)
        print("  Foreman Seed Complete")
        print("=" * 58)
        print(f"  Customers seeded:     {total}")
        print(f"  Active (<6 mo):       {active}  ({active*100//total}%)")
        print(f"  Priority dormant:     {priority_dormant}  ({priority_dormant*100//total}%)")
        print(f"  Cold (18m+):          {cold}  ({cold*100//total}%)")
        print(f"  Total lifetime rev:   ${total_revenue:,.0f}")
        print(f"  Score tiers — H/M/L:  {high_tier} / {med_tier} / {low_tier}")
        print(f"  Already contacted:    {contacted}")
        print("=" * 58 + "\n")


if __name__ == "__main__":
    seed()

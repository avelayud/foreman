"""
data/reseed.py
Resets and reseeds the database with richer test data.
Expands to 40 customers with varied statuses, multiple job histories,
and some outreach logs to show all dashboard states.

Run: python data/reseed.py
Or against prod: DATABASE_URL="postgresql://..." python data/reseed.py
"""

from datetime import datetime, timedelta
import random
from core.database import init_db, get_db
from core.models import Operator, Customer, Job, OutreachLog

random.seed(42)  # reproducible

SERVICE_TYPES = [
    "AC tune-up", "Heating inspection", "Furnace repair",
    "AC installation", "Duct cleaning", "Thermostat replacement",
    "Refrigerant recharge", "Emergency repair", "Annual maintenance",
    "Heat pump service", "Mini-split installation", "Filter replacement",
    "Boiler service", "Zone control install", "Air quality inspection",
]

CUSTOMERS = [
    # High-value, long-dormant prime targets
    {"name": "Patty Simmons",   "email": "pattys@email.com",      "phone": "555-201-0016", "address": "88 Dogwood Ave"},
    {"name": "Sandra Patel",    "email": "sandra.p@email.com",    "phone": "555-201-0002", "address": "87 Maple Ave"},
    {"name": "Faye Chambers",   "email": "fayec@email.com",       "phone": "555-201-0014", "address": "44 Cypress Ln"},
    {"name": "Dave Marchetti",  "email": "davem@email.com",       "phone": "555-201-0011", "address": "522 Poplar St"},
    {"name": "Tom Harrington",  "email": "tom.h@email.com",       "phone": "555-201-0001", "address": "142 Oak St"},
    {"name": "Josie Larkin",    "email": "josiel@email.com",      "phone": "555-201-0018", "address": "91 Chestnut Blvd"},
    {"name": "Earl Hutchinson", "email": "earlh@email.com",       "phone": "555-201-0015", "address": "365 Sycamore Rd"},
    {"name": "Greg Tillman",    "email": "gregt@email.com",       "phone": "555-201-0013", "address": "190 Magnolia Dr"},
    # Mid-value prime
    {"name": "Rick Deluca",     "email": "rick.d@email.com",      "phone": "555-201-0003", "address": "310 Pine Rd"},
    {"name": "Donna Kowalski",  "email": "donnakow@email.com",    "phone": "555-201-0006", "address": "401 Elm St"},
    {"name": "Wayne Brennan",   "email": "wayneb@email.com",      "phone": "555-201-0017", "address": "227 Redwood Ct"},
    {"name": "Kevin Okafor",    "email": "kevinokafor@email.com", "phone": "555-201-0009", "address": "33 Aspen Way"},
    {"name": "Maria Gonzalez",  "email": "mariag@email.com",      "phone": "555-201-0004", "address": "55 Birch Ln"},
    {"name": "Anita Russo",     "email": "anitar@email.com",      "phone": "555-201-0012", "address": "78 Willow Way"},
    {"name": "Carl Estrada",    "email": "carle@email.com",       "phone": "555-201-0019", "address": "416 Linden St"},
    # In outreach sequence
    {"name": "Brian Nguyen",    "email": "briann@email.com",      "phone": "555-201-0007", "address": "67 Spruce Ct"},
    {"name": "Linda Foster",    "email": "lindaf@email.com",      "phone": "555-201-0008", "address": "890 Walnut Blvd"},
    {"name": "James Whitfield", "email": "jwhit@email.com",       "phone": "555-201-0005", "address": "209 Cedar Dr"},
    # Replied / converted
    {"name": "Cheryl Banks",    "email": "cherylb@email.com",     "phone": "555-201-0010", "address": "147 Hickory Pl"},
    {"name": "Sheila Morgan",   "email": "sheilam@email.com",     "phone": "555-201-0020", "address": "73 Juniper Dr"},
    # Warming up (180-365 days)
    {"name": "Marcus Webb",     "email": "marcusw@email.com",     "phone": "555-201-0021", "address": "19 Birchwood Ct"},
    {"name": "Tanya Rhodes",    "email": "tanyr@email.com",       "phone": "555-201-0022", "address": "303 Elmwood Dr"},
    {"name": "Phil Garrett",    "email": "philg@email.com",       "phone": "555-201-0023", "address": "54 Lakeview Rd"},
    {"name": "Norma Castillo",  "email": "normac@email.com",      "phone": "555-201-0024", "address": "128 Riverside Ave"},
    # Recent (< 180 days)
    {"name": "Derek Yuen",      "email": "dereky@email.com",      "phone": "555-201-0025", "address": "77 Summit Way"},
    {"name": "Paula Stern",     "email": "paulas@email.com",      "phone": "555-201-0026", "address": "240 Park Blvd"},
    {"name": "Hank Novak",      "email": "hankn@email.com",       "phone": "555-201-0027", "address": "615 Hillcrest Dr"},
    {"name": "Joyce Osei",      "email": "joyceo@email.com",      "phone": "555-201-0028", "address": "82 Fernwood Ln"},
    {"name": "Ray Fontaine",    "email": "rayf@email.com",        "phone": "555-201-0029", "address": "391 Oakdale Rd"},
    {"name": "Carla Pineda",    "email": "carlap@email.com",      "phone": "555-201-0030", "address": "27 Brookside Ct"},
    # New leads (single install job)
    {"name": "Jake Moretti",    "email": "jakem@email.com",       "phone": "555-201-0031", "address": "508 Clearwater Dr"},
    {"name": "Nina Bashir",     "email": "ninab@email.com",       "phone": "555-201-0032", "address": "163 Terrace Ave"},
    {"name": "Clyde Reeves",    "email": "clyder@email.com",      "phone": "555-201-0033", "address": "44 Pinewood Blvd"},
    # End-of-life (very long dormant)
    {"name": "Irene Cobb",      "email": "irenec@email.com",      "phone": "555-201-0034", "address": "729 Walden Rd"},
    {"name": "Harold Simms",    "email": "harolds@email.com",     "phone": "555-201-0035", "address": "51 Edgewood Ct"},
    # Mixed
    {"name": "Bev Thornton",    "email": "bevt@email.com",        "phone": "555-201-0036", "address": "184 Clearfield St"},
    {"name": "Sam Keller",      "email": "samk@email.com",        "phone": "555-201-0037", "address": "62 Maplewood Ave"},
    {"name": "Rosa Delgado",    "email": "rosad@email.com",       "phone": "555-201-0038", "address": "317 Hillside Dr"},
    {"name": "Len Kowalski",    "email": "lenk@email.com",        "phone": "555-201-0039", "address": "88 Poplar St"},
    {"name": "Amy Chen",        "email": "amyc@email.com",        "phone": "555-201-0040", "address": "430 Creekside Rd"},
]

# (days_ago_range, num_jobs_range, spend_range, status, job_types)
PROFILES = [
    # High-value prime (0-7)
    (500, 700, 3, 5, 1800, 2800, "never_contacted", ["Furnace repair", "AC tune-up", "Annual maintenance"]),
    (420, 600, 3, 6, 1600, 2600, "never_contacted", ["AC tune-up", "Thermostat replacement", "Annual maintenance"]),
    (700, 900, 2, 4, 1500, 2200, "never_contacted", ["Furnace repair", "Emergency repair"]),
    (380, 500, 3, 5, 1700, 2400, "never_contacted", ["AC installation", "Annual maintenance", "Filter replacement"]),
    (400, 550, 2, 4, 1500, 2000, "never_contacted", ["AC tune-up", "Refrigerant recharge"]),
    (430, 650, 2, 5, 1600, 2500, "never_contacted", ["Heat pump service", "Heating inspection"]),
    (500, 750, 2, 4, 1400, 2100, "never_contacted", ["Boiler service", "Annual maintenance"]),
    (550, 800, 2, 3, 1200, 1900, "never_contacted", ["Furnace repair", "Duct cleaning"]),
    # Mid-value prime (8-14)
    (365, 500, 2, 3,  800, 1400, "never_contacted", ["AC tune-up", "Annual maintenance"]),
    (400, 600, 1, 3,  600, 1200, "never_contacted", ["Heating inspection", "Filter replacement"]),
    (370, 480, 2, 3,  900, 1400, "never_contacted", ["Furnace repair", "Thermostat replacement"]),
    (390, 520, 1, 2,  700, 1100, "never_contacted", ["AC tune-up", "Refrigerant recharge"]),
    (420, 580, 1, 3,  800, 1300, "never_contacted", ["Annual maintenance", "Duct cleaning"]),
    (440, 640, 1, 2,  500,  950, "never_contacted", ["Heating inspection", "Filter replacement"]),
    (365, 460, 1, 2,  600, 1000, "never_contacted", ["AC tune-up", "Emergency repair"]),
    # In sequence (15-17)
    (400, 600, 2, 4, 1100, 1800, "outreach_sent",   ["Furnace repair", "AC tune-up", "Annual maintenance"]),
    (450, 700, 1, 3,  900, 1500, "sequence_step_2", ["AC installation", "Filter replacement"]),
    (380, 520, 2, 3, 1200, 1900, "outreach_sent",   ["Heat pump service", "Heating inspection"]),
    # Replied / converted (18-19)
    (200, 350, 3, 5, 1800, 2600, "booked",  ["AC tune-up", "Annual maintenance", "Zone control install"]),
    (180, 300, 2, 4, 1400, 2200, "replied", ["Furnace repair", "Thermostat replacement"]),
    # Warming up (20-23)
    (200, 340, 1, 3,  700, 1300, "never_contacted", ["AC tune-up", "Annual maintenance"]),
    (220, 360, 1, 2,  600, 1100, "never_contacted", ["Heating inspection", "Filter replacement"]),
    (180, 320, 2, 3,  900, 1500, "never_contacted", ["Furnace repair", "Refrigerant recharge"]),
    (210, 350, 1, 2,  800, 1200, "never_contacted", ["Mini-split installation", "Annual maintenance"]),
    # Recent (24-29)
    ( 30,  90, 1, 2,  400,  900, "never_contacted", ["AC tune-up", "Filter replacement"]),
    ( 20,  70, 1, 2,  300,  700, "never_contacted", ["Heating inspection"]),
    ( 45, 110, 1, 3,  500, 1000, "never_contacted", ["Annual maintenance", "Thermostat replacement"]),
    ( 10,  50, 1, 1,  200,  500, "never_contacted", ["Filter replacement"]),
    ( 60, 150, 1, 2,  600, 1100, "never_contacted", ["AC tune-up", "Refrigerant recharge"]),
    ( 30, 100, 2, 3,  700, 1200, "never_contacted", ["Furnace repair", "Emergency repair"]),
    # New leads / single install (30-32)
    (120, 200, 1, 1, 1800, 2400, "never_contacted", ["AC installation"]),
    ( 90, 160, 1, 1, 2200, 3000, "never_contacted", ["Mini-split installation"]),
    (100, 180, 1, 1, 1500, 2200, "never_contacted", ["Heat pump service"]),
    # End-of-life (33-34)
    (800, 1100, 2, 4, 1200, 2000, "never_contacted", ["Furnace repair", "Annual maintenance"]),
    (900, 1300, 1, 3,  900, 1600, "never_contacted", ["AC tune-up", "Emergency repair"]),
    # Mixed (35-39)
    (250, 400, 2, 3, 1000, 1600, "never_contacted", ["Air quality inspection", "Duct cleaning"]),
    (300, 500, 1, 3,  800, 1400, "sequence_step_3", ["Annual maintenance", "Filter replacement"]),
    ( 90, 200, 1, 2,  600, 1000, "never_contacted", ["Heating inspection"]),
    (400, 600, 1, 2,  700, 1200, "never_contacted", ["AC tune-up", "Refrigerant recharge"]),
    ( 50, 130, 2, 3, 1100, 1700, "never_contacted", ["Furnace repair", "Thermostat replacement"]),
]

DRAFT_BODY = """Hey {name},

Hope you're doing well! It's been a while since we last came out — just wanted to check in and see if there's anything you need heading into the season.

If it's time for your annual tune-up or you've noticed anything off, I'd love to get something scheduled before things get busy. Should only take an hour.

Let me know what works!

Best, Arjuna"""


def reseed(db_url=None):
    import os
    if db_url:
        # NOTE: this only works if core modules haven't been imported yet.
        # Prefer: DATABASE_URL="..." python -m data.reseed
        os.environ['DATABASE_URL'] = db_url

    init_db()
    now = datetime.utcnow()

    with get_db() as db:
        # Wipe existing data (order matters for FK constraints)
        db.query(OutreachLog).delete()
        db.query(Job).delete()
        db.query(Customer).delete()
        db.query(Operator).delete()
        db.flush()

        # Create operator as Arjuna (connected Gmail account)
        operator = Operator(
            id=1,
            name="Arjuna Velayudam",
            business_name="Arjuna's HVAC Solutions",
            email="arjunavelayudam@gmail.com",
            phone="555-800-1234",
            niche="hvac",
            onboarding_complete=True,
        )
        operator.voice_profiles = [
            {"id": "vp_001", "name": "Arjuna", "role": "Owner"},
            {"id": "vp_002", "name": "Sarah",  "role": "Office Manager"},
        ]
        operator.tone_profile = {
            "formality": "casual",
            "greeting_style": "Hey [name],",
            "signoff_style": "Best, Arjuna",
            "sentence_length": "short",
            "humor": False,
            "emoji": False,
            "sample_phrases": [
                "Hope you had a great weekend",
                "Just wanted to check in",
                "Should only take an hour",
                "Let me know what works",
            ]
        }
        db.add(operator)
        db.flush()

        for i, c_data in enumerate(CUSTOMERS):
            profile = PROFILES[i]
            days_min, days_max, jobs_min, jobs_max, spend_min, spend_max, status, job_types = profile

            days_ago = random.randint(days_min, days_max)
            last_service = now - timedelta(days=days_ago)
            num_jobs = random.randint(jobs_min, jobs_max)
            total_spend = round(random.uniform(spend_min, spend_max), 2)
            last_svc_type = job_types[-1]  # most recent type

            customer = Customer(
                operator_id=1,
                name=c_data["name"],
                email=c_data["email"],
                phone=c_data["phone"],
                address=c_data["address"],
                last_service_date=last_service,
                last_service_type=last_svc_type,
                total_jobs=num_jobs,
                total_spend=total_spend,
                reactivation_status=status,
            )
            db.add(customer)
            db.flush()

            # Add job history — spread across the dormancy period
            per_job = round(total_spend / num_jobs, 2)
            for j in range(num_jobs):
                svc = job_types[j % len(job_types)]
                completed = last_service - timedelta(days=j * random.randint(180, 400))
                db.add(Job(
                    operator_id=1,
                    customer_id=customer.id,
                    service_type=svc,
                    scheduled_at=completed,
                    completed_at=completed,
                    status="complete",
                    amount=per_job,
                ))

            # Add outreach logs for customers in-sequence
            if status in ("outreach_sent", "sequence_step_2", "sequence_step_3"):
                step = {"outreach_sent": 0, "sequence_step_2": 1, "sequence_step_3": 2}[status]
                for s in range(step + 1):
                    sent_at = now - timedelta(days=(step - s) * 7 + random.randint(1, 5))
                    db.add(OutreachLog(
                        operator_id=1,
                        customer_id=customer.id,
                        channel="email",
                        direction="outbound",
                        subject=f"Checking in, {c_data['name'].split()[0]}",
                        content=DRAFT_BODY.format(name=c_data["name"].split()[0]),
                        dry_run=(s == step),  # latest is still queued
                        sequence_step=s,
                        sent_at=sent_at,
                    ))

            # Add reply log for replied/booked customers
            if status in ("replied", "booked"):
                db.add(OutreachLog(
                    operator_id=1,
                    customer_id=customer.id,
                    channel="email",
                    direction="outbound",
                    subject=f"Checking in, {c_data['name'].split()[0]}",
                    content=DRAFT_BODY.format(name=c_data["name"].split()[0]),
                    dry_run=False,
                    sequence_step=0,
                    sent_at=now - timedelta(days=random.randint(10, 30)),
                ))
                db.add(OutreachLog(
                    operator_id=1,
                    customer_id=customer.id,
                    channel="email",
                    direction="inbound",
                    subject=f"Re: Checking in, {c_data['name'].split()[0]}",
                    content=f"Hey! Yeah let's do it. I've been meaning to call. What times work for you?",
                    dry_run=False,
                    sequence_step=0,
                    sent_at=now - timedelta(days=random.randint(5, 15)),
                ))

        print(f"✅ Reseeded: 1 operator (Arjuna), {len(CUSTOMERS)} customers")


if __name__ == "__main__":
    import sys
    # DATABASE_URL must be set in the environment BEFORE importing core modules.
    # Correct usage: DATABASE_URL="postgresql://..." python -m data.reseed
    # The db_url arg is kept for backwards compat but env var is the reliable path.
    db_url = sys.argv[1] if len(sys.argv) > 1 else None
    reseed(db_url)

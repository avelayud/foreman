"""
data/seed.py
Seeds the database with a sample operator and realistic HVAC customer data.
Run once to set up your dev environment:  python main.py --seed
"""

from datetime import datetime, timedelta
import random
from core.database import init_db, get_db
from core.models import Operator, Customer, Job


SAMPLE_SERVICE_TYPES = [
    "AC tune-up", "Heating inspection", "Furnace repair",
    "AC installation", "Duct cleaning", "Thermostat replacement",
    "Refrigerant recharge", "Emergency repair", "Annual maintenance"
]

SAMPLE_CUSTOMERS = [
    {"name": "Tom Harrington", "email": "tom.h@email.com", "phone": "555-201-0001", "address": "142 Oak St"},
    {"name": "Sandra Patel", "email": "sandra.p@email.com", "phone": "555-201-0002", "address": "87 Maple Ave"},
    {"name": "Rick Deluca", "email": "rick.d@email.com", "phone": "555-201-0003", "address": "310 Pine Rd"},
    {"name": "Maria Gonzalez", "email": "mariag@email.com", "phone": "555-201-0004", "address": "55 Birch Ln"},
    {"name": "James Whitfield", "email": "jwhit@email.com", "phone": "555-201-0005", "address": "209 Cedar Dr"},
    {"name": "Donna Kowalski", "email": "donnakow@email.com", "phone": "555-201-0006", "address": "401 Elm St"},
    {"name": "Brian Nguyen", "email": "briann@email.com", "phone": "555-201-0007", "address": "67 Spruce Ct"},
    {"name": "Linda Foster", "email": "lindaf@email.com", "phone": "555-201-0008", "address": "890 Walnut Blvd"},
    {"name": "Kevin Okafor", "email": "kevinokafor@email.com", "phone": "555-201-0009", "address": "33 Aspen Way"},
    {"name": "Cheryl Banks", "email": "cherylb@email.com", "phone": "555-201-0010", "address": "147 Hickory Pl"},
    {"name": "Dave Marchetti", "email": "davem@email.com", "phone": "555-201-0011", "address": "522 Poplar St"},
    {"name": "Anita Russo", "email": "anitar@email.com", "phone": "555-201-0012", "address": "78 Willow Way"},
    {"name": "Greg Tillman", "email": "gregt@email.com", "phone": "555-201-0013", "address": "190 Magnolia Dr"},
    {"name": "Faye Chambers", "email": "fayec@email.com", "phone": "555-201-0014", "address": "44 Cypress Ln"},
    {"name": "Earl Hutchinson", "email": "earlh@email.com", "phone": "555-201-0015", "address": "365 Sycamore Rd"},
    {"name": "Patty Simmons", "email": "pattys@email.com", "phone": "555-201-0016", "address": "88 Dogwood Ave"},
    {"name": "Wayne Brennan", "email": "wayneb@email.com", "phone": "555-201-0017", "address": "227 Redwood Ct"},
    {"name": "Josie Larkin", "email": "josiel@email.com", "phone": "555-201-0018", "address": "91 Chestnut Blvd"},
    {"name": "Carl Estrada", "email": "carle@email.com", "phone": "555-201-0019", "address": "416 Linden St"},
    {"name": "Sheila Morgan", "email": "sheilam@email.com", "phone": "555-201-0020", "address": "73 Juniper Dr"},
]


def seed():
    init_db()

    with get_db() as db:
        # Check if already seeded
        existing = db.query(Operator).filter_by(business_name="Mike's HVAC Solutions").first()
        if existing:
            print("⚠️  Database already seeded. Skipping.")
            return

        # Create sample operator
        operator = Operator(
            name="Mike Kowalczyk",
            business_name="Mike's HVAC Solutions",
            email="mike@mikeshvac.com",
            phone="555-800-1234",
            niche="hvac",
            onboarding_complete=False,
        )
        db.add(operator)
        db.flush()  # Get operator.id

        now = datetime.utcnow()

        for c_data in SAMPLE_CUSTOMERS:
            # Randomize last service date
            # Mix of: very old (2+ yrs), old (1-2 yrs), recent (< 1yr)
            days_ago = random.choice([
                random.randint(400, 900),   # Prime reactivation target
                random.randint(400, 900),   # Weight toward older
                random.randint(180, 399),   # Edge cases
                random.randint(30, 179),    # Recent — should NOT be targeted
            ])
            last_service = now - timedelta(days=days_ago)
            service_type = random.choice(SAMPLE_SERVICE_TYPES)
            num_jobs = random.randint(1, 6)
            total_spend = round(random.uniform(150, 2400), 2)

            customer = Customer(
                operator_id=operator.id,
                name=c_data["name"],
                email=c_data["email"],
                phone=c_data["phone"],
                address=c_data["address"],
                last_service_date=last_service,
                last_service_type=service_type,
                total_jobs=num_jobs,
                total_spend=total_spend,
                reactivation_status="never_contacted",
            )
            db.add(customer)
            db.flush()

            # Add a job record for the last service
            job = Job(
                operator_id=operator.id,
                customer_id=customer.id,
                service_type=service_type,
                scheduled_at=last_service,
                completed_at=last_service,
                status="complete",
                amount=round(total_spend / num_jobs, 2),
            )
            db.add(job)

        print(f"✅ Seeded operator '{operator.business_name}' with {len(SAMPLE_CUSTOMERS)} customers.")
        print("   Run `python main.py` to start the agent.")


if __name__ == "__main__":
    seed()

"""
data/reseed.py
Full wipe + reseed with 200 customers.

Customer breakdown:
  -   8  live email customers (real addresses, never_contacted, clean for real simulation)
  -  40  scenario customers   (named, rich multi-turn email conversations)
  - 152  bulk generated       (name/profile pools, realistic HVAC histories)

Scenario types: price_haggler, scheduling_negotiation, callback_then_email,
  maybe_next_month, multiple_questions, reschedule, not_interested, straightforward_book

Quick run:
  # Railway (use public proxy URL — never the internal postgres.railway.internal from local):
  DATABASE_URL="postgresql://postgres:<pass>@hopper.proxy.rlwy.net:26095/railway" \\
    venv/bin/python -m data.reseed

  # Local SQLite:
  DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m data.reseed

See data/README.md for full documentation: adding live emails, new scenarios,
augmenting bulk profiles, and re-running safely.
"""

from datetime import datetime, timedelta
import random
import json

from core.database import init_db, get_db
from core.models import Operator, Customer, Job, OutreachLog, Booking

random.seed(42)
NOW = datetime.utcnow()

SERVICE_TYPES = [
    "AC tune-up", "Heating inspection", "Furnace repair",
    "AC installation", "Duct cleaning", "Thermostat replacement",
    "Refrigerant recharge", "Emergency repair", "Annual maintenance",
    "Heat pump service", "Mini-split installation", "Filter replacement",
    "Boiler service", "Zone control install", "Air quality inspection",
]

JOB_TYPE_POOLS = {
    "maintenance": ["AC tune-up", "Heating inspection", "Annual maintenance", "Filter replacement", "Air quality inspection"],
    "install":     ["AC installation", "Mini-split installation", "Zone control install", "Heat pump service"],
    "repair":      ["Furnace repair", "Refrigerant recharge", "Emergency repair", "Thermostat replacement", "Boiler service", "Duct cleaning"],
    "mixed":       SERVICE_TYPES,
}


# ── Email content helpers ─────────────────────────────────────────────────────

def _initial_outreach(first):
    return (
        f"Hey {first},\n\n"
        "Hope you're doing well! It's been a while since we last came out — just wanted to check in "
        "and see if there's anything you need heading into the season.\n\n"
        "If it's time for your annual tune-up or you've noticed anything off, I'd love to get "
        "something scheduled before things get busy. Should only take an hour.\n\n"
        "Let me know what works!\n\nBest, Arjuna"
    )

def _pricing_response(first, price=129, service="AC tune-up"):
    return (
        f"Hey {first}!\n\n"
        f"A standard {service} is ${price}. That includes a full system inspection, coil cleaning, "
        "refrigerant level check, and we'll flag anything that needs attention before it becomes a bigger issue.\n\n"
        "Happy to schedule — what does your availability look like?\n\nBest, Arjuna"
    )

def _haggle_response(first, price=110):
    return (
        f"Hey {first},\n\n"
        f"I hear you — I can do ${price} if we can get something on the calendar in the next couple weeks. "
        "Same full service, nothing cut short. Want me to find a time that works?\n\nBest, Arjuna"
    )

def _slot_proposal(first, s1, s2, s3):
    return (
        f"Hey {first},\n\n"
        f"I have {s1}, {s2}, or {s3}. Any of those work for you?\n\nBest, Arjuna"
    )

def _booking_confirm(first, slot):
    return (
        f"Hey {first},\n\n"
        f"Perfect — I've got you down for {slot}. I'll send a reminder the day before. "
        "Feel free to reach out if anything comes up.\n\nSee you then!\nBest, Arjuna"
    )

def _reschedule_confirm(first, slot):
    return (
        f"Hey {first},\n\n"
        f"No problem at all! I've moved you to {slot}. See you then.\n\nBest, Arjuna"
    )

def _followup_1(first):
    return (
        f"Hey {first},\n\n"
        "Just circling back — still have some openings this week and next if you'd like to lock "
        "something in. No rush, just wanted to make sure the timing works out.\n\nBest, Arjuna"
    )

def _followup_2(first):
    return (
        f"Hey {first},\n\n"
        "One more check-in — schedule is filling up for the month. Happy to hold a spot for you "
        "if this is a good time. Otherwise totally understand.\n\nBest, Arjuna"
    )

def _callback_offer(first):
    return (
        f"Hey {first},\n\n"
        "Of course! I can give you a call. Also happy to sort it out over email if that's easier — "
        "sometimes quicker. Whatever works best for you.\n\nBest, Arjuna"
    )

def _service_detail(first):
    return (
        f"Hey {first},\n\n"
        "Great question! The tune-up covers:\n"
        "- Full system inspection (indoor + outdoor units)\n"
        "- Condenser coil cleaning\n"
        "- Refrigerant level check\n"
        "- Electrical connection tightening\n"
        "- Filter check + replacement if needed\n"
        "- Thermostat calibration\n\n"
        "We'll walk you through anything we find before doing any extra work.\n\nBest, Arjuna"
    )

def _duct_info(first):
    return (
        f"Hey {first},\n\n"
        "Duct cleaning is a separate service — typically $275–325 depending on the size of the home. "
        "We can bundle both the tune-up and duct cleaning and I'll knock 10% off the total. "
        "Let me know if you'd want both.\n\nBest, Arjuna"
    )

def _duration_response(first):
    return (
        f"Hey {first},\n\n"
        "Usually 45 minutes to an hour for the tune-up. If we find something that needs fixing "
        "we'll walk you through the options before doing anything extra — no surprises.\n\nBest, Arjuna"
    )


# ── Log + booking generators ──────────────────────────────────────────────────

def _add_jobs(db, customer_id, last_service, num_jobs, total_spend, job_types):
    per_job = round(total_spend / num_jobs, 2)
    for j in range(num_jobs):
        svc = job_types[j % len(job_types)]
        completed = last_service - timedelta(days=j * random.randint(180, 400))
        db.add(Job(
            operator_id=1, customer_id=customer_id,
            service_type=svc, scheduled_at=completed, completed_at=completed,
            status="complete", amount=per_job,
        ))


def _add_booking(db, customer_id, service_type):
    days_out = random.randint(5, 21)
    hour = random.choice([9, 10, 11, 13, 14, 15])
    start = NOW + timedelta(days=days_out, hours=hour)
    db.add(Booking(
        operator_id=1, customer_id=customer_id,
        slot_start=start, slot_end=start + timedelta(hours=1, minutes=30),
        status=random.choice(["tentative", "confirmed"]),
        source="ai_outreach", service_type=service_type,
    ))


def _log(db, customer_id, days_ago, direction, subject, content,
         dry_run=False, seq=0, approval="sent", classification=None):
    db.add(OutreachLog(
        operator_id=1, customer_id=customer_id,
        channel="email", direction=direction,
        subject=subject, content=content,
        sent_at=NOW - timedelta(days=days_ago),
        dry_run=dry_run, sequence_step=seq,
        approval_status=approval,
        response_classification=classification,
        classified_at=(NOW - timedelta(days=days_ago)) if classification else None,
    ))


def _add_scenario_logs(db, customer_id, first_name, scenario, service_type):
    """Add multi-turn conversation logs. Returns final reactivation_status."""
    subj = f"Checking in, {first_name}"
    re_subj = f"Re: Checking in, {first_name}"

    if scenario == "price_haggler":
        b = random.randint(28, 42)
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 3, "inbound",  re_subj, "Hey! Quick question — how much does a tune-up usually run these days?", seq=0)
        _log(db, customer_id, b - 4, "outbound", re_subj, _pricing_response(first_name, 129), seq=1)
        _log(db, customer_id, b - 6, "inbound",  re_subj, "That's a little more than I expected. Any chance you could do $99?", seq=1)
        _log(db, customer_id, b - 7, "outbound", re_subj, _haggle_response(first_name, 110), seq=2)
        _log(db, customer_id, b - 9, "inbound",  re_subj, "OK deal. What times do you have available?", seq=2)
        _log(db, customer_id, b-10,  "outbound", re_subj, _slot_proposal(first_name, "Tuesday the 18th at 10am", "Wednesday the 19th at 2pm", "Thursday the 20th at 9am"), seq=3)
        _log(db, customer_id, b-12,  "inbound",  re_subj, "The Tuesday works! See you then.", seq=3, classification="booking_intent")
        _add_booking(db, customer_id, service_type)
        return "booked"

    elif scenario == "scheduling_negotiation":
        b = random.randint(28, 42)
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 3, "inbound",  re_subj, "Hi! Yes it's definitely time. What does your schedule look like this week?", seq=0)
        _log(db, customer_id, b - 4, "outbound", re_subj, _slot_proposal(first_name, "Thursday at 11am", "Friday at 9am", "Monday the 22nd at 2pm"), seq=1)
        _log(db, customer_id, b - 6, "inbound",  re_subj, "Thursday doesn't work and I'm out of town Friday. What do you have the following week?", seq=1)
        _log(db, customer_id, b - 7, "outbound", re_subj, _slot_proposal(first_name, "Tuesday the 25th at 10am", "Tuesday the 25th at 2pm", "Wednesday the 26th at 9am"), seq=2)
        _log(db, customer_id, b - 9, "inbound",  re_subj, "Tuesday at 2pm is perfect. I'll put it in my calendar.", seq=2, classification="booking_intent")
        _log(db, customer_id, b-10,  "outbound", re_subj, _booking_confirm(first_name, "Tuesday the 25th at 2pm"), seq=3)
        _add_booking(db, customer_id, service_type)
        return "booked"

    elif scenario == "callback_then_email":
        b = random.randint(22, 35)
        phone = f"555-{random.randint(200,899):03d}-{random.randint(1000,9999):04d}"
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 3, "inbound",  re_subj, f"Hey, could you give me a call? My cell is {phone}.", seq=0)
        _log(db, customer_id, b - 4, "outbound", re_subj, _callback_offer(first_name), seq=1)
        _log(db, customer_id, b - 6, "inbound",  re_subj, "Actually email is easier honestly. What times do you have available next week?", seq=1)
        _log(db, customer_id, b - 7, "outbound", re_subj, _slot_proposal(first_name, "Monday the 21st at 10am", "Wednesday the 23rd at 2pm", "Thursday the 24th at 9am"), seq=2)
        _log(db, customer_id, b - 9, "inbound",  re_subj, "Wednesday at 2pm works! See you then.", seq=2, classification="booking_intent")
        _log(db, customer_id, b-10,  "outbound", re_subj, _booking_confirm(first_name, "Wednesday the 23rd at 2pm"), seq=3)
        _add_booking(db, customer_id, service_type)
        return "booked"

    elif scenario == "maybe_next_month":
        b = random.randint(48, 65)
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 4, "inbound",  re_subj, "Hi! Things are pretty hectic over here right now — can you reach back out in a month or so?", seq=0)
        _log(db, customer_id, b-14,  "outbound", re_subj, _followup_1(first_name), seq=1)
        _log(db, customer_id, b-28,  "outbound", re_subj, _followup_2(first_name), seq=2)
        _log(db, customer_id, b-35,  "inbound",  re_subj, "Actually you know what, now is a pretty good time. What's your availability this week?", seq=2, classification="booking_intent")
        # Pending slot proposal (in queue, not yet sent)
        _log(db, customer_id, b-36,  "outbound", re_subj,
             _slot_proposal(first_name, "Tuesday at 10am", "Wednesday at 2pm", "Thursday at 9am"),
             dry_run=True, seq=3, approval="pending")
        return "replied"

    elif scenario == "multiple_questions":
        b = random.randint(28, 42)
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 3, "inbound",  re_subj, "Hi Arjuna! What exactly is included in the tune-up service?", seq=0)
        _log(db, customer_id, b - 4, "outbound", re_subj, _service_detail(first_name), seq=1)
        _log(db, customer_id, b - 6, "inbound",  re_subj, "Do you also do duct cleaning or is that a separate thing?", seq=1)
        _log(db, customer_id, b - 7, "outbound", re_subj, _duct_info(first_name), seq=2)
        _log(db, customer_id, b - 9, "inbound",  re_subj, "And roughly how long does the tune-up take? Trying to plan around my work schedule.", seq=2)
        _log(db, customer_id, b-10,  "outbound", re_subj, _duration_response(first_name), seq=3)
        _log(db, customer_id, b-12,  "inbound",  re_subj, "OK that all sounds good. When do you have availability?", seq=3, classification="booking_intent")
        _log(db, customer_id, b-13,  "outbound", re_subj, _slot_proposal(first_name, "Tuesday the 18th at 10am", "Friday the 21st at 9am", "Monday the 24th at 2pm"), seq=4)
        _log(db, customer_id, b-15,  "inbound",  re_subj, "Friday at 9am works great. See you then!", seq=4, classification="booking_intent")
        _log(db, customer_id, b-16,  "outbound", re_subj, _booking_confirm(first_name, "Friday the 21st at 9am"), seq=5)
        _add_booking(db, customer_id, service_type)
        return "booked"

    elif scenario == "reschedule":
        b = random.randint(38, 55)
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 4, "inbound",  re_subj, "Hey yes! When do you have availability?", seq=0)
        _log(db, customer_id, b - 5, "outbound", re_subj, _slot_proposal(first_name, "Monday the 14th at 10am", "Wednesday the 16th at 2pm", "Friday the 18th at 9am"), seq=1)
        _log(db, customer_id, b - 7, "inbound",  re_subj, "Monday at 10am works for me!", seq=1, classification="booking_intent")
        _log(db, customer_id, b - 8, "outbound", re_subj, _booking_confirm(first_name, "Monday the 14th at 10am"), seq=2)
        _log(db, customer_id, b-15,  "inbound",  re_subj, "Hey Arjuna — I'm so sorry, something came up. Any chance we can move to Wednesday instead?", seq=2)
        _log(db, customer_id, b-16,  "outbound", re_subj, _reschedule_confirm(first_name, "Wednesday the 16th at 10am"), seq=3)
        _add_booking(db, customer_id, service_type)
        return "booked"

    elif scenario == "not_interested":
        b = random.randint(20, 40)
        replies = [
            "Not interested at this time, thanks.",
            "We've switched to a different HVAC company.",
            "Please don't email me anymore.",
            "Not interested — please remove me from your list.",
            "Thanks but no thanks.",
        ]
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 5, "inbound",  re_subj, random.choice(replies), seq=0, classification="not_interested")
        return "unsubscribed"

    elif scenario == "straightforward_book":
        b = random.randint(22, 35)
        replies = [
            "Hi! Yes I've been meaning to reach out. When can you come by?",
            "Hey! Great timing — I was just thinking about this. What do you have available?",
            "Yes! It's definitely time. When are you free?",
            "Hi Arjuna! Would love to get something scheduled. What times work?",
            "Good to hear from you! Yes let's do it. What's your availability?",
        ]
        _log(db, customer_id, b,     "outbound", subj,    _initial_outreach(first_name), seq=0)
        _log(db, customer_id, b - 3, "inbound",  re_subj, random.choice(replies), seq=0, classification="booking_intent")
        _log(db, customer_id, b - 4, "outbound", re_subj, _slot_proposal(first_name, "Tuesday the 18th at 10am", "Thursday the 20th at 2pm", "Friday the 21st at 9am"), seq=1)
        _log(db, customer_id, b - 6, "inbound",  re_subj, "Thursday at 2pm works perfectly.", seq=1, classification="booking_intent")
        _log(db, customer_id, b - 7, "outbound", re_subj, _booking_confirm(first_name, "Thursday the 20th at 2pm"), seq=2)
        _add_booking(db, customer_id, service_type)
        return "booked"

    return "never_contacted"


def _add_sequence_logs(db, customer_id, first_name, status):
    step = {"outreach_sent": 0, "sequence_step_2": 1, "sequence_step_3": 2}[status]
    subj = f"Checking in, {first_name}"
    contents = [_initial_outreach(first_name), _followup_1(first_name), _followup_2(first_name)]
    for s in range(step + 1):
        sent = NOW - timedelta(days=(step - s) * 7 + random.randint(1, 5))
        is_latest = (s == step)
        db.add(OutreachLog(
            operator_id=1, customer_id=customer_id,
            channel="email", direction="outbound",
            subject=subj, content=contents[s],
            sent_at=sent,
            dry_run=is_latest,
            sequence_step=s,
            approval_status="pending" if is_latest else "sent",
        ))


# ── Live email customers (8) ──────────────────────────────────────────────────

LIVE_CUSTOMERS = [
    {
        "name": "Harold Simmons", "email": "hsimmons921@gmail.com",
        "phone": "555-301-0001", "address": "142 Oak Street, Atlanta, GA 30301",
        "days_dormant": 520, "num_jobs": 4, "total_spend": 2340.00,
        "job_types": ["Annual maintenance", "AC tune-up", "Furnace repair", "Thermostat replacement"],
    },
    {
        "name": "Arjun Velayudam", "email": "arjun.velayudam99@gmail.com",
        "phone": "555-301-0002", "address": "87 Maple Avenue, Decatur, GA 30030",
        "days_dormant": 410, "num_jobs": 3, "total_spend": 1890.00,
        "job_types": ["AC tune-up", "Refrigerant recharge", "Heating inspection"],
    },
    {
        "name": "Sarah Parsons", "email": "sparsons313@gmail.com",
        "phone": "555-301-0003", "address": "309 Birch Lane, Marietta, GA 30060",
        "days_dormant": 475, "num_jobs": 5, "total_spend": 2680.00,
        "job_types": ["AC installation", "Annual maintenance", "Filter replacement", "Duct cleaning", "AC tune-up"],
    },
    {
        "name": "Chris Tucker", "email": "christuck769@gmail.com",
        "phone": "555-301-0004", "address": "55 Walnut Drive, Kennesaw, GA 30144",
        "days_dormant": 395, "num_jobs": 3, "total_spend": 1540.00,
        "job_types": ["Furnace repair", "Annual maintenance", "Emergency repair"],
    },
    {
        "name": "Sam Keller", "email": "samkeller716@gmail.com",
        "phone": "555-301-0005", "address": "220 Pine Road, Smyrna, GA 30080",
        "days_dormant": 445, "num_jobs": 4, "total_spend": 1960.00,
        "job_types": ["Heat pump service", "Annual maintenance", "AC tune-up", "Filter replacement"],
    },
    {
        "name": "Arjuna Velayudam", "email": "velayudam.arj@gmail.com",
        "phone": "555-301-0006", "address": "108 Cypress Court, Sandy Springs, GA 30328",
        "days_dormant": 380, "num_jobs": 2, "total_spend": 980.00,
        "job_types": ["Boiler service", "Heating inspection"],
    },
    {
        "name": "Kate Dawson", "email": "kated.kitkat@gmail.com",
        "phone": "555-301-0007", "address": "67 Spruce Way, Tucker, GA 30084",
        "days_dormant": 500, "num_jobs": 4, "total_spend": 2150.00,
        "job_types": ["Mini-split installation", "Annual maintenance", "AC tune-up", "Air quality inspection"],
    },
    {
        "name": "AV Test", "email": "velayudamarjuna@gmail.com",
        "phone": "555-301-0008", "address": "402 Redwood Circle, Alpharetta, GA 30022",
        "days_dormant": 430, "num_jobs": 3, "total_spend": 1720.00,
        "job_types": ["Zone control install", "AC tune-up", "Annual maintenance"],
    },
]


# ── Scenario customers (40) ───────────────────────────────────────────────────

SCENARIO_CUSTOMERS = [
    # Price hagglers → booked (6)
    {"name": "Patricia Simmons",  "email": "patsimm@email.com",    "phone": "555-401-0001", "address": "88 Dogwood Ave, Roswell, GA 30075",         "days_dormant": 540, "num_jobs": 4, "total_spend": 2280, "job_types": ["Furnace repair", "AC tune-up", "Annual maintenance", "Filter replacement"], "scenario": "price_haggler"},
    {"name": "Dave Marchetti",    "email": "davem@email.com",       "phone": "555-401-0002", "address": "522 Poplar St, Norcross, GA 30093",         "days_dormant": 480, "num_jobs": 3, "total_spend": 1750, "job_types": ["AC tune-up", "Thermostat replacement", "Annual maintenance"],            "scenario": "price_haggler"},
    {"name": "Josie Larkin",      "email": "josiel@email.com",      "phone": "555-401-0003", "address": "91 Chestnut Blvd, Duluth, GA 30096",        "days_dormant": 420, "num_jobs": 3, "total_spend": 1620, "job_types": ["Heating inspection", "Annual maintenance", "Refrigerant recharge"],      "scenario": "price_haggler"},
    {"name": "Wayne Brennan",     "email": "wayneb@email.com",      "phone": "555-401-0004", "address": "227 Redwood Ct, Lawrenceville, GA 30044",    "days_dormant": 390, "num_jobs": 2, "total_spend": 1150, "job_types": ["AC tune-up", "Refrigerant recharge"],                                   "scenario": "price_haggler"},
    {"name": "Donna Kowalski",    "email": "donnakow@email.com",    "phone": "555-401-0005", "address": "401 Elm St, Peachtree City, GA 30269",       "days_dormant": 460, "num_jobs": 4, "total_spend": 2100, "job_types": ["Furnace repair", "Annual maintenance", "Duct cleaning", "Filter replacement"], "scenario": "price_haggler"},
    {"name": "Rick Deluca",       "email": "rick.d@email.com",      "phone": "555-401-0006", "address": "310 Pine Rd, Woodstock, GA 30188",           "days_dormant": 510, "num_jobs": 3, "total_spend": 1890, "job_types": ["AC installation", "Annual maintenance", "AC tune-up"],                 "scenario": "price_haggler"},
    # Scheduling negotiation → booked (6)
    {"name": "Marcus Webb",       "email": "marcusw@email.com",     "phone": "555-401-0007", "address": "19 Birchwood Ct, Cumming, GA 30040",         "days_dormant": 370, "num_jobs": 3, "total_spend": 1480, "job_types": ["AC tune-up", "Annual maintenance", "Thermostat replacement"],           "scenario": "scheduling_negotiation"},
    {"name": "Linda Foster",      "email": "lindaf@email.com",      "phone": "555-401-0008", "address": "890 Walnut Blvd, Canton, GA 30114",          "days_dormant": 500, "num_jobs": 4, "total_spend": 2060, "job_types": ["Furnace repair", "AC tune-up", "Annual maintenance", "Filter replacement"], "scenario": "scheduling_negotiation"},
    {"name": "Anita Russo",       "email": "anitar@email.com",      "phone": "555-401-0009", "address": "78 Willow Way, Acworth, GA 30101",            "days_dormant": 415, "num_jobs": 3, "total_spend": 1320, "job_types": ["Heating inspection", "Annual maintenance", "Air quality inspection"],   "scenario": "scheduling_negotiation"},
    {"name": "Greg Tillman",      "email": "gregt@email.com",       "phone": "555-401-0010", "address": "190 Magnolia Dr, McDonough, GA 30252",        "days_dormant": 560, "num_jobs": 3, "total_spend": 1780, "job_types": ["Boiler service", "Annual maintenance", "Filter replacement"],          "scenario": "scheduling_negotiation"},
    {"name": "Tanya Rhodes",      "email": "tanyr@email.com",       "phone": "555-401-0011", "address": "303 Elmwood Dr, Conyers, GA 30012",           "days_dormant": 430, "num_jobs": 2, "total_spend": 970,  "job_types": ["AC tune-up", "Refrigerant recharge"],                                   "scenario": "scheduling_negotiation"},
    {"name": "Phil Garrett",      "email": "philg@email.com",       "phone": "555-401-0012", "address": "54 Lakeview Rd, Stockbridge, GA 30281",       "days_dormant": 380, "num_jobs": 3, "total_spend": 1560, "job_types": ["Mini-split installation", "Annual maintenance", "AC tune-up"],          "scenario": "scheduling_negotiation"},
    # Callback → email → booked (4)
    {"name": "Sandra Patel",      "email": "sandra.p@email.com",    "phone": "555-401-0013", "address": "87 Maple Ave, Lithonia, GA 30058",            "days_dormant": 440, "num_jobs": 4, "total_spend": 2380, "job_types": ["Heat pump service", "Annual maintenance", "Heating inspection", "Filter replacement"], "scenario": "callback_then_email"},
    {"name": "Earl Hutchinson",   "email": "earlh@email.com",       "phone": "555-401-0014", "address": "365 Sycamore Rd, Snellville, GA 30039",       "days_dormant": 490, "num_jobs": 3, "total_spend": 1690, "job_types": ["Furnace repair", "AC tune-up", "Annual maintenance"],                  "scenario": "callback_then_email"},
    {"name": "Norma Castillo",    "email": "normac@email.com",      "phone": "555-401-0015", "address": "128 Riverside Ave, Buford, GA 30518",         "days_dormant": 395, "num_jobs": 2, "total_spend": 1100, "job_types": ["Duct cleaning", "Annual maintenance"],                                  "scenario": "callback_then_email"},
    {"name": "Brian Nguyen",      "email": "briann@email.com",      "phone": "555-401-0016", "address": "67 Spruce Ct, Sugar Hill, GA 30518",          "days_dormant": 425, "num_jobs": 3, "total_spend": 1580, "job_types": ["Zone control install", "AC tune-up", "Thermostat replacement"],         "scenario": "callback_then_email"},
    # Maybe next month → re-engaged (5)
    {"name": "Faye Chambers",     "email": "fayec@email.com",       "phone": "555-401-0017", "address": "44 Cypress Ln, Gainesville, GA 30501",        "days_dormant": 700, "num_jobs": 3, "total_spend": 1650, "job_types": ["Furnace repair", "Emergency repair", "Annual maintenance"],            "scenario": "maybe_next_month"},
    {"name": "Tom Harrington",    "email": "tom.h@email.com",       "phone": "555-401-0018", "address": "142 Oak St, Gainesville, GA 30504",           "days_dormant": 580, "num_jobs": 4, "total_spend": 2190, "job_types": ["AC tune-up", "Annual maintenance", "Refrigerant recharge", "Filter replacement"], "scenario": "maybe_next_month"},
    {"name": "James Whitfield",   "email": "jwhit@email.com",       "phone": "555-401-0019", "address": "209 Cedar Dr, Flowery Branch, GA 30542",      "days_dormant": 620, "num_jobs": 3, "total_spend": 1870, "job_types": ["Heat pump service", "Heating inspection", "Annual maintenance"],       "scenario": "maybe_next_month"},
    {"name": "Cheryl Banks",      "email": "cherylb@email.com",     "phone": "555-401-0020", "address": "147 Hickory Pl, Braselton, GA 30517",         "days_dormant": 760, "num_jobs": 5, "total_spend": 2890, "job_types": ["AC installation", "Annual maintenance", "AC tune-up", "Filter replacement", "Duct cleaning"], "scenario": "maybe_next_month"},
    {"name": "Kevin Okafor",      "email": "kevinokafor@email.com", "phone": "555-401-0021", "address": "33 Aspen Way, Jefferson, GA 30549",           "days_dormant": 530, "num_jobs": 3, "total_spend": 1440, "job_types": ["Thermostat replacement", "AC tune-up", "Refrigerant recharge"],         "scenario": "maybe_next_month"},
    # Multiple questions → booked (5)
    {"name": "Maria Gonzalez",    "email": "mariag@email.com",      "phone": "555-401-0022", "address": "55 Birch Ln, Commerce, GA 30529",             "days_dormant": 455, "num_jobs": 3, "total_spend": 1360, "job_types": ["Annual maintenance", "Duct cleaning", "Filter replacement"],            "scenario": "multiple_questions"},
    {"name": "Carl Estrada",      "email": "carle@email.com",       "phone": "555-401-0023", "address": "416 Linden St, Monroe, GA 30655",             "days_dormant": 490, "num_jobs": 2, "total_spend": 920,  "job_types": ["AC tune-up", "Thermostat replacement"],                                 "scenario": "multiple_questions"},
    {"name": "Patty Rios",        "email": "pattyr@email.com",      "phone": "555-401-0024", "address": "82 Fernwood Ln, Winder, GA 30680",            "days_dormant": 380, "num_jobs": 3, "total_spend": 1580, "job_types": ["Furnace repair", "Annual maintenance", "Air quality inspection"],       "scenario": "multiple_questions"},
    {"name": "Derek Yuen",        "email": "dereky@email.com",      "phone": "555-401-0025", "address": "77 Summit Way, Athens, GA 30601",             "days_dormant": 400, "num_jobs": 2, "total_spend": 1080, "job_types": ["Heat pump service", "Annual maintenance"],                             "scenario": "multiple_questions"},
    {"name": "Paula Stern",       "email": "paulas@email.com",      "phone": "555-401-0026", "address": "240 Park Blvd, Watkinsville, GA 30677",       "days_dormant": 440, "num_jobs": 4, "total_spend": 2020, "job_types": ["Mini-split installation", "AC tune-up", "Annual maintenance", "Filter replacement"], "scenario": "multiple_questions"},
    # Books then reschedules → booked (4)
    {"name": "Sheila Morgan",     "email": "sheilam@email.com",     "phone": "555-401-0027", "address": "73 Juniper Dr, Bogart, GA 30622",             "days_dormant": 490, "num_jobs": 3, "total_spend": 1460, "job_types": ["Furnace repair", "Annual maintenance", "Heating inspection"],           "scenario": "reschedule"},
    {"name": "Hank Novak",        "email": "hankn@email.com",       "phone": "555-401-0028", "address": "615 Hillcrest Dr, Social Circle, GA 30025",   "days_dormant": 420, "num_jobs": 2, "total_spend": 870,  "job_types": ["AC tune-up", "Filter replacement"],                                    "scenario": "reschedule"},
    {"name": "Irene Cobb",        "email": "irenec@email.com",      "phone": "555-401-0029", "address": "729 Walden Rd, Covington, GA 30014",          "days_dormant": 560, "num_jobs": 3, "total_spend": 1720, "job_types": ["Boiler service", "Furnace repair", "Annual maintenance"],              "scenario": "reschedule"},
    {"name": "Jake Moretti",      "email": "jakem@email.com",       "phone": "555-401-0030", "address": "508 Clearwater Dr, Oxford, GA 30054",         "days_dormant": 380, "num_jobs": 2, "total_spend": 990,  "job_types": ["AC tune-up", "Refrigerant recharge"],                                  "scenario": "reschedule"},
    # Not interested → unsubscribed (5)
    {"name": "Harold Simms",      "email": "harolds@email.com",     "phone": "555-401-0031", "address": "51 Edgewood Ct, Covington, GA 30016",         "days_dormant": 850, "num_jobs": 2, "total_spend": 980,  "job_types": ["Annual maintenance", "Filter replacement"],                            "scenario": "not_interested"},
    {"name": "Ray Fontaine",      "email": "rayf@email.com",        "phone": "555-401-0032", "address": "391 Oakdale Rd, Conyers, GA 30013",           "days_dormant": 740, "num_jobs": 2, "total_spend": 750,  "job_types": ["AC tune-up", "Refrigerant recharge"],                                  "scenario": "not_interested"},
    {"name": "Bev Thornton",      "email": "bevt@email.com",        "phone": "555-401-0033", "address": "184 Clearfield St, Porterdale, GA 30070",     "days_dormant": 910, "num_jobs": 1, "total_spend": 420,  "job_types": ["Filter replacement"],                                                  "scenario": "not_interested"},
    {"name": "Rosa Delgado",      "email": "rosad@email.com",       "phone": "555-401-0034", "address": "317 Hillside Dr, Newborn, GA 30056",          "days_dormant": 680, "num_jobs": 2, "total_spend": 890,  "job_types": ["Annual maintenance", "Duct cleaning"],                                 "scenario": "not_interested"},
    {"name": "Len Kowalski",      "email": "lenk@email.com",        "phone": "555-401-0035", "address": "88 Poplar St, Loganville, GA 30052",          "days_dormant": 800, "num_jobs": 3, "total_spend": 1340, "job_types": ["Furnace repair", "Annual maintenance", "AC tune-up"],                  "scenario": "not_interested"},
    # Straightforward reply → booked (5)
    {"name": "Joyce Osei",        "email": "joyceo@email.com",      "phone": "555-401-0036", "address": "82 Fernwood Ln, Grayson, GA 30017",           "days_dormant": 420, "num_jobs": 3, "total_spend": 1640, "job_types": ["AC tune-up", "Annual maintenance", "Heating inspection"],              "scenario": "straightforward_book"},
    {"name": "Carla Pineda",      "email": "carlap@email.com",      "phone": "555-401-0037", "address": "27 Brookside Ct, Dacula, GA 30019",           "days_dormant": 480, "num_jobs": 4, "total_spend": 2150, "job_types": ["Zone control install", "Annual maintenance", "Filter replacement", "AC tune-up"], "scenario": "straightforward_book"},
    {"name": "Amy Chen",          "email": "amyc@email.com",        "phone": "555-401-0038", "address": "430 Creekside Rd, Hoschton, GA 30548",        "days_dormant": 390, "num_jobs": 2, "total_spend": 980,  "job_types": ["Annual maintenance", "Air quality inspection"],                        "scenario": "straightforward_book"},
    {"name": "Marcus Hollins",    "email": "marcush@email.com",     "phone": "555-401-0039", "address": "55 Heritage Way, Auburn, GA 30011",           "days_dormant": 510, "num_jobs": 3, "total_spend": 1780, "job_types": ["Furnace repair", "AC tune-up", "Annual maintenance"],                  "scenario": "straightforward_book"},
    {"name": "Teresa Kim",        "email": "teresat@email.com",     "phone": "555-401-0040", "address": "198 Lakemont Dr, Winder, GA 30680",           "days_dormant": 440, "num_jobs": 4, "total_spend": 2290, "job_types": ["Heat pump service", "Annual maintenance", "Heating inspection", "Filter replacement"], "scenario": "straightforward_book"},
]


# ── Bulk name / address pools ─────────────────────────────────────────────────

FIRST_NAMES = [
    "Aaron","Abby","Albert","Alex","Alice","Allen","Amanda","Andrew","Angela","Ann",
    "Anthony","Arthur","Ashley","Barbara","Barry","Ben","Beth","Betty","Bill","Bob",
    "Brad","Brandon","Brenda","Brett","Bruce","Bryan","Carol","Catherine","Chad",
    "Charles","Charlotte","Chris","Christina","Christopher","Cynthia","Dale","Dan",
    "Dana","Daniel","Danielle","Darren","David","Dawn","Dean","Deborah","Dennis",
    "Diana","Donald","Douglas","Drew","Dylan","Edward","Elizabeth","Emily","Emma",
    "Eric","Erica","Eugene","Frank","Fred","Gary","George","Gerald","Gloria","Grace",
    "Grant","Gregory","Hannah","Heather","Helen","Henry","Howard","Jacob","Janet",
    "Jason","Jean","Jeff","Jennifer","Jeremy","Jessica","Joe","Joel","John","Jon",
    "Jonathan","Joshua","Joyce","Judy","Julie","Justin","Karen","Katherine","Kathy",
    "Keith","Kelly","Ken","Kim","Kimberly","Larry","Laura","Lauren","Lawrence","Lee",
    "Leslie","Lisa","Lori","Louis","Luke","Margaret","Mark","Martha","Martin","Mary",
    "Matt","Matthew","Melissa","Michael","Michelle","Nancy","Nathan","Neil","Nicholas",
    "Nicole","Noah","Pamela","Patrick","Paul","Peter","Philip","Rachel","Randy",
    "Raymond","Rebecca","Richard","Robert","Robin","Roger","Ronald","Rose","Roy",
    "Russell","Ryan","Samuel","Sara","Scott","Sharon","Sherry","Shirley","Stephanie",
    "Stephen","Steve","Susan","Teresa","Thomas","Timothy","Todd","Tracy","Tyler",
    "Victor","Victoria","Walter","Wendy","William",
]

LAST_NAMES = [
    "Adams","Alexander","Allen","Anderson","Bailey","Baker","Barnes","Bell","Bennett",
    "Black","Boyd","Brooks","Brown","Bryant","Butler","Campbell","Carter","Castillo",
    "Clark","Cole","Coleman","Collins","Cook","Cooper","Cox","Crawford","Cruz","Davis",
    "Dawson","Dixon","Edwards","Elliott","Ellis","Evans","Ferguson","Flores","Ford",
    "Foster","Freeman","Garcia","Gardner","Gibson","Gonzalez","Gordon","Graham","Grant",
    "Gray","Green","Griffin","Hall","Hamilton","Harris","Harrison","Hart","Hayes",
    "Henderson","Henry","Hernandez","Hill","Holmes","Howard","Hudson","Hughes","Hunt",
    "Hunter","Jackson","Jenkins","Johnson","Jones","Jordan","Kelly","Kennedy","King",
    "Knight","Lawrence","Lee","Lewis","Long","Lopez","Marshall","Martin","Martinez",
    "Mason","Matthews","McDonald","Miller","Mills","Mitchell","Moore","Morgan","Morris",
    "Murphy","Murray","Myers","Nelson","Nguyen","Nichols","Olson","Owen","Parker",
    "Patterson","Payne","Perry","Peters","Peterson","Phillips","Pierce","Porter",
    "Powell","Price","Reed","Reid","Reynolds","Richardson","Rivera","Roberts",
    "Robinson","Rodriguez","Rogers","Ross","Russell","Sanchez","Sanders","Scott",
    "Shaw","Simpson","Smith","Spencer","Stone","Sullivan","Taylor","Thomas","Thompson",
    "Torres","Turner","Walker","Wallace","Ward","Warren","Washington","Watson",
    "Weaver","Webb","Wells","West","White","Williams","Wilson","Wood","Wright","Young",
]

GA_STREETS = [
    ("12 Peachtree Way", "Atlanta, GA 30301"),
    ("345 Magnolia Blvd", "Marietta, GA 30060"),
    ("89 Cedar Ridge Dr", "Roswell, GA 30075"),
    ("201 Brookfield Ct", "Alpharetta, GA 30022"),
    ("56 Sycamore Ln", "Kennesaw, GA 30144"),
    ("780 Heritage Park Dr", "Smyrna, GA 30080"),
    ("34 Lakemont Blvd", "Decatur, GA 30030"),
    ("129 Olde Ivy Rd", "Sandy Springs, GA 30328"),
    ("477 Hillcrest Ave", "Dunwoody, GA 30338"),
    ("93 Canton Rd", "Marietta, GA 30066"),
    ("258 Treetop Way", "Woodstock, GA 30188"),
    ("641 Stonehaven Dr", "Cumming, GA 30040"),
    ("18 Winding Creek Ct", "Johns Creek, GA 30097"),
    ("304 Thornberry Ln", "Suwanee, GA 30024"),
    ("87 Forest Hills Dr", "Duluth, GA 30096"),
    ("510 River Shoals Rd", "Lawrenceville, GA 30044"),
    ("23 Ashford Ct", "Norcross, GA 30093"),
    ("163 Mimosa Dr", "Tucker, GA 30084"),
    ("398 Eagle Rock Rd", "Stone Mountain, GA 30083"),
    ("72 Clairmont Rd", "Chamblee, GA 30341"),
    ("445 Holly Springs Rd", "Canton, GA 30114"),
    ("186 Windmill Way", "Acworth, GA 30101"),
    ("311 Kimberly Way", "Buford, GA 30518"),
    ("54 Magnolia Glen", "Sugar Hill, GA 30518"),
    ("279 Woodlands Pkwy", "Grayson, GA 30017"),
    ("822 Alcovy Rd", "Dacula, GA 30019"),
    ("67 Cricket Hollow Rd", "Winder, GA 30680"),
    ("145 Amber Leaf Ct", "Loganville, GA 30052"),
    ("390 Brookstone Blvd", "Conyers, GA 30094"),
    ("217 Pine Grove Cir", "Covington, GA 30014"),
    ("533 Ivy Commons Dr", "Gainesville, GA 30501"),
    ("108 Blue Heron Way", "Flowery Branch, GA 30542"),
    ("77 Blackberry Ct", "Buford, GA 30518"),
    ("422 Whitfield Rd", "Jefferson, GA 30549"),
    ("15 Quail Run", "Monroe, GA 30655"),
    ("668 Tribble Mill Rd", "Lawrenceville, GA 30045"),
    ("291 Graystone Terrace", "Snellville, GA 30039"),
    ("56 Lancaster Gate", "Peachtree City, GA 30269"),
    ("189 Shadowbrook Dr", "McDonough, GA 30252"),
    ("374 Brookwood Dr", "Stockbridge, GA 30281"),
]

# (days_min, days_max, jobs_min, jobs_max, spend_min, spend_max, status, pool_key)
BULK_PROFILES = [
    # High-value prime (dormant 400-800d)
    (400, 650, 3, 6, 1600, 2800, "never_contacted", "mixed"),
    (450, 700, 3, 5, 1800, 3000, "never_contacted", "maintenance"),
    (380, 600, 2, 4, 1400, 2400, "never_contacted", "repair"),
    (500, 780, 3, 6, 2000, 3200, "never_contacted", "mixed"),
    (420, 650, 2, 5, 1500, 2600, "never_contacted", "maintenance"),
    (600, 900, 2, 4, 1200, 2100, "never_contacted", "mixed"),
    (350, 550, 3, 5, 1700, 2800, "never_contacted", "maintenance"),
    (480, 720, 2, 4, 1300, 2200, "never_contacted", "repair"),
    (390, 580, 3, 5, 1600, 2500, "never_contacted", "mixed"),
    (440, 680, 2, 4, 1400, 2300, "never_contacted", "maintenance"),
    (520, 800, 3, 6, 1800, 2900, "never_contacted", "mixed"),
    (360, 520, 2, 4, 1100, 1900, "never_contacted", "repair"),
    (410, 640, 3, 5, 1500, 2500, "never_contacted", "maintenance"),
    (470, 730, 2, 4, 1300, 2100, "never_contacted", "mixed"),
    (540, 820, 3, 5, 1700, 2800, "never_contacted", "maintenance"),
    # Mid-value prime (dormant 365-540d)
    (365, 500, 2, 3,  800, 1400, "never_contacted", "maintenance"),
    (380, 520, 1, 3,  600, 1200, "never_contacted", "repair"),
    (390, 510, 2, 4,  900, 1500, "never_contacted", "mixed"),
    (400, 540, 1, 3,  700, 1300, "never_contacted", "maintenance"),
    (375, 490, 2, 3,  850, 1400, "never_contacted", "repair"),
    (410, 560, 1, 3,  650, 1150, "never_contacted", "maintenance"),
    (365, 480, 2, 4,  950, 1600, "never_contacted", "mixed"),
    (420, 590, 1, 3,  700, 1300, "never_contacted", "repair"),
    (380, 510, 2, 3,  800, 1350, "never_contacted", "maintenance"),
    (395, 530, 1, 3,  600, 1100, "never_contacted", "repair"),
    (415, 560, 2, 4,  900, 1500, "never_contacted", "mixed"),
    (370, 490, 1, 2,  500,  950, "never_contacted", "maintenance"),
    (440, 600, 2, 3,  800, 1400, "never_contacted", "repair"),
    (365, 480, 1, 2,  600, 1000, "never_contacted", "maintenance"),
    (400, 540, 2, 4,  950, 1600, "never_contacted", "mixed"),
    # Warming up (180-365d)
    (200, 340, 1, 3,  700, 1300, "never_contacted", "maintenance"),
    (220, 360, 1, 2,  600, 1100, "never_contacted", "repair"),
    (180, 320, 2, 3,  900, 1500, "never_contacted", "mixed"),
    (210, 350, 1, 2,  800, 1200, "never_contacted", "maintenance"),
    (240, 360, 2, 3,  700, 1300, "never_contacted", "repair"),
    (190, 310, 1, 3,  850, 1400, "never_contacted", "maintenance"),
    (200, 330, 2, 3, 1000, 1600, "never_contacted", "mixed"),
    (215, 345, 1, 2,  600, 1100, "never_contacted", "repair"),
    (230, 355, 2, 3,  800, 1350, "never_contacted", "maintenance"),
    (185, 305, 1, 2,  700, 1200, "never_contacted", "repair"),
    # Recent (10-180d)
    ( 30,  90, 1, 2,  400,  900, "never_contacted", "maintenance"),
    ( 20,  70, 1, 2,  300,  700, "never_contacted", "repair"),
    ( 45, 110, 1, 3,  500, 1000, "never_contacted", "maintenance"),
    ( 10,  50, 1, 1,  200,  500, "never_contacted", "maintenance"),
    ( 60, 150, 1, 2,  600, 1100, "never_contacted", "mixed"),
    ( 30, 100, 2, 3,  700, 1200, "never_contacted", "repair"),
    ( 15,  60, 1, 2,  350,  750, "never_contacted", "maintenance"),
    ( 40, 120, 1, 3,  500,  950, "never_contacted", "mixed"),
    ( 25,  80, 1, 2,  400,  800, "never_contacted", "repair"),
    ( 50, 140, 2, 3,  800, 1300, "never_contacted", "maintenance"),
    # New leads / single install
    ( 80, 200, 1, 1, 1800, 3200, "never_contacted", "install"),
    ( 60, 180, 1, 1, 2200, 3500, "never_contacted", "install"),
    (100, 220, 1, 1, 1500, 2800, "never_contacted", "install"),
    ( 90, 200, 1, 1, 1600, 2900, "never_contacted", "install"),
    (120, 240, 1, 1, 1900, 3100, "never_contacted", "install"),
    # End-of-life (800+d)
    (800, 1100, 2, 4, 1200, 2000, "never_contacted", "mixed"),
    (850, 1200, 1, 3,  900, 1600, "never_contacted", "repair"),
    (900, 1300, 2, 3, 1100, 1800, "never_contacted", "mixed"),
    (750, 1050, 1, 2,  700, 1300, "never_contacted", "maintenance"),
    (820, 1100, 2, 4, 1000, 1700, "never_contacted", "repair"),
    # In outreach sequence
    (400, 600, 2, 4, 1100, 1800, "outreach_sent",   "mixed"),
    (450, 700, 1, 3,  900, 1500, "sequence_step_2", "maintenance"),
    (380, 520, 2, 3, 1200, 1900, "outreach_sent",   "repair"),
    (420, 580, 2, 4, 1400, 2100, "sequence_step_2", "mixed"),
    (390, 540, 1, 3, 1000, 1700, "sequence_step_3", "maintenance"),
    (460, 680, 2, 4, 1300, 2000, "outreach_sent",   "repair"),
    (410, 600, 1, 3, 1100, 1800, "sequence_step_2", "mixed"),
    (375, 500, 2, 3,  950, 1600, "outreach_sent",   "maintenance"),
    (440, 640, 2, 4, 1500, 2200, "sequence_step_3", "mixed"),
    (420, 580, 1, 2,  800, 1400, "outreach_sent",   "repair"),
]


# ── Main reseed ───────────────────────────────────────────────────────────────

def reseed():
    init_db()

    used_names = set()

    with get_db() as db:
        # Wipe in FK order
        db.query(Booking).delete()
        db.query(OutreachLog).delete()
        db.query(Job).delete()
        db.query(Customer).delete()
        db.query(Operator).delete()
        db.flush()

        # Operator
        op = Operator(
            id=1, name="Arjuna Velayudam",
            business_name="Arjuna's HVAC Solutions",
            email="arjunavelayudam@gmail.com",
            phone="555-800-1234", niche="hvac", onboarding_complete=True,
        )
        op.voice_profiles = [
            {"id": "vp_001", "name": "Arjuna", "role": "Owner"},
            {"id": "vp_002", "name": "Sarah",  "role": "Office Manager"},
        ]
        op.tone_profile = {
            "formality": "casual",
            "greeting_style": "Hey [name],",
            "signoff_style": "Best, Arjuna",
            "sentence_length": "short",
            "humor": False, "emoji": False,
            "sample_phrases": [
                "Hope you had a great weekend",
                "Just wanted to check in",
                "Should only take an hour",
                "Let me know what works",
            ],
        }
        db.add(op)
        db.flush()

        count = 0

        # ── Live email customers ──────────────────────────────────────────
        for c in LIVE_CUSTOMERS:
            used_names.add(c["name"])
            last_service = NOW - timedelta(days=c["days_dormant"])
            cust = Customer(
                operator_id=1, name=c["name"], email=c["email"],
                phone=c["phone"], address=c["address"],
                last_service_date=last_service,
                last_service_type=c["job_types"][-1],
                total_jobs=c["num_jobs"], total_spend=c["total_spend"],
                reactivation_status="never_contacted",
            )
            db.add(cust); db.flush()
            _add_jobs(db, cust.id, last_service, c["num_jobs"], c["total_spend"], c["job_types"])
            count += 1

        # ── Scenario customers ────────────────────────────────────────────
        for c in SCENARIO_CUSTOMERS:
            used_names.add(c["name"])
            last_service = NOW - timedelta(days=c["days_dormant"])
            cust = Customer(
                operator_id=1, name=c["name"], email=c["email"],
                phone=c["phone"], address=c["address"],
                last_service_date=last_service,
                last_service_type=c["job_types"][-1],
                total_jobs=c["num_jobs"], total_spend=c["total_spend"],
                reactivation_status="never_contacted",
            )
            db.add(cust); db.flush()
            _add_jobs(db, cust.id, last_service, c["num_jobs"], c["total_spend"], c["job_types"])
            new_status = _add_scenario_logs(db, cust.id, c["name"].split()[0], c["scenario"], c["job_types"][-1])
            cust.reactivation_status = new_status
            count += 1

        # ── Bulk customers ────────────────────────────────────────────────
        target = 200
        bulk_needed = target - count
        addr_pool = GA_STREETS * 10
        random.shuffle(addr_pool)
        addr_idx = 0

        for i in range(bulk_needed):
            p = BULK_PROFILES[i % len(BULK_PROFILES)]
            days_min, days_max, jmin, jmax, smin, smax, status, pool_key = p

            # Unique name
            for _ in range(100):
                first = random.choice(FIRST_NAMES)
                last  = random.choice(LAST_NAMES)
                full  = f"{first} {last}"
                if full not in used_names:
                    used_names.add(full)
                    break

            days_ago   = random.randint(days_min, days_max)
            num_jobs   = random.randint(jmin, jmax)
            total_spend = round(random.uniform(smin, smax), 2)
            last_service = NOW - timedelta(days=days_ago)

            pool = JOB_TYPE_POOLS[pool_key]
            job_types = []
            for j in range(num_jobs):
                job_types.append(pool[j % len(pool)])

            street, city = addr_pool[addr_idx % len(addr_pool)]
            addr_idx += 1
            num = random.randint(100, 999)
            parts = street.split(" ", 1)
            address = f"{num} {parts[1] if len(parts) > 1 else parts[0]}, {city}"

            email = f"{first.lower()}.{last.lower()}{random.randint(10,99)}@email.com"
            phone = f"555-{random.randint(200,899):03d}-{random.randint(1000,9999):04d}"

            cust = Customer(
                operator_id=1, name=full, email=email, phone=phone, address=address,
                last_service_date=last_service,
                last_service_type=job_types[-1],
                total_jobs=num_jobs, total_spend=total_spend,
                reactivation_status=status,
            )
            db.add(cust); db.flush()
            _add_jobs(db, cust.id, last_service, num_jobs, total_spend, job_types)

            if status in ("outreach_sent", "sequence_step_2", "sequence_step_3"):
                _add_sequence_logs(db, cust.id, first, status)

            count += 1

        print(f"✅ Reseeded: 1 operator, {count} customers")
        print(f"   - {len(LIVE_CUSTOMERS)} live email customers (never_contacted)")
        print(f"   - {len(SCENARIO_CUSTOMERS)} scenario customers (rich conversations)")
        print(f"   - {count - len(LIVE_CUSTOMERS) - len(SCENARIO_CUSTOMERS)} bulk customers")


if __name__ == "__main__":
    reseed()

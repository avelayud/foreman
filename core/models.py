"""
core/models.py
SQLAlchemy ORM models for FieldAgent.
These are the core data structures every agent reads from and writes to.
"""

import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Operator(Base):
    """
    The business owner using FieldAgent.
    One operator can have many customers, jobs, and bookings.
    """
    __tablename__ = "operators"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    business_name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)

    # Business type — controls templates, seasonal logic, terminology
    niche = Column(
        Enum("hvac", "plumbing", "electrical", "landscaping", "cleaning", "other", native_enum=False),
        default="hvac"
    )

    # JSON blob storing Claude's analysis of operator's writing style
    # Schema: { formality, greeting_style, signoff, humor, emoji, sample_phrases[] }
    _tone_profile = Column("tone_profile", Text, default="{}")

    # JSON list of named voice profiles for drafting
    # Schema: [{"id": "vp_xxx", "name": "...", "role": "..."}]
    _voice_profiles = Column("voice_profiles", Text, default="[]")

    # Which external services are connected
    # Schema: { gmail: bool, google_cal: bool, sendgrid: bool, twilio: bool }
    _integrations = Column("integrations", Text, default="{}")

    # Onboarding state
    onboarding_complete = Column(Boolean, default=False)

    # Global delivery mode:
    # dry_run    -> approvals/scheduling only, no Gmail sends
    # production -> Gmail send actions are enabled
    outreach_mode = Column(String, default="dry_run")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customers = relationship("Customer", back_populates="operator")
    jobs = relationship("Job", back_populates="operator")
    bookings = relationship("Booking", back_populates="operator")
    outreach_logs = relationship("OutreachLog", back_populates="operator")

    @property
    def tone_profile(self):
        return json.loads(self._tone_profile or "{}")

    @tone_profile.setter
    def tone_profile(self, value):
        self._tone_profile = json.dumps(value)

    @property
    def integrations(self):
        return json.loads(self._integrations or "{}")

    @integrations.setter
    def integrations(self, value):
        self._integrations = json.dumps(value)

    @property
    def voice_profiles(self):
        return json.loads(self._voice_profiles or "[]")

    @voice_profiles.setter
    def voice_profiles(self, value):
        self._voice_profiles = json.dumps(value)

    def __repr__(self):
        return f"<Operator {self.business_name}>"


class Customer(Base):
    """
    A customer of the operator. Core entity for reactivation targeting.
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False)

    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    address = Column(String)

    # Service history summary (denormalized for fast agent queries)
    last_service_date = Column(DateTime)
    last_service_type = Column(String)   # e.g. "AC tune-up", "Pipe repair"
    total_jobs = Column(Integer, default=0)
    total_spend = Column(Float, default=0.0)

    # Reactivation state machine
    reactivation_status = Column(
        Enum(
            "never_contacted",
            "outreach_sent",
            "sequence_step_2",
            "sequence_step_3",
            "sequence_complete",
            "replied",
            "booked",
            "unsubscribed",
            native_enum=False
        ),
        default="never_contacted"
    )

    # Voice profile assigned for drafting (references Operator.voice_profiles[].id)
    assigned_voice_id = Column(String, nullable=True)

    # JSON profile built by CustomerAnalyzer from prior Gmail correspondence
    # Schema: { relationship_history, topics_discussed, customer_tone,
    #           prior_concerns, response_patterns, interest_signals,
    #           context_notes, analyzed_at }
    _customer_profile = Column("customer_profile", Text, nullable=True)

    notes = Column(Text)

    # Phase 5: scoring engine output
    score = Column(Integer, default=0)
    score_breakdown = Column(Text, nullable=True)       # JSON stored as Text
    priority_tier = Column(String, nullable=True)       # "high" | "medium" | "low"
    estimated_job_value = Column(Float, nullable=True)  # avg of historical job revenues
    service_interval_days = Column(Integer, nullable=True)  # avg days between jobs
    predicted_next_service = Column(DateTime, nullable=True)  # last_job + interval

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    operator = relationship("Operator", back_populates="customers")
    jobs = relationship("Job", back_populates="customer")
    bookings = relationship("Booking", back_populates="customer")
    outreach_logs = relationship("OutreachLog", back_populates="customer")

    @property
    def customer_profile(self):
        return json.loads(self._customer_profile or "{}")

    @customer_profile.setter
    def customer_profile(self, value):
        self._customer_profile = json.dumps(value)

    def __repr__(self):
        return f"<Customer {self.name} ({self.reactivation_status})>"


class Job(Base):
    """
    A completed or scheduled service job.
    Historical jobs inform reactivation timing and messaging.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    service_type = Column(String, nullable=False)
    scheduled_at = Column(DateTime)
    completed_at = Column(DateTime)

    status = Column(
        Enum("scheduled", "complete", "cancelled", "no_show", native_enum=False),
        default="scheduled"
    )

    amount = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    operator = relationship("Operator", back_populates="jobs")
    customer = relationship("Customer", back_populates="jobs")

    def __repr__(self):
        return f"<Job {self.service_type} for {self.customer_id} — {self.status}>"


class Booking(Base):
    """
    An upcoming appointment. Can be created by AI outreach, customer self-booking,
    or manual operator entry. All three flow into the unified calendar.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    slot_start = Column(DateTime, nullable=False)
    slot_end = Column(DateTime, nullable=False)

    status = Column(
        Enum("tentative", "confirmed", "cancelled", "complete", native_enum=False),
        default="tentative"
    )

    # How was this booking created?
    source = Column(
        Enum("ai_outreach", "customer_initiated", "manual", "phone", native_enum=False),
        default="manual"
    )

    service_type = Column(String)
    notes = Column(Text)
    estimated_value = Column(Float, nullable=True)  # Operator's estimate of job value ($)
    google_cal_event_id = Column(String)  # Populated if synced to Google Cal
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    operator = relationship("Operator", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")

    def __repr__(self):
        return f"<Booking {self.slot_start} — {self.status}>"


class OutreachLog(Base):
    """
    Every message sent or received by the agent, in either direction.
    This is the agent's memory of what it's done per customer.
    """
    __tablename__ = "outreach_logs"

    id = Column(Integer, primary_key=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    channel = Column(Enum("email", "sms", native_enum=False), nullable=False)
    direction = Column(Enum("outbound", "inbound", native_enum=False), nullable=False)

    content = Column(Text, nullable=False)
    subject = Column(String)   # Email subject if applicable

    sent_at = Column(DateTime, default=datetime.utcnow)
    opened = Column(Boolean, default=False)
    opened_at = Column(DateTime)
    replied = Column(Boolean, default=False)
    replied_at = Column(DateTime)
    reply_content = Column(Text)

    # Which step in the follow-up sequence (0 = initial, 1 = first follow-up, etc.)
    sequence_step = Column(Integer, default=0)

    # Was this a dry run (generated but not sent)?
    dry_run = Column(Boolean, default=False)

    # Delivery workflow status:
    # pending   -> generated draft, awaiting approval
    # approved  -> approved by operator, waiting to be sent
    # scheduled -> approved with a target send time
    # sent      -> successfully delivered through Gmail API
    # failed    -> send attempt failed, needs operator retry
    approval_status = Column(String, default="pending")
    approved_at = Column(DateTime)
    scheduled_send_at = Column(DateTime)
    send_error = Column(Text)

    # Gmail thread ID — populated after sending via Gmail API
    # Enables exact reply detection by thread rather than fuzzy address matching
    gmail_thread_id = Column(String, nullable=True)

    # RFC 2822 Message-ID from the customer's reply — stored at detection time
    # Used as explicit In-Reply-To when sending the next message so the recipient's
    # email client threads the conversation correctly on their side.
    rfc_message_id = Column(String, nullable=True)

    # For booking_confirmed drafts: extracted appointment slot from customer's reply.
    # Stored as naive Eastern time (consistent with Booking.slot_start/slot_end).
    booking_slot_start = Column(DateTime, nullable=True)
    booking_slot_end = Column(DateTime, nullable=True)

    # Phase 5: conversion tracking
    response_classification = Column(String, nullable=True)  # booking_intent | callback_request | price_inquiry | not_interested | unclear
    classified_at = Column(DateTime, nullable=True)
    converted_to_job = Column(Boolean, default=False)
    converted_job_value = Column(Float, nullable=True)
    converted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    operator = relationship("Operator", back_populates="outreach_logs")
    customer = relationship("Customer", back_populates="outreach_logs")

    def __repr__(self):
        return f"<OutreachLog {self.channel} {self.direction} to customer {self.customer_id}>"

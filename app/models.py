# app/models.py
# Phase 2 additions:
#   - Cattle model (individual animal tracking)
#   - BreedingRecord, MilkRecord, VaccinationRecord
#   - TeleVetBooking, PaymentRecord
#   - Updated relationships and indexes
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database import Base
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean,
    Text, ForeignKey, Float, Enum, Date, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
# from app.database import Base
import enum


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class QueryType(str, enum.Enum):
    text  = "text"
    image = "image"
    voice = "voice"

class CattleGender(str, enum.Enum):
    female = "female"
    male   = "male"

class CattleBreed(str, enum.Enum):
    gir          = "Gir"
    sahiwal      = "Sahiwal"
    murrah       = "Murrah Buffalo"
    hf_cross     = "HF Cross"
    jersey_cross = "Jersey Cross"
    other        = "Other"

class BookingStatus(str, enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"

class PaymentStatus(str, enum.Enum):
    pending   = "pending"
    success   = "success"
    failed    = "failed"
    refunded  = "refunded"


# ─── EXISTING PHASE 1 MODELS (unchanged) ─────────────────────────────────────

class Farmer(Base):
    __tablename__ = "farmers"
    phone         = Column(String(20), primary_key=True, index=True)
    name          = Column(String(100), default="")
    village       = Column(String(100), default="")
    district      = Column(String(100), default="")
    state         = Column(String(100), default="")
    # language      = Column(String(20),  default="hindi")
    daily_queries = Column(Integer,     default=0)
    last_reset    = Column(String(10),  default="")
    is_premium    = Column(Boolean,     default=False)
    cattle_count  = Column(Integer,     default=1)
    created_at    = Column(DateTime,    server_default=func.now())

    # Phase 2 fields
    lat           = Column(Float,  nullable=True)
    lon           = Column(Float,  nullable=True)
    preferred_lang = Column(String(20), default="hindi")
    onboarding_done = Column(Boolean, default=False)

    # Relationships
    logs          = relationship("QueryLog",         back_populates="farmer", cascade="all, delete")
    cattle        = relationship("Cattle",           back_populates="farmer", cascade="all, delete")
    bookings      = relationship("TeleVetBooking",   back_populates="farmer")
    payments      = relationship("PaymentRecord",    back_populates="farmer")
    feedback_list = relationship("Feedback",         back_populates="farmer")


class QueryLog(Base):
    __tablename__ = "query_logs"
    id         = Column(Integer,  primary_key=True, autoincrement=True)
    phone      = Column(String(20), ForeignKey("farmers.phone", ondelete="SET NULL"), nullable=True)
    input_type = Column(String(50), default="text")
    symptom    = Column(Text,    default="")
    diagnosis  = Column(Text,    default="")
    hindi_name = Column(Text,    default="")
    confidence = Column(Float,   default=0.0)
    severity   = Column(String(20), default="")
    emergency  = Column(Boolean, default=False)
    cattle_id  = Column(String(36), ForeignKey("cattle.id"), nullable=True)  # Phase 2
    timestamp  = Column(DateTime, server_default=func.now())
    farmer     = relationship("Farmer", back_populates="logs")


class VetProfile(Base):
    __tablename__ = "vets"
    id             = Column(String(36), primary_key=True)
    name           = Column(String(100))
    phone          = Column(String(20), unique=True, index=True)
    district       = Column(String(100))
    state          = Column(String(100))
    specialization = Column(String(100), default="General")
    lat            = Column(Float, nullable=True)
    lon            = Column(Float, nullable=True)
    is_available   = Column(Boolean, default=True)
    rating         = Column(Float,   default=5.0)
    charge_inr     = Column(Integer, default=99)
    total_calls    = Column(Integer, default=0)  # Phase 2
    created_at     = Column(DateTime, server_default=func.now())
    bookings       = relationship("TeleVetBooking", back_populates="vet")


class EmergencyLog(Base):
    __tablename__ = "emergency_logs"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    farmer_phone = Column(String(20))
    disease      = Column(String(200))
    vet_assigned = Column(String(36), ForeignKey("vets.id"), nullable=True)
    status       = Column(String(50), default="triggered")
    timestamp    = Column(DateTime,  server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    phone       = Column(String(20), ForeignKey("farmers.phone", ondelete="SET NULL"), nullable=True)
    query_id    = Column(Integer,   ForeignKey("query_logs.id"), nullable=True)
    rating      = Column(Integer,   default=5)
    was_helpful = Column(Boolean,   default=True)
    comment     = Column(Text,      default="")
    timestamp   = Column(DateTime,  server_default=func.now())
    farmer      = relationship("Farmer", back_populates="feedback_list")


# ─── PHASE 2: CATTLE INDIVIDUAL TRACKING ─────────────────────────────────────

class Cattle(Base):
    """Individual cattle profile — the core of Phase 2."""
    __tablename__ = "cattle"

    id            = Column(String(36),  primary_key=True)   # UUID
    farmer_phone  = Column(String(20),  ForeignKey("farmers.phone", ondelete="CASCADE"))
    tag_number    = Column(String(50),  default="")          # Physical ear tag
    name          = Column(String(100), default="")          # Farmer-given name
    gender        = Column(String(10),  default="female")
    breed         = Column(String(50),  default="Other")
    dob           = Column(Date,        nullable=True)        # Date of birth
    weight_kg     = Column(Float,       default=0.0)
    colour        = Column(String(50),  default="")
    is_active     = Column(Boolean,     default=True)        # False = sold/dead
    purchase_cost = Column(Float,       default=0.0)
    notes         = Column(Text,        default="")
    created_at    = Column(DateTime,    server_default=func.now())

    # Relationships
    farmer              = relationship("Farmer",             back_populates="cattle")
    milk_records        = relationship("MilkRecord",         back_populates="cattle", cascade="all, delete")
    vaccination_records = relationship("VaccinationRecord",  back_populates="cattle", cascade="all, delete")
    breeding_records    = relationship("BreedingRecord",     back_populates="cattle", cascade="all, delete")
    health_logs         = relationship("QueryLog",           foreign_keys=[QueryLog.cattle_id])


class MilkRecord(Base):
    """Daily milk yield tracking per animal."""
    __tablename__ = "milk_records"

    id           = Column(Integer,  primary_key=True, autoincrement=True)
    cattle_id    = Column(String(36), ForeignKey("cattle.id", ondelete="CASCADE"))
    date         = Column(Date,       nullable=False)
    morning_ltrs = Column(Float,      default=0.0)
    evening_ltrs = Column(Float,      default=0.0)
    total_ltrs   = Column(Float,      default=0.0)   # auto-calc or override
    fat_pct      = Column(Float,      default=0.0)
    price_per_ltr = Column(Float,     default=35.0)  # INR
    notes        = Column(Text,       default="")
    recorded_at  = Column(DateTime,   server_default=func.now())

    cattle = relationship("Cattle", back_populates="milk_records")


class VaccinationRecord(Base):
    """Vaccination history and upcoming reminders."""
    __tablename__ = "vaccination_records"

    id           = Column(Integer,  primary_key=True, autoincrement=True)
    cattle_id    = Column(String(36), ForeignKey("cattle.id", ondelete="CASCADE"))
    vaccine_name = Column(String(100))               # FMD, HS, BQ, etc.
    hindi_name   = Column(String(100), default="")
    dose_number  = Column(Integer,  default=1)
    given_date   = Column(Date,     nullable=False)
    next_due     = Column(Date,     nullable=True)
    given_by     = Column(String(100), default="")   # Vet name
    batch_number = Column(String(50),  default="")
    is_free      = Column(Boolean,     default=True) # Govt-free vaccine?
    notes        = Column(Text,        default="")
    reminded     = Column(Boolean,     default=False) # WhatsApp reminder sent?
    created_at   = Column(DateTime,    server_default=func.now())

    cattle = relationship("Cattle", back_populates="vaccination_records")


class BreedingRecord(Base):
    """Breeding / AI insemination tracking + heat detection."""
    __tablename__ = "breeding_records"

    id              = Column(Integer,  primary_key=True, autoincrement=True)
    cattle_id       = Column(String(36), ForeignKey("cattle.id", ondelete="CASCADE"))
    insemination_date = Column(Date,   nullable=False)
    bull_breed      = Column(String(100), default="HF")
    method          = Column(String(50),  default="AI")    # AI | natural
    pregnancy_confirmed = Column(Boolean, nullable=True)   # None=unknown
    expected_calving = Column(Date,    nullable=True)
    actual_calving   = Column(Date,    nullable=True)
    calf_gender     = Column(String(10),  nullable=True)
    outcome_notes   = Column(Text,     default="")
    created_at      = Column(DateTime, server_default=func.now())

    cattle = relationship("Cattle", back_populates="breeding_records")


# ─── PHASE 2: TELE-VET BOOKING ───────────────────────────────────────────────

class TeleVetBooking(Base):
    """Tele-vet call bookings between farmers and vets."""
    __tablename__ = "televet_bookings"

    id           = Column(Integer,  primary_key=True, autoincrement=True)
    farmer_phone = Column(String(20), ForeignKey("farmers.phone", ondelete="SET NULL"), nullable=True)
    vet_id       = Column(String(36), ForeignKey("vets.id"),       nullable=True)
    cattle_id    = Column(String(36), ForeignKey("cattle.id"),     nullable=True)
    scheduled_at = Column(DateTime,  nullable=False)
    duration_min = Column(Integer,   default=15)
    charge_inr   = Column(Integer,   default=99)
    status       = Column(String(20), default="pending")           # BookingStatus
    call_link    = Column(String(500), default="")                 # Video call URL
    symptoms     = Column(Text,       default="")
    vet_notes    = Column(Text,       default="")
    reminder_sent = Column(Boolean,   default=False)
    created_at   = Column(DateTime,   server_default=func.now())

    farmer  = relationship("Farmer",     back_populates="bookings")
    vet     = relationship("VetProfile", back_populates="bookings")


class OtpChallenge(Base):
    """OTP challenge for phone verification."""
    __tablename__ = "otp_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    request_id = Column(String(64), index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False, index=True)
    attempts_left = Column(Integer, default=5)
    last_sent_at = Column(DateTime, nullable=True)


class PaymentRecord(Base):
    """Payment tracking for premium subscriptions and vet calls."""
    __tablename__ = "payments"

    id             = Column(Integer,  primary_key=True, autoincrement=True)
    farmer_phone   = Column(String(20), ForeignKey("farmers.phone", ondelete="SET NULL"), nullable=True)
    amount_inr     = Column(Float,    nullable=False)
    purpose        = Column(String(100), default="premium")  # premium | televet | medicine
    status         = Column(String(20),  default="pending")  # PaymentStatus
    gateway        = Column(String(50),  default="razorpay")
    gateway_txn_id = Column(String(200), default="")
    booking_id     = Column(Integer,   ForeignKey("televet_bookings.id"), nullable=True)
    created_at     = Column(DateTime,  server_default=func.now())

    farmer = relationship("Farmer", back_populates="payments")

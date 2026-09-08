import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    donor = "donor"
    receiver = "receiver"
    volunteer = "volunteer"
    ngo = "ngo"
    admin = "admin"


class FoodType(str, enum.Enum):
    veg = "veg"
    non_veg = "non_veg"


class FoodCategory(str, enum.Enum):
    cooked = "cooked"
    raw = "raw"
    packaged = "packaged"


class DonationStatus(str, enum.Enum):
    available = "available"
    matched = "matched"
    picked_up = "picked_up"
    delivered = "delivered"
    expired = "expired"
    cancelled = "cancelled"


class RequestStatus(str, enum.Enum):
    open = "open"
    matched = "matched"
    fulfilled = "fulfilled"
    cancelled = "cancelled"


class UrgencyLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DeliveryStatus(str, enum.Enum):
    posted = "posted"
    accepted = "accepted"
    picked_up = "picked_up"
    delivered = "delivered"
    failed = "failed"


class ActivityType(str, enum.Enum):
    food_donated = "food_donated"
    volunteer_assigned = "volunteer_assigned"
    delivery_started = "delivery_started"
    delivery_completed = "delivery_completed"
    food_expired = "food_expired"
    ngo_joined = "ngo_joined"
    user_registered = "user_registered"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Volunteer-specific
    is_available = Column(Boolean, default=True)
    vehicle_type = Column(String(50), nullable=True)

    donations = relationship("Donation", back_populates="donor", foreign_keys="Donation.donor_id")
    requests = relationship("FoodRequest", back_populates="requester")
    deliveries_as_volunteer = relationship("Delivery", back_populates="volunteer", foreign_keys="Delivery.volunteer_id")

    __table_args__ = (
        Index("idx_users_location", "location", postgresql_using="gist"),
    )


class Donation(Base):
    __tablename__ = "donations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    donor_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    food_type = Column(SAEnum(FoodType), nullable=False)
    category = Column(SAEnum(FoodCategory), nullable=False)
    description = Column(Text, nullable=True)
    quantity_serves = Column(Integer, nullable=False)
    expiry_time = Column(DateTime(timezone=True), nullable=False)
    pickup_location = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    pickup_address = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    status = Column(SAEnum(DonationStatus), default=DonationStatus.available)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    donor = relationship("User", back_populates="donations", foreign_keys=[donor_id])
    delivery = relationship("Delivery", back_populates="donation", uselist=False)

    __table_args__ = (
        Index("idx_donations_location", "pickup_location", postgresql_using="gist"),
        Index("idx_donations_expiry", "expiry_time"),
        Index("idx_donations_status", "status"),
    )


class FoodRequest(Base):
    __tablename__ = "requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    requester_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    people_count = Column(Integer, nullable=False)
    urgency = Column(SAEnum(UrgencyLevel), default=UrgencyLevel.medium)
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    address = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(SAEnum(RequestStatus), default=RequestStatus.open)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requester = relationship("User", back_populates="requests")
    delivery = relationship("Delivery", back_populates="request", uselist=False)

    __table_args__ = (
        Index("idx_requests_location", "location", postgresql_using="gist"),
        Index("idx_requests_status", "status"),
    )


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    donation_id = Column(UUID(as_uuid=False), ForeignKey("donations.id"), nullable=False)
    request_id = Column(UUID(as_uuid=False), ForeignKey("requests.id"), nullable=False)
    volunteer_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    status = Column(SAEnum(DeliveryStatus), default=DeliveryStatus.posted)
    distance_km = Column(Float, nullable=True)
    estimated_minutes = Column(Float, nullable=True)
    otp = Column(String(6), nullable=True)
    otp_verified = Column(Boolean, default=False)
    volunteer_notified_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    picked_up_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    donation = relationship("Donation", back_populates="delivery")
    request = relationship("FoodRequest", back_populates="delivery")
    volunteer = relationship("User", back_populates="deliveries_as_volunteer", foreign_keys=[volunteer_id])

    __table_args__ = (
        Index("idx_deliveries_status", "status"),
        Index("idx_deliveries_volunteer", "volunteer_id"),
    )


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    delivery_id = Column(UUID(as_uuid=False), ForeignKey("deliveries.id"), nullable=False)
    otp_code = Column(String(6), nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    activity_type = Column(SAEnum(ActivityType), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    donation_id = Column(UUID(as_uuid=False), ForeignKey("donations.id"), nullable=True)
    delivery_id = Column(UUID(as_uuid=False), ForeignKey("deliveries.id"), nullable=True)
    message = Column(Text, nullable=False)
    location_name = Column(String(200), nullable=True)
    extra_data = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_activity_type", "activity_type"),
        Index("idx_activity_created", "created_at"),
    )

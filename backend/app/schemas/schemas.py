from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator
from app.models import UserRole, FoodType, FoodCategory, UrgencyLevel, DeliveryStatus


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str
    role: UserRole
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    vehicle_type: Optional[str] = None  # for volunteers


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: UserRole


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str]
    role: UserRole
    is_verified: bool
    is_active: bool
    address: Optional[str]
    is_available: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Donations ────────────────────────────────────────────────────────────────

class DonationCreate(BaseModel):
    food_type: FoodType
    category: FoodCategory
    description: Optional[str] = None
    quantity_serves: int
    expiry_time: datetime
    pickup_lat: float
    pickup_lng: float
    pickup_address: str

    @field_validator("quantity_serves")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("quantity_serves must be positive")
        return v


class DonationOut(BaseModel):
    id: str
    donor_id: str
    food_type: FoodType
    category: FoodCategory
    description: Optional[str]
    quantity_serves: int
    expiry_time: datetime
    pickup_address: str
    image_url: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Requests ─────────────────────────────────────────────────────────────────

class FoodRequestCreate(BaseModel):
    people_count: int
    urgency: UrgencyLevel = UrgencyLevel.medium
    lat: float
    lng: float
    address: str
    notes: Optional[str] = None


class FoodRequestOut(BaseModel):
    id: str
    requester_id: str
    people_count: int
    urgency: UrgencyLevel
    address: str
    notes: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Matching ─────────────────────────────────────────────────────────────────

class MatchResult(BaseModel):
    donation_id: str
    request_id: str
    volunteer_id: Optional[str]
    distance_km: float
    estimated_minutes: float
    expiry_remaining_minutes: float
    feasible: bool
    delivery_id: Optional[str] = None


# ─── Delivery / Tracking ──────────────────────────────────────────────────────

class DeliveryOut(BaseModel):
    id: str
    donation_id: str
    request_id: str
    volunteer_id: Optional[str]
    status: DeliveryStatus
    distance_km: Optional[float]
    estimated_minutes: Optional[float]
    otp_verified: bool
    accepted_at: Optional[datetime]
    picked_up_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class OTPVerifyRequest(BaseModel):
    delivery_id: str
    otp_code: str


class VolunteerStatusUpdate(BaseModel):
    is_available: bool


# ─── Analytics ────────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    total_meals_delivered: int
    total_donations: int
    total_deliveries: int
    failed_deliveries: int
    expired_donations: int
    avg_delivery_minutes: Optional[float]
    expired_percentage: float
    active_volunteers: int
    active_ngos: int


# ─── Activity Feed ────────────────────────────────────────────────────────────

class ActivityOut(BaseModel):
    id: str
    activity_type: str
    message: str
    location_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

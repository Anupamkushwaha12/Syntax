"""
Feasibility Check Engine — Core USP of FoodBridge.

Rule: A match is ONLY valid if estimated_delivery_time < remaining_time_before_expiry
"""
from datetime import datetime, timezone
from typing import Optional
from app.config import settings


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def estimate_delivery_minutes(distance_km: float, avg_speed_kmh: Optional[float] = None) -> float:
    """Estimate delivery time in minutes with a 20% buffer for traffic/stops."""
    speed = avg_speed_kmh or settings.AVG_SPEED_KMH
    raw_minutes = (distance_km / speed) * 60
    return raw_minutes * 1.2  # 20% buffer


def get_remaining_minutes(expiry_time: datetime) -> float:
    """Minutes remaining before food expires."""
    now = datetime.now(timezone.utc)
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)
    delta = expiry_time - now
    return max(delta.total_seconds() / 60, 0)


def is_feasible(
    donor_lat: float, donor_lng: float,
    receiver_lat: float, receiver_lng: float,
    expiry_time: datetime,
    volunteer_lat: Optional[float] = None,
    volunteer_lng: Optional[float] = None,
) -> dict:
    """
    Core feasibility check.
    Returns dict with feasibility result and all computed metrics.
    """
    # If volunteer location known, route is: volunteer → donor → receiver
    if volunteer_lat is not None and volunteer_lng is not None:
        leg1 = haversine_km(volunteer_lat, volunteer_lng, donor_lat, donor_lng)
        leg2 = haversine_km(donor_lat, donor_lng, receiver_lat, receiver_lng)
        total_distance = leg1 + leg2
    else:
        total_distance = haversine_km(donor_lat, donor_lng, receiver_lat, receiver_lng)

    estimated_minutes = estimate_delivery_minutes(total_distance)
    remaining_minutes = get_remaining_minutes(expiry_time)

    feasible = estimated_minutes < remaining_minutes

    return {
        "feasible": feasible,
        "distance_km": round(total_distance, 2),
        "estimated_minutes": round(estimated_minutes, 1),
        "remaining_minutes": round(remaining_minutes, 1),
    }

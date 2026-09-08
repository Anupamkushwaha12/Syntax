"""
Smart Matching Engine — matches donations to requests using:
- Geospatial proximity (PostGIS ST_DWithin)
- Expiry urgency (nearest expiry first)
- Demand matching (serves >= people_count)
- Feasibility check (delivery time < expiry remaining)
- Volunteer availability
"""
import json
import random
import string
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from app.models import (
    Donation, FoodRequest, Delivery, User, ActivityLog,
    DonationStatus, RequestStatus, DeliveryStatus, ActivityType, UserRole
)
from app.core.feasibility import is_feasible, haversine_km
from app.config import settings


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def find_nearest_volunteer(
    db: AsyncSession,
    donor_lat: float,
    donor_lng: float,
    exclude_ids: list[str] = []
) -> Optional[User]:
    """Find nearest available volunteer using PostGIS."""
    exclude_clause = ""
    if exclude_ids:
        ids = ", ".join(f"'{i}'" for i in exclude_ids)
        exclude_clause = f"AND id NOT IN ({ids})"

    query = text(f"""
        SELECT id, ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat
        FROM users
        WHERE role = 'volunteer'
          AND is_available = true
          AND is_active = true
          AND location IS NOT NULL
          {exclude_clause}
        ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
        LIMIT 1
    """)
    result = await db.execute(query, {"lat": donor_lat, "lng": donor_lng})
    row = result.fetchone()
    if not row:
        return None, None, None

    volunteer = await db.get(User, row.id)
    return volunteer, row.lat, row.lng


async def run_matching_for_donation(
    db: AsyncSession,
    donation: Donation,
    ws_manager=None
) -> Optional[Delivery]:
    """
    Match a single donation to the best open request, assign a volunteer,
    and create a Delivery record.
    """
    # Extract donor coordinates from PostGIS geography
    coord_query = text("""
        SELECT ST_X(pickup_location::geometry) as lng,
               ST_Y(pickup_location::geometry) as lat
        FROM donations WHERE id = :id
    """)
    coord_result = await db.execute(coord_query, {"id": donation.id})
    donor_coords = coord_result.fetchone()
    if not donor_coords:
        return None
    donor_lat, donor_lng = donor_coords.lat, donor_coords.lng

    # Find open requests within radius, ordered by urgency + proximity
    radius_m = settings.MAX_MATCHING_RADIUS_KM * 1000
    requests_query = text("""
        SELECT r.id,
               ST_X(r.location::geometry) as lng,
               ST_Y(r.location::geometry) as lat,
               r.people_count,
               r.urgency
        FROM requests r
        WHERE r.status = 'open'
          AND r.people_count <= :serves
          AND ST_DWithin(
              r.location,
              ST_SetSRID(ST_MakePoint(:donor_lng, :donor_lat), 4326)::geography,
              :radius
          )
        ORDER BY
            CASE r.urgency
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
            END,
            r.location <-> ST_SetSRID(ST_MakePoint(:donor_lng, :donor_lat), 4326)
        LIMIT 10
    """)
    req_result = await db.execute(requests_query, {
        "serves": donation.quantity_serves,
        "donor_lat": donor_lat,
        "donor_lng": donor_lng,
        "radius": radius_m
    })
    candidate_requests = req_result.fetchall()

    if not candidate_requests:
        return None

    # Find nearest volunteer
    volunteer, vol_lat, vol_lng = await find_nearest_volunteer(db, donor_lat, donor_lng)

    # Pick first feasible request
    best_request = None
    best_check = None
    for req in candidate_requests:
        check = is_feasible(
            donor_lat, donor_lng,
            req.lat, req.lng,
            donation.expiry_time,
            vol_lat, vol_lng
        )
        if check["feasible"]:
            best_request = req
            best_check = check
            break

    if not best_request:
        return None

    # Create delivery
    otp = _generate_otp()
    delivery = Delivery(
        donation_id=donation.id,
        request_id=best_request.id,
        volunteer_id=volunteer.id if volunteer else None,
        status=DeliveryStatus.posted,
        distance_km=best_check["distance_km"],
        estimated_minutes=best_check["estimated_minutes"],
        otp=otp,
    )
    db.add(delivery)

    # Update statuses
    donation.status = DonationStatus.matched
    request_obj = await db.get(FoodRequest, best_request.id)
    request_obj.status = RequestStatus.matched

    if volunteer:
        volunteer.is_available = False
        delivery.volunteer_notified_at = datetime.now(timezone.utc)

    # Log activity
    log = ActivityLog(
        activity_type=ActivityType.volunteer_assigned,
        donation_id=donation.id,
        delivery_id=delivery.id,
        message=f"Match found: {donation.quantity_serves} serves → {best_request.people_count} people. ETA {best_check['estimated_minutes']} min.",
        extra_data=json.dumps(best_check)
    )
    db.add(log)
    await db.flush()

    # Broadcast via WebSocket
    if ws_manager:
        await ws_manager.broadcast({
            "event": "match_created",
            "delivery_id": delivery.id,
            "donation_id": donation.id,
            "request_id": best_request.id,
            "volunteer_id": volunteer.id if volunteer else None,
            "estimated_minutes": best_check["estimated_minutes"],
        })

    return delivery

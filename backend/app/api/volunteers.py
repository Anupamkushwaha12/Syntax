"""
Volunteer-specific endpoints:
- View assigned deliveries
- Update live location
- Delivery history + stats
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel
from app.database import get_db
from app.models import User, Delivery, DeliveryStatus, UserRole
from app.schemas import DeliveryOut
from app.core.auth import require_roles
from app.core.websocket import ws_manager

router = APIRouter(prefix="/volunteers", tags=["Volunteers"])


class LocationUpdate(BaseModel):
    lat: float
    lng: float


@router.get("/my-deliveries", response_model=list[DeliveryOut])
async def my_deliveries(
    status: DeliveryStatus = None,
    limit: int = 20,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Delivery)
        .where(Delivery.volunteer_id == current_user.id)
        .order_by(Delivery.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Delivery.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/location")
async def update_location(
    payload: LocationUpdate,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db),
):
    """Update volunteer's live GPS location."""
    current_user.location = WKTElement(f"POINT({payload.lng} {payload.lat})", srid=4326)

    # Find active delivery and broadcast location to that room
    active_result = await db.execute(
        select(Delivery).where(
            Delivery.volunteer_id == current_user.id,
            Delivery.status.in_([DeliveryStatus.accepted, DeliveryStatus.picked_up])
        ).limit(1)
    )
    active_delivery = active_result.scalar_one_or_none()

    if active_delivery:
        await ws_manager.send_to_room(active_delivery.id, {
            "event": "volunteer_location_update",
            "delivery_id": active_delivery.id,
            "lat": payload.lat,
            "lng": payload.lng,
        })

    return {"updated": True}


@router.get("/stats")
async def my_stats(
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'delivered') AS completed,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) AS total,
            AVG(EXTRACT(EPOCH FROM (delivered_at - accepted_at)) / 60)
                FILTER (WHERE status = 'delivered' AND delivered_at IS NOT NULL AND accepted_at IS NOT NULL)
                AS avg_delivery_minutes
        FROM deliveries
        WHERE volunteer_id = :vid
    """), {"vid": current_user.id})
    row = result.fetchone()
    return {
        "completed": row.completed or 0,
        "failed": row.failed or 0,
        "total": row.total or 0,
        "avg_delivery_minutes": round(float(row.avg_delivery_minutes), 1) if row.avg_delivery_minutes else None,
    }

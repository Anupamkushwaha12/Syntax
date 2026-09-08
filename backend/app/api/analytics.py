from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from app.database import get_db
from app.models import Delivery, Donation, User, DeliveryStatus, DonationStatus, UserRole
from app.schemas import AnalyticsSummary
from app.core.auth import get_current_user, require_roles
from app.core.redis_client import cache_set, cache_get

router = APIRouter(prefix="/analytics", tags=["Analytics"])

CACHE_TTL = 120  # 2 minutes


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    cached = await cache_get("analytics:summary")
    if cached:
        return AnalyticsSummary(**cached)

    # Total meals delivered
    meals_result = await db.execute(text("""
        SELECT COALESCE(SUM(d.quantity_serves), 0) as total
        FROM deliveries del
        JOIN donations d ON del.donation_id = d.id
        WHERE del.status = 'delivered'
    """))
    total_meals = meals_result.scalar()

    # Counts
    counts = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            COUNT(*) as total
        FROM deliveries
    """))
    row = counts.fetchone()

    # Expired donations
    expired = await db.execute(text("""
        SELECT COUNT(*) as expired, COUNT(*) FILTER (WHERE status != 'expired') as total
        FROM donations
    """))
    exp_row = expired.fetchone()

    # Avg delivery time (minutes)
    avg_time = await db.execute(text("""
        SELECT AVG(EXTRACT(EPOCH FROM (delivered_at - accepted_at)) / 60)
        FROM deliveries
        WHERE status = 'delivered' AND delivered_at IS NOT NULL AND accepted_at IS NOT NULL
    """))
    avg_minutes = avg_time.scalar()

    # Active volunteers and NGOs
    active_vols = await db.execute(text(
        "SELECT COUNT(*) FROM users WHERE role = 'volunteer' AND is_active = true AND is_available = true"
    ))
    active_ngos = await db.execute(text(
        "SELECT COUNT(*) FROM users WHERE role = 'ngo' AND is_active = true"
    ))

    total_donations = await db.execute(text("SELECT COUNT(*) FROM donations"))
    expired_count = await db.execute(text("SELECT COUNT(*) FROM donations WHERE status = 'expired'"))
    total_don = total_donations.scalar() or 1
    expired_val = int(expired_count.scalar() or 0)

    summary = AnalyticsSummary(
        total_meals_delivered=int(total_meals or 0),
        total_donations=int(total_don),
        total_deliveries=int(row.total or 0),
        failed_deliveries=int(row.failed or 0),
        expired_donations=expired_val,
        avg_delivery_minutes=round(float(avg_minutes), 1) if avg_minutes else None,
        expired_percentage=round((expired_val / total_don) * 100, 1),
        active_volunteers=int(active_vols.scalar() or 0),
        active_ngos=int(active_ngos.scalar() or 0),
    )

    await cache_set("analytics:summary", summary.model_dump(), ttl=CACHE_TTL)
    return summary


@router.get("/activity-feed")
async def get_activity_feed(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(text("""
        SELECT id, activity_type, message, location_name, created_at
        FROM activity_logs
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit})
    rows = result.fetchall()
    return [
        {
            "id": str(r.id),
            "activity_type": r.activity_type,
            "message": r.message,
            "location_name": r.location_name,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]

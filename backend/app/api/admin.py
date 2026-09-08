"""
Admin-only management endpoints:
- List / manage all users
- Verify NGOs and volunteers
- Platform-wide controls
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db
from app.models import User, UserRole, Donation, DonationStatus
from app.schemas import UserOut
from app.core.auth import require_roles

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=list[UserOut])
async def list_all_users(
    role: UserRole = None,
    is_verified: bool = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if role:
        query = query.where(User.role == role)
    if is_verified is not None:
        query = query.where(User.is_verified == is_verified)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/users/{user_id}/verify", response_model=UserOut)
async def verify_user(
    user_id: str,
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_verified = True
    return user


@router.patch("/users/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user.is_active = False
    return user


@router.get("/stats/zones")
async def active_zones(
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Return donation hotspots grouped by address prefix (city-level)."""
    result = await db.execute(text("""
        SELECT
            SPLIT_PART(pickup_address, ',', -1) AS zone,
            COUNT(*) AS total_donations,
            COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
            COUNT(*) FILTER (WHERE status = 'expired') AS expired
        FROM donations
        GROUP BY zone
        ORDER BY total_donations DESC
        LIMIT 20
    """))
    rows = result.fetchall()
    return [
        {
            "zone": r.zone.strip(),
            "total_donations": r.total_donations,
            "delivered": r.delivered,
            "expired": r.expired,
        }
        for r in rows
    ]


@router.post("/donations/{donation_id}/force-expire")
async def force_expire_donation(
    donation_id: str,
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    donation.status = DonationStatus.expired
    return {"status": "expired", "donation_id": donation_id}

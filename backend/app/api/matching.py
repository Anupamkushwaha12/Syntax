from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.models import Donation, DonationStatus, UserRole, User
from app.schemas import MatchResult
from app.core.auth import get_current_user, require_roles
from app.core.matching import run_matching_for_donation
from app.core.websocket import ws_manager

router = APIRouter(prefix="/matching", tags=["Matching Engine"])


@router.post("/trigger/{donation_id}", response_model=MatchResult)
async def trigger_match(
    donation_id: str,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.ngo)),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger matching for a specific donation."""
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    if donation.status != DonationStatus.available:
        raise HTTPException(status_code=400, detail="Donation is not available for matching")

    delivery = await run_matching_for_donation(db, donation, ws_manager)
    if not delivery:
        raise HTTPException(status_code=422, detail="No feasible match found")

    return MatchResult(
        donation_id=donation.id,
        request_id=delivery.request_id,
        volunteer_id=delivery.volunteer_id,
        distance_km=delivery.distance_km,
        estimated_minutes=delivery.estimated_minutes,
        expiry_remaining_minutes=0,  # computed inside matching
        feasible=True,
        delivery_id=delivery.id,
    )


@router.post("/run-all")
async def run_all_matching(
    current_user: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db)
):
    """Run matching for all available donations (admin only)."""
    result = await db.execute(
        text("SELECT id FROM donations WHERE status = 'available' ORDER BY expiry_time ASC LIMIT 50")
    )
    donation_ids = [row.id for row in result.fetchall()]

    matched = 0
    for did in donation_ids:
        donation = await db.get(Donation, did)
        if donation:
            delivery = await run_matching_for_donation(db, donation, ws_manager)
            if delivery:
                matched += 1

    return {"processed": len(donation_ids), "matched": matched}

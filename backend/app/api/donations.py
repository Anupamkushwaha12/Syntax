import os
import aiofiles
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.elements import WKTElement
from app.database import get_db
from app.models import Donation, ActivityLog, ActivityType, DonationStatus, UserRole, FoodType, FoodCategory
from app.schemas import DonationCreate, DonationOut
from app.core.auth import get_current_user, require_roles
from app.core.redis_client import zadd_priority
from app.services.twilio_service import notify_donor_matched
from app.config import settings
from app.models import User

router = APIRouter(prefix="/donations", tags=["Donations"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("", response_model=DonationOut, status_code=201)
async def create_donation(
    food_type: FoodType = Form(...),
    category: FoodCategory = Form(...),
    description: str = Form(None),
    quantity_serves: int = Form(...),
    expiry_time: datetime = Form(...),
    pickup_lat: float = Form(...),
    pickup_lng: float = Form(...),
    pickup_address: str = Form(...),
    image: UploadFile = File(None),
    current_user: User = Depends(require_roles(UserRole.donor, UserRole.ngo, UserRole.admin)),
    db: AsyncSession = Depends(get_db)
):
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)
    if expiry_time <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Expiry time must be in the future")

    image_url = None
    if image:
        if image.content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP images allowed")
        content = await image.read()
        if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Image exceeds {settings.MAX_FILE_SIZE_MB}MB")
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        filename = f"{current_user.id}_{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(settings.UPLOAD_DIR, filename)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        image_url = f"/uploads/{filename}"

    donation = Donation(
        donor_id=current_user.id,
        food_type=food_type,
        category=category,
        description=description,
        quantity_serves=quantity_serves,
        expiry_time=expiry_time,
        pickup_location=WKTElement(f"POINT({pickup_lng} {pickup_lat})", srid=4326),
        pickup_address=pickup_address,
        image_url=image_url,
    )
    db.add(donation)

    log = ActivityLog(
        activity_type=ActivityType.food_donated,
        user_id=current_user.id,
        message=f"{current_user.name} donated {quantity_serves} serves of {category.value} food",
        location_name=pickup_address,
    )
    db.add(log)
    await db.flush()

    # Add to priority queue (score = expiry timestamp for urgency ordering)
    await zadd_priority("matching:priority", expiry_time.timestamp(), donation.id)

    # Notify donor via WhatsApp that donation was received
    if current_user.phone:
        notify_donor_matched(
            current_user.phone,
            f"{category.value} food ({quantity_serves} serves)",
            0  # ETA unknown at creation time
        )

    return donation


@router.post("/{donation_id}/notify")
async def notify_donation(
    donation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send WhatsApp confirmation to donor that donation was received."""
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    donor = await db.get(User, donation.donor_id)
    if donor and donor.phone:
        from app.services.twilio_service import _send_whatsapp
        _send_whatsapp(
            donor.phone,
            f"✅ *FoodBridge* — Your donation of {donation.quantity_serves} serves has been received!\n"
            f"We are finding a volunteer to pick it up. You'll be notified when matched. 💚"
        )
    return {"status": "notified"}
async def list_donations(
    status: DonationStatus = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Donation).order_by(Donation.expiry_time.asc()).limit(limit).offset(offset)
    if status:
        query = query.where(Donation.status == status)
    # Non-admins only see their own or available donations
    if current_user.role not in (UserRole.admin, UserRole.ngo):
        if current_user.role == UserRole.donor:
            query = query.where(Donation.donor_id == current_user.id)
        else:
            query = query.where(Donation.status == DonationStatus.available)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{donation_id}", response_model=DonationOut)
async def get_donation(
    donation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    return donation


@router.delete("/{donation_id}", status_code=204)
async def cancel_donation(
    donation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    donation = await db.get(Donation, donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    if donation.donor_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    if donation.status not in (DonationStatus.available,):
        raise HTTPException(status_code=400, detail="Cannot cancel a matched or delivered donation")
    donation.status = DonationStatus.cancelled

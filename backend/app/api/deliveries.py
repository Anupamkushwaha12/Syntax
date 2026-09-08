import random
import string
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import (
    Delivery, Donation, FoodRequest, User, OTPVerification, ActivityLog,
    DeliveryStatus, DonationStatus, RequestStatus, ActivityType, UserRole
)
from app.schemas import DeliveryOut, OTPVerifyRequest
from app.core.auth import get_current_user, require_roles
from app.core.websocket import ws_manager
from app.core.redis_client import get_redis
from app.services.twilio_service import (
    notify_volunteer_pickup, notify_delivery_confirmed, handle_volunteer_reply
)

router = APIRouter(prefix="/deliveries", tags=["Deliveries & Tracking"])


def _gen_otp():
    return "".join(random.choices(string.digits, k=6))


@router.get("", response_model=list[DeliveryOut])
async def list_deliveries(
    status: DeliveryStatus = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Delivery).order_by(Delivery.created_at.desc()).limit(limit).offset(offset)
    if status:
        query = query.where(Delivery.status == status)
    if current_user.role == UserRole.volunteer:
        query = query.where(Delivery.volunteer_id == current_user.id)
    elif current_user.role not in (UserRole.admin, UserRole.ngo):
        # Donors/receivers see their own deliveries
        query = query.join(Donation, Delivery.donation_id == Donation.id).where(
            Donation.donor_id == current_user.id
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{delivery_id}", response_model=DeliveryOut)
async def get_delivery(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    delivery = await db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return delivery


@router.post("/{delivery_id}/accept", response_model=DeliveryOut)
async def accept_delivery(
    delivery_id: str,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db)
):
    delivery = await db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.volunteer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your delivery")
    if delivery.status != DeliveryStatus.posted:
        raise HTTPException(status_code=400, detail="Delivery already processed")

    delivery.status = DeliveryStatus.accepted
    delivery.accepted_at = datetime.now(timezone.utc)

    # Generate OTP for receiver
    otp_code = _gen_otp()
    otp = OTPVerification(
        delivery_id=delivery.id,
        otp_code=otp_code,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
    )
    db.add(otp)
    delivery.otp = otp_code

    # Notify receiver via WhatsApp
    request_obj = await db.get(FoodRequest, delivery.request_id)
    receiver = await db.get(User, request_obj.requester_id)
    if receiver and receiver.phone:
        notify_delivery_confirmed(receiver.phone, otp_code)

    await ws_manager.send_to_room(delivery_id, {
        "event": "delivery_accepted",
        "delivery_id": delivery_id,
        "volunteer_id": current_user.id,
        "volunteer_name": current_user.name,
    })

    return delivery


@router.post("/{delivery_id}/pickup", response_model=DeliveryOut)
async def mark_picked_up(
    delivery_id: str,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db)
):
    delivery = await db.get(Delivery, delivery_id)
    if not delivery or delivery.volunteer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if delivery.status != DeliveryStatus.accepted:
        raise HTTPException(status_code=400, detail="Must accept before pickup")

    delivery.status = DeliveryStatus.picked_up
    delivery.picked_up_at = datetime.now(timezone.utc)

    donation = await db.get(Donation, delivery.donation_id)
    donation.status = DonationStatus.picked_up

    await ws_manager.send_to_room(delivery_id, {
        "event": "food_picked_up",
        "delivery_id": delivery_id,
        "picked_up_at": delivery.picked_up_at.isoformat(),
    })

    return delivery


@router.post("/{delivery_id}/deliver", response_model=DeliveryOut)
async def mark_delivered(
    delivery_id: str,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db)
):
    delivery = await db.get(Delivery, delivery_id)
    if not delivery or delivery.volunteer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if delivery.status != DeliveryStatus.picked_up:
        raise HTTPException(status_code=400, detail="Must pick up before delivering")
    if not delivery.otp_verified:
        raise HTTPException(status_code=400, detail="OTP must be verified before marking delivered")

    delivery.status = DeliveryStatus.delivered
    delivery.delivered_at = datetime.now(timezone.utc)

    donation = await db.get(Donation, delivery.donation_id)
    donation.status = DonationStatus.delivered

    request_obj = await db.get(FoodRequest, delivery.request_id)
    request_obj.status = RequestStatus.fulfilled

    current_user.is_available = True

    log = ActivityLog(
        activity_type=ActivityType.delivery_completed,
        delivery_id=delivery.id,
        donation_id=delivery.donation_id,
        message=f"Delivery completed by volunteer {current_user.name}",
    )
    db.add(log)

    await ws_manager.broadcast({
        "event": "delivery_completed",
        "delivery_id": delivery_id,
        "volunteer_name": current_user.name,
    })

    return delivery


@router.post("/verify-otp", response_model=dict)
async def verify_otp(
    payload: OTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    delivery = await db.get(Delivery, payload.delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    otp_result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.delivery_id == payload.delivery_id,
            OTPVerification.otp_code == payload.otp_code,
            OTPVerification.is_used == False,
            OTPVerification.expires_at > datetime.now(timezone.utc)
        )
    )
    otp_record = otp_result.scalar_one_or_none()
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    otp_record.is_used = True
    delivery.otp_verified = True

    return {"verified": True, "delivery_id": payload.delivery_id}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Twilio WhatsApp webhook — handles YES/NO replies from volunteers."""
    form = await request.form()
    from_phone = form.get("From", "").replace("whatsapp:", "")
    body = form.get("Body", "")

    action = handle_volunteer_reply(from_phone, body)

    # Find volunteer by phone
    result = await db.execute(select(User).where(User.phone == from_phone))
    volunteer = result.scalar_one_or_none()
    if not volunteer:
        return {"status": "unknown_user"}

    if action == "accepted":
        # Find their pending delivery
        delivery_result = await db.execute(
            select(Delivery).where(
                Delivery.volunteer_id == volunteer.id,
                Delivery.status == DeliveryStatus.posted
            ).order_by(Delivery.volunteer_notified_at.desc()).limit(1)
        )
        delivery = delivery_result.scalar_one_or_none()
        if delivery:
            delivery.status = DeliveryStatus.accepted
            delivery.accepted_at = datetime.now(timezone.utc)
            await ws_manager.send_to_room(delivery.id, {
                "event": "volunteer_accepted_via_whatsapp",
                "delivery_id": delivery.id,
                "volunteer_id": volunteer.id,
            })

    elif action == "declined":
        r = await get_redis()
        delivery_result = await db.execute(
            select(Delivery).where(
                Delivery.volunteer_id == volunteer.id,
                Delivery.status == DeliveryStatus.posted
            ).limit(1)
        )
        delivery = delivery_result.scalar_one_or_none()
        if delivery:
            volunteer.is_available = True
            import json
            await r.lpush("reassignment:queue", json.dumps({
                "delivery_id": delivery.id,
                "donation_id": delivery.donation_id,
                "exclude_volunteer_id": volunteer.id
            }))

    return {"status": "ok"}

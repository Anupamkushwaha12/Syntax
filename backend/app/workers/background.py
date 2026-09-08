"""
Background workers:
1. Expiry scanner — marks expired donations, re-triggers matching
2. Volunteer timeout — reassigns if no response within timeout window
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models import Donation, Delivery, User, ActivityLog, DonationStatus, DeliveryStatus, ActivityType
from app.core.redis_client import get_redis, dequeue_task
from app.config import settings

logger = logging.getLogger(__name__)


async def expiry_scanner():
    """Runs every 60s. Marks expired donations and re-queues unmatched ones."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)

                # Mark expired available donations
                expired_query = text("""
                    UPDATE donations
                    SET status = 'expired', updated_at = NOW()
                    WHERE status = 'available'
                      AND expiry_time <= :now
                    RETURNING id, quantity_serves
                """)
                result = await db.execute(expired_query, {"now": now})
                expired = result.fetchall()

                for row in expired:
                    log = ActivityLog(
                        activity_type=ActivityType.food_expired,
                        donation_id=row.id,
                        message=f"Donation expired: {row.quantity_serves} serves wasted.",
                    )
                    db.add(log)

                # Find near-expiry donations (expiring in < 30 min) still available
                near_expiry_query = text("""
                    SELECT id FROM donations
                    WHERE status = 'available'
                      AND expiry_time BETWEEN :now AND :soon
                """)
                result = await db.execute(near_expiry_query, {
                    "now": now,
                    "soon": now + timedelta(minutes=30)
                })
                near_expiry = result.fetchall()

                r = await get_redis()
                for row in near_expiry:
                    # Push to priority matching queue
                    await r.zadd("matching:priority", {row.id: 0})

                await db.commit()

                if expired:
                    logger.info(f"Expiry scanner: marked {len(expired)} donations as expired")

        except Exception as e:
            logger.error(f"Expiry scanner error: {e}")

        await asyncio.sleep(60)


async def volunteer_timeout_watcher():
    """Runs every 30s. Reassigns deliveries where volunteer didn't respond."""
    timeout_minutes = settings.VOLUNTEER_RESPONSE_TIMEOUT_MINUTES

    while True:
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

                # Find deliveries where volunteer was notified but not accepted
                timed_out_query = text("""
                    SELECT d.id, d.donation_id, d.volunteer_id
                    FROM deliveries d
                    WHERE d.status = 'posted'
                      AND d.volunteer_id IS NOT NULL
                      AND d.volunteer_notified_at <= :cutoff
                      AND d.accepted_at IS NULL
                """)
                result = await db.execute(timed_out_query, {"cutoff": cutoff})
                timed_out = result.fetchall()

                for row in timed_out:
                    # Free the current volunteer
                    old_volunteer = await db.get(User, row.volunteer_id)
                    if old_volunteer:
                        old_volunteer.is_available = True

                    # Push reassignment task to queue
                    r = await get_redis()
                    await r.lpush("reassignment:queue", json.dumps({
                        "delivery_id": row.id,
                        "donation_id": row.donation_id,
                        "exclude_volunteer_id": row.volunteer_id
                    }))

                    logger.info(f"Volunteer timeout: delivery {row.id} queued for reassignment")

                await db.commit()

        except Exception as e:
            logger.error(f"Volunteer timeout watcher error: {e}")

        await asyncio.sleep(30)


async def reassignment_worker():
    """Processes reassignment queue from Redis."""
    from app.core.matching import find_nearest_volunteer
    from app.core.feasibility import is_feasible
    from app.services.twilio_service import notify_volunteer_pickup

    while True:
        try:
            task = await dequeue_task("reassignment:queue")
            if task:
                async with AsyncSessionLocal() as db:
                    delivery = await db.get(Delivery, task["delivery_id"])
                    if not delivery or delivery.status != DeliveryStatus.posted:
                        continue

                    donation = await db.get(Donation, task["donation_id"])
                    if not donation or donation.status not in (DonationStatus.matched, DonationStatus.available):
                        continue

                    # Get donor coords
                    coord_q = text("SELECT ST_X(pickup_location::geometry) as lng, ST_Y(pickup_location::geometry) as lat FROM donations WHERE id = :id")
                    coords = (await db.execute(coord_q, {"id": donation.id})).fetchone()
                    if not coords:
                        continue

                    exclude = [task.get("exclude_volunteer_id")] if task.get("exclude_volunteer_id") else []
                    volunteer, vol_lat, vol_lng = await find_nearest_volunteer(
                        db, coords.lat, coords.lng, exclude_ids=exclude
                    )

                    if volunteer:
                        delivery.volunteer_id = volunteer.id
                        delivery.volunteer_notified_at = datetime.now(timezone.utc)
                        delivery.accepted_at = None
                        volunteer.is_available = False

                        if volunteer.phone:
                            notify_volunteer_pickup(
                                volunteer.phone,
                                donation.pickup_address,
                                f"{donation.category.value} food ({donation.quantity_serves} serves)",
                                delivery.id
                            )

                    await db.commit()
        except Exception as e:
            logger.error(f"Reassignment worker error: {e}")

        await asyncio.sleep(5)


async def start_background_workers():
    asyncio.create_task(expiry_scanner())
    asyncio.create_task(volunteer_timeout_watcher())
    asyncio.create_task(reassignment_worker())
    logger.info("Background workers started")

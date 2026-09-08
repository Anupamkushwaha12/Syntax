"""
Twilio WhatsApp integration for volunteer notifications and delivery confirmations.
"""
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> Client:
    global _client
    if _client is None and settings.TWILIO_ACCOUNT_SID:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


def _send_whatsapp(to_phone: str, message: str) -> bool:
    """Send a WhatsApp message. Returns True on success."""
    client = _get_client()
    if not client:
        logger.warning("Twilio not configured — skipping WhatsApp message")
        return False
    try:
        to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
        client.messages.create(body=message, from_=settings.TWILIO_WHATSAPP_FROM, to=to)
        return True
    except TwilioRestException as e:
        logger.error(f"Twilio error: {e}")
        return False


def notify_volunteer_pickup(phone: str, donor_address: str, food_desc: str, delivery_id: str) -> bool:
    msg = (
        f"🍱 *FoodBridge Pickup Request*\n\n"
        f"Food: {food_desc}\n"
        f"Pickup: {donor_address}\n"
        f"Delivery ID: {delivery_id}\n\n"
        f"Reply *YES* to accept or *NO* to decline.\n"
        f"You have 5 minutes to respond."
    )
    return _send_whatsapp(phone, msg)


def notify_volunteer_reassigned(phone: str) -> bool:
    return _send_whatsapp(phone, "ℹ️ FoodBridge: This delivery has been reassigned. Thank you!")


def notify_expiry_alert(phone: str, food_desc: str, minutes_left: float) -> bool:
    msg = (
        f"⏰ *FoodBridge Expiry Alert*\n\n"
        f"Food '{food_desc}' expires in {int(minutes_left)} minutes!\n"
        f"A volunteer is being assigned urgently."
    )
    return _send_whatsapp(phone, msg)


def notify_delivery_confirmed(phone: str, otp: str) -> bool:
    msg = (
        f"✅ *FoodBridge Delivery Confirmed*\n\n"
        f"Your delivery OTP: *{otp}*\n"
        f"Share this with the volunteer to confirm receipt.\n"
        f"Thank you for using FoodBridge! 🙏"
    )
    return _send_whatsapp(phone, msg)


def notify_donor_matched(phone: str, food_desc: str, eta_minutes: float) -> bool:
    msg = (
        f"🎉 *FoodBridge Match Found!*\n\n"
        f"Your donation '{food_desc}' has been matched!\n"
        f"A volunteer will pick it up in ~{int(eta_minutes)} minutes.\n"
        f"Thank you for your generosity! 💚"
    )
    return _send_whatsapp(phone, msg)


def handle_volunteer_reply(from_phone: str, body: str) -> str:
    """
    Process incoming WhatsApp reply from volunteer.
    Returns the delivery_id from Redis if found (handled by webhook route).
    """
    reply = body.strip().upper()
    if reply == "YES":
        return "accepted"
    elif reply == "NO":
        return "declined"
    return "unknown"

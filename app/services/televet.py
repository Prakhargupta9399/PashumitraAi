# app/services/televet.py
# NEW Phase 2: Tele-vet booking engine.
# Creates bookings, generates video call links (Jitsi Meet — free & open source),
# sends confirmations to farmer and vet via WhatsApp.

import uuid, logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models import TeleVetBooking, VetProfile, Farmer
from app.config import settings

logger = logging.getLogger("pashumitra.televet")


def _jitsi_link(booking_id: int) -> str:
    """Generate a free Jitsi Meet video call link."""
    return f"https://meet.jit.si/PashuMitra-Vet-{booking_id}-{uuid.uuid4().hex[:6]}"


class TeleVetService:

    def find_available_vets(self, db: Session,
                            district: Optional[str] = None,
                            specialization: Optional[str] = None) -> List[Dict]:
        """Find available vets, optionally filtered by district/specialty."""
        q = db.query(VetProfile).filter(VetProfile.is_available == True)
        if district:
            q = q.filter(VetProfile.district.ilike(f"%{district}%"))
        if specialization:
            q = q.filter(VetProfile.specialization.ilike(f"%{specialization}%"))
        vets = q.order_by(VetProfile.rating.desc()).limit(10).all()
        return [
            {
                "id":             v.id,
                "name":           v.name,
                "district":       v.district,
                "specialization": v.specialization,
                "rating":         v.rating,
                "charge_inr":     v.charge_inr,
                "total_calls":    v.total_calls,
            }
            for v in vets
        ]

    def create_booking(self, db: Session, farmer_phone: str, vet_id: str,
                       scheduled_at: datetime, symptoms: str = "",
                       cattle_id: Optional[str] = None) -> Dict:
        """Create a tele-vet booking and return confirmation details."""
        vet = db.query(VetProfile).filter(VetProfile.id == vet_id).first()
        if not vet:
            return {"error": "Vet not found"}
        if vet.is_available is False:
            return {"error": "Vet not available right now"}

        booking = TeleVetBooking(
            farmer_phone = farmer_phone,
            vet_id       = vet_id,
            cattle_id    = cattle_id,
            scheduled_at = scheduled_at,
            charge_inr   = vet.charge_inr,
            status       = "pending",
            symptoms     = symptoms,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # Generate call link after ID is assigned
        booking.call_link = _jitsi_link(booking.id)  # type: ignore
        db.commit()

        logger.info("TeleVet booking #%d created: farmer=%s vet=%s at=%s",
                    booking.id, farmer_phone[-4:], vet.name, scheduled_at)

        return {
            "booking_id":  booking.id,
            "vet_name":    vet.name,
            "vet_phone":   vet.phone,
            "scheduled":   str(scheduled_at),
            "charge":      vet.charge_inr,
            "call_link":   booking.call_link,
            "status":      "pending",
        }

    def confirm_booking(self, db: Session, booking_id: int) -> bool:
        booking = db.query(TeleVetBooking).filter(
            TeleVetBooking.id == booking_id).first()
        if not booking:
            return False
        setattr(booking, "status", "confirmed")
        db.commit()
        return True

    def format_booking_whatsapp(self, booking: Dict, lang: str = "hindi") -> str:
        """Format booking confirmation for WhatsApp."""
        return (
            f"✅ *TeleVet Booking Confirmed!*\n\n"
            f"👨‍⚕️ *डॉक्टर:* {booking['vet_name']}\n"
            f"📅 *समय:* {booking['scheduled']}\n"
            f"💰 *शुल्क:* ₹{booking['charge']}\n\n"
            f"📱 *Video Call Link:*\n{booking['call_link']}\n\n"
            f"⏰ *5 मिनट पहले इस लिंक पर क्लिक करें।*\n"
            f"📞 *डॉक्टर का नंबर:* {booking.get('vet_phone', 'N/A')}\n\n"
            f"_⚠️ तकनीकी समस्या हो तो: support@pashumitra.ai_"
        )

    def get_farmer_bookings(self, db: Session, farmer_phone: str) -> List[Dict]:
        """Get all bookings for a farmer."""
        bookings = (
            db.query(TeleVetBooking)
            .filter(TeleVetBooking.farmer_phone == farmer_phone)
            .order_by(TeleVetBooking.scheduled_at.desc())
            .limit(10)
            .all()
        )
        result = []
        for b in bookings:
            vet = db.query(VetProfile).filter(VetProfile.id == b.vet_id).first()
            result.append({
                "id":          b.id,
                "vet_name":    vet.name if vet else "Unknown",
                "scheduled":   str(b.scheduled_at),
                "status":      b.status,
                "charge":      b.charge_inr,
                "call_link":   b.call_link,
                "symptoms":    b.symptoms,
            })
        return result


televet_service = TeleVetService()

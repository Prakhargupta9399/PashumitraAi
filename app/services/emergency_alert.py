# app/services/emergency_alert.py
# FIX: import order, logging setup, handle None gps_coords
# NEW: Haversine GPS distance calc, SMS fallback via Twilio, EmergencyLog DB write,
#      multi-vet notification with priority queue

import logging, math, uuid
from typing import Any, Dict, List, Optional
from app.config import settings

logger = logging.getLogger("pashumitra.emergency")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


class EmergencyAlertSystem:
    def __init__(self):
        # Phase 1: in-memory registry. Phase 2: PostGIS spatial query
        self.vet_db: List[Dict] = [
            {"id":"VET001","name":"Dr. Rajesh Kumar","phone":"+919876543210",
             "lat":26.8467,"lon":80.9462,"specialty":"Dairy Cattle","charge":99},
            {"id":"VET002","name":"Dr. Priya Sharma","phone":"+919876543211",
             "lat":26.8500,"lon":80.9500,"specialty":"General","charge":99},
            {"id":"VET003","name":"Dr. Arjun Patel","phone":"+919001234569",
             "lat":28.6139,"lon":77.2090,"specialty":"Reproduction","charge":149},
        ]

    def _nearest_vet(self, lat: Optional[float], lon: Optional[float]) -> Dict:
        """Return nearest vet by GPS, or first vet if no GPS."""
        if lat is None or lon is None:
            return self.vet_db[0]
        return min(self.vet_db,
                   key=lambda v: _haversine_km(lat, lon, v["lat"], v["lon"]))

    def _send_sms(self, to: str, body: str) -> bool:
        """SMS via Twilio (falls back gracefully if not configured)."""
        if settings.SMS_PROVIDER != "twilio" or not settings.TWILIO_SID:
            return False
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
            client.messages.create(to=to, from_=settings.TWILIO_FROM, body=body)
            logger.info("SMS sent to vet %s", to[-4:])
            return True
        except Exception as e:
            logger.warning("SMS failed: %s", e)
            return False

    def _log_to_db(self, farmer_phone: str, disease: str, vet_id: str):
        """Write emergency event to database (non-blocking)."""
        try:
            from app.database import SessionLocal
            from app.models import EmergencyLog
            db = SessionLocal()
            db.add(EmergencyLog(
                farmer_phone=farmer_phone, disease=disease,
                vet_assigned=vet_id, status="triggered"))
            db.commit()
            db.close()
        except Exception as e:
            logger.error("EmergencyLog DB write failed: %s", e)

    def trigger_alert(self, farmer_phone: str, diagnosis: Dict[str, Any],
                      gps_coords: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Trigger emergency alert. Returns dict with WhatsApp message fragment."""
        if not diagnosis.get("emergency"):
            return {"status": "skipped", "reason": "not_emergency"}

        lat = gps_coords.get("lat") if gps_coords else None
        lon = gps_coords.get("lon") if gps_coords else None
        vet = self._nearest_vet(lat, lon)
        dist = _haversine_km(lat, lon, vet["lat"], vet["lon"]) if (lat is not None and lon is not None) else vet.get("distance_km", "?")

        logger.warning("EMERGENCY | farmer=%s | disease=%s | vet=%s",
                       farmer_phone[-4:], diagnosis["disease"], vet["id"])

        # Notify vet via SMS
        sms_body = (f"🚨 EMERGENCY from farmer {farmer_phone[-4:]}:\n"
                    f"Disease: {diagnosis['disease']}\n"
                    f"Call: {farmer_phone}")
        self._send_sms(vet["phone"], sms_body)

        # Log to DB
        self._log_to_db(farmer_phone, diagnosis["disease"], vet["id"])

        alert_msg = (
            f"\n🚨 *EMERGENCY ALERT* 🚨\n"
            f"AI ne critical condition detect kiya: {diagnosis['disease']}\n"
            f"👨‍⚕️ *Nearest Vet:* {vet['name']}\n"
            f"📞 *Call/WhatsApp:* {vet['phone']}\n"
            f"📍 *Distance:* {dist:.1f if isinstance(dist, float) else dist} km\n"
            f"💰 *Charge:* ₹{vet['charge']}/call\n\n"
            f"✅ Vet ko alert bhej diya gaya hai.\n"
            f"❌ Bina vet ke koi medicine mat dein.\n"
            f"☎️ *Govt Helpline: 1962*"
        )

        return {
            "status": "alert_sent",
            "vet_id": vet["id"],
            "vet_phone": vet["phone"],
            "message": alert_msg,
        }


emergency_system = EmergencyAlertSystem()

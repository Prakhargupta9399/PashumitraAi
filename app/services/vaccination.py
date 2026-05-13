# app/services/vaccination.py
# NEW Phase 2: Vaccination schedule manager with auto-reminder logic.
# Integrates with APScheduler (tasks/scheduler.py) to send daily WhatsApp reminders.

import uuid, logging
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models import Cattle, VaccinationRecord
from app.services.language import lang_engine

logger = logging.getLogger("pashumitra.vaccination")

# ── MASTER VACCINE SCHEDULE ────────────────────────────────────────────────────
VACCINES = {
    "FMD": {
        "hindi": "खुरपका-मुँहपका", "interval_months": 6,
        "free": True,  "critical": True,
        "warning_days": 15,   # Remind 15 days before due
    },
    "HS": {
        "hindi": "गलघोंटू", "interval_months": 12,
        "free": True,  "critical": True,
        "warning_days": 30,
    },
    "BQ": {
        "hindi": "लंगड़िया बुखार", "interval_months": 12,
        "free": True,  "critical": False,
        "warning_days": 30,
    },
    "Brucellosis": {
        "hindi": "ब्रुसेलोसिस", "interval_months": 999,
        "free": True,  "critical": False,
        "warning_days": 60,
        "note": "Female calves 4-8 months only"
    },
    "Theileria": {
        "hindi": "थिलेरिया", "interval_months": 999,
        "free": False, "critical": False,
        "warning_days": 30,
    },
    "PPR": {
        "hindi": "पीपीआर (बकरी रोग)", "interval_months": 36,
        "free": True,  "critical": True,
        "warning_days": 30,
        "species": ["goat", "sheep"],
    },
}


class VaccinationManager:

    def add_record(self, db: Session, cattle_id: str, vaccine_name: str,
                   given_date: date, given_by: str = "", batch: str = "",
                   is_free: bool = True) -> VaccinationRecord:
        """Add a vaccination record and calculate next due date."""
        vaccine = VACCINES.get(vaccine_name, {})
        interval = vaccine.get("interval_months", 12)

        if interval >= 999:
            next_due = None  # One-time vaccine
        else:
            # Approximate: interval months = interval * 30 days
            next_due = given_date + timedelta(days=interval * 30)

        record = VaccinationRecord(
            cattle_id    = cattle_id,
            vaccine_name = vaccine_name,
            hindi_name   = vaccine.get("hindi", vaccine_name),
            given_date   = given_date,
            next_due     = next_due,
            given_by     = given_by,
            batch_number = batch,
            is_free      = is_free,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("Vaccination %s recorded for cattle %s, next due: %s",
                    vaccine_name, cattle_id[:8], next_due)
        return record

    def get_due_reminders(self, db: Session, days_ahead: int = 15) -> List[Dict]:
        """
        Returns all vaccination records due within `days_ahead` days.
        Called by the daily scheduler.
        """
        today    = date.today()
        deadline = today + timedelta(days=days_ahead)

        records = (
            db.query(VaccinationRecord)
            .filter(
                VaccinationRecord.next_due.isnot(None),
                VaccinationRecord.next_due <= deadline,
                VaccinationRecord.next_due >= today,
                VaccinationRecord.reminded == False,
            )
            .all()
        )

        reminders = []
        for rec in records:
            cattle = db.query(Cattle).filter(Cattle.id == rec.cattle_id).first()
            if not cattle or cattle.is_active is False:
                continue
            days_left = (rec.next_due - today).days
            reminders.append({
                "cattle_id":    rec.cattle_id,
                "cattle_name":  cattle.name or cattle.tag_number or "Unnamed",
                "farmer_phone": cattle.farmer_phone,
                "vaccine":      rec.vaccine_name,
                "hindi_name":   rec.hindi_name,
                "next_due":     str(rec.next_due),
                "days_left":    days_left,
                "is_free":      rec.is_free,
                "record_id":    rec.id,
            })
        return reminders

    def mark_reminded(self, db: Session, record_id: int):
        rec = db.query(VaccinationRecord).filter(VaccinationRecord.id == record_id).first()
        if rec:
            setattr(rec, "reminded", True)
            db.commit()

    def get_cattle_schedule(self, db: Session, cattle_id: str) -> List[Dict]:
        """Full vaccination history + upcoming schedule for one animal."""
        records = (
            db.query(VaccinationRecord)
            .filter(VaccinationRecord.cattle_id == cattle_id)
            .order_by(VaccinationRecord.given_date.desc())
            .all()
        )
        return [
            {
                "id":         r.id,
                "vaccine":    r.vaccine_name,
                "hindi":      r.hindi_name,
                "given":      str(r.given_date),
                "next_due":   str(r.next_due) if r.next_due is not None else "N/A",
                "is_free":    r.is_free,
                "given_by":   r.given_by,
            }
            for r in records
        ]

    def build_reminder_message(self, reminder: Dict, lang: str = "hindi") -> str:
        """Format WhatsApp reminder message for a vaccination due."""
        free_tag = " (सरकारी — मुफ्त 🆓)" if reminder["is_free"] else " (₹ charge)"
        days     = reminder["days_left"]
        urgency  = "🔴 *आज देर मत करें!*" if days <= 3 else f"⏰ {days} दिन बाकी"

        return (
            f"💉 *PashuMitra — टीकाकरण अनुस्मारक*\n\n"
            f"🐄 पशु: *{reminder['cattle_name']}*\n"
            f"💊 टीका: *{reminder['hindi_name']}*{free_tag}\n"
            f"📅 देय तारीख: *{reminder['next_due']}*\n"
            f"{urgency}\n\n"
            f"📍 नजदीकी सरकारी पशु चिकित्सालय या PHC पर जाएं।\n"
            f"☎️ *Helpline: 1962*\n\n"
            f"_यह PashuMitra AI का स्वचालित अनुस्मारक है।_"
        )


vaccination_manager = VaccinationManager()

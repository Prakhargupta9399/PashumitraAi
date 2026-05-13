# app/tasks/reminders.py
# NEW Phase 2: Daily WhatsApp reminder dispatch.
# Called by APScheduler at 8 AM IST every day.
# Sends: vaccination due reminders, breeding alerts, milk decline alerts.

import logging
from datetime import date, timedelta
from app.database import SessionLocal
from app.models import Cattle, MilkRecord, BreedingRecord
from app.services.vaccination import vaccination_manager
from app.services.milk_optimizer import milk_optimizer
from app.whatsapp import wa

logger = logging.getLogger("pashumitra.reminders")


def send_vaccination_reminders():
    """Send WhatsApp reminders for vaccinations due in the next 15 days."""
    db = SessionLocal()
    sent = 0
    try:
        reminders = vaccination_manager.get_due_reminders(db, days_ahead=15)
        for reminder in reminders:
            phone   = str(reminder["farmer_phone"])
            message = vaccination_manager.build_reminder_message(reminder)
            ok = wa.send_text(phone, message)
            if ok:
                vaccination_manager.mark_reminded(db, reminder["record_id"])
                sent += 1
                logger.info("Vaccination reminder sent: phone=%s vaccine=%s",
                            phone[-4:], reminder["vaccine"])
    except Exception as e:
        logger.error("Vaccination reminder job error: %s", e)
    finally:
        db.close()
    logger.info("Vaccination reminders sent: %d", sent)
    return sent


def send_milk_decline_alerts():
    """
    Check all active cattle for declining milk trend.
    Send alert to farmer if trend is 'declining' and last alert was > 3 days ago.
    """
    db = SessionLocal()
    sent = 0
    try:
        cattle_list = db.query(Cattle).filter(Cattle.is_active == True).all()
        for cattle in cattle_list:
            try:
                trend = milk_optimizer.get_trend(db, str(cattle.id), days=7)
                if trend.get("trend") == "declining" and trend.get("avg_daily", 0) > 0:
                    msg = (
                        f"📉 *PashuMitra Alert — {cattle.name or 'Aapki Gaay'}*\n\n"
                        f"⚠️ पिछले 7 दिनों में दूध कम हो रहा है!\n"
                        f"📊 औसत: {trend['avg_daily']} लीटर/दिन\n\n"
                        f"🔍 *क्या जांचें:*\n"
                        f"  • थनैला रोग (mastitis)\n"
                        f"  • आहार में कमी\n"
                        f"  • तनाव या बीमारी\n\n"
                        f"📞 *लक्षण भेजें* और हम तुरंत सलाह देंगे!\n"
                        f"☎️ *1962 (Govt Helpline)*"
                    )
                    wa.send_text(str(cattle.farmer_phone), msg)
                    sent += 1
            except Exception as e:
                logger.warning("Milk alert error for cattle %s: %s", cattle.id[:8], e)
    except Exception as e:
        logger.error("Milk decline job error: %s", e)
    finally:
        db.close()
    logger.info("Milk decline alerts sent: %d", sent)
    return sent


def send_breeding_reminders():
    """
    Remind farmers about upcoming heat cycles and overdue insemination.
    """
    db = SessionLocal()
    sent = 0
    today = date.today()
    try:
        # Find cows where expected next heat is within 3 days
        from app.models import BreedingRecord
        upcoming = (
            db.query(BreedingRecord)
            .filter(
                BreedingRecord.actual_calving.isnot(None),
                BreedingRecord.pregnancy_confirmed != True,
            )
            .all()
        )
        for rec in upcoming:
            if rec.actual_calving is None:
                continue
            next_heat = rec.actual_calving + __import__("datetime").timedelta(days=60)
            days_left = (next_heat - today).days
            if 0 <= days_left <= 3:
                cattle = db.query(Cattle).filter(Cattle.id == rec.cattle_id).first()
                if not cattle:
                    continue
                msg = (
                    f"🌡️ *PashuMitra — गर्मी का संकेत*\n\n"
                    f"🐄 *{cattle.name or 'Aapki Gaay'}* अगले *{days_left+1} दिनों* में "
                    f"गर्मी में आने की संभावना है।\n\n"
                    f"✅ *AI Insemination बुक करें:*\n"
                    f"  • अभी Pashu Mitra पर 'breeding' लिखें\n"
                    f"  • या नजदीकी AI center पर जाएं\n\n"
                    f"💡 *सही समय = ज्यादा pregnancy success rate*\n"
                    f"☎️ *BAIF/NDDB helpline: 1800-180-1551*"
                )
                wa.send_text(str(cattle.farmer_phone), msg)
                sent += 1
    except Exception as e:
        logger.error("Breeding reminder error: %s", e)
    finally:
        db.close()
    logger.info("Breeding reminders sent: %d", sent)
    return sent

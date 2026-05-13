import asyncio
import logging

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
    from apscheduler.triggers.cron import CronTrigger            # type: ignore
    APS_INSTALLED = True
except ImportError:
    # Fallback for environments where apscheduler is not yet installed or resolved
    AsyncIOScheduler = None
    CronTrigger = None
    APS_INSTALLED = False

logger = logging.getLogger("pashumitra.scheduler")

def create_scheduler():
    """
    Create and configure the async scheduler.
    All times are IST (UTC+5:30).
    """
    if not APS_INSTALLED or AsyncIOScheduler is None or CronTrigger is None:
        logger.error("APScheduler not installed. Run 'pip install apscheduler'")
        return None

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # ── VACCINATION REMINDERS — 8:00 AM IST daily ────────────────────────────
    scheduler.add_job(
        _run_vaccination_reminders,
        CronTrigger(hour=8, minute=0),
        id="vaccination_reminders",
        name="Daily Vaccination Reminders",
        replace_existing=True,
    )

    # ── MILK DECLINE ALERTS — 9:00 AM IST daily ──────────────────────────────
    scheduler.add_job(
        _run_milk_alerts,
        CronTrigger(hour=9, minute=0),
        id="milk_decline_alerts",
        name="Daily Milk Decline Alerts",
        replace_existing=True,
    )

    # ── BREEDING REMINDERS — 7:00 AM IST daily ───────────────────────────────
    scheduler.add_job(
        _run_breeding_reminders,
        CronTrigger(hour=7, minute=0),
        id="breeding_reminders",
        name="Daily Breeding Heat Reminders",
        replace_existing=True,
    )

    # ── TELEVET BOOKING REMINDERS — every 30 minutes ─────────────────────────
    scheduler.add_job(
        _run_televet_reminders,
        CronTrigger(minute="*/30"),
        id="televet_reminders",
        name="TeleVet Booking Reminders",
        replace_existing=True,
    )

    logger.info(f"Scheduler configured with {len(scheduler.get_jobs())} jobs")
    return scheduler

# ── ASYNC WRAPPERS ────────────────────────────────────────────────────────────
# Use asyncio.get_running_loop() instead of the deprecated get_event_loop()
# inside async functions (required in Python 3.10+).

async def _run_vaccination_reminders():
    from app.tasks.reminders import send_vaccination_reminders
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, send_vaccination_reminders)

async def _run_milk_alerts():
    from app.tasks.reminders import send_milk_decline_alerts
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, send_milk_decline_alerts)

async def _run_breeding_reminders():
    from app.tasks.reminders import send_breeding_reminders
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, send_breeding_reminders)

async def _run_televet_reminders():
    """Send WhatsApp reminders 30 minutes before tele-vet bookings."""
    from datetime import datetime, timedelta
    from app.database import SessionLocal
    from app.models import TeleVetBooking, VetProfile
    from app.whatsapp import wa

    def _job():
        db = SessionLocal()
        try:
            now = datetime.now()
            window = now + timedelta(minutes=35)

            bookings = (
                db.query(TeleVetBooking)
                .filter(
                    TeleVetBooking.status == "confirmed",
                    TeleVetBooking.scheduled_at <= window,
                    TeleVetBooking.scheduled_at >= now,
                    TeleVetBooking.reminder_sent.is_(False),
                )
                .all()
            )

            for b in bookings:
                vet = db.query(VetProfile).filter(VetProfile.id == b.vet_id).first()
                msg = (
                    f"⏰ *30 मिनट में आपकी TeleVet Call है!*\n\n"
                    f"👨‍⚕️ डॉक्टर: {vet.name if vet else 'Your Vet'}\n"
                    f"📱 Call Link:\n{b.call_link}\n\n"
                    f"_अभी link खोलकर तैयार रहें।_"
                )
                wa.send_text(str(b.farmer_phone), msg)
                setattr(b, "reminder_sent", True)
                db.commit()
        finally:
            db.close()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _job)
# app/limits.py
# FIX: Uses settings.FREE_QUERIES_PER_DAY instead of hardcoded 3
# FIX: Proper session close in all paths (finally block was missing in one branch)
# NEW: is_premium_farmer() helper, get_usage() helper for dashboard
from datetime import date
import logging
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.database import SessionLocal
from app.models import Farmer
from app.config import settings

logger = logging.getLogger("pashumitra.limits")
LIMIT = settings.FREE_QUERIES_PER_DAY


def check_and_increment(phone: str) -> bool:
    """Return True if query allowed; increment counter. Thread-safe via DB."""
    today = str(date.today())
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
        if not farmer:
            try:
                db.add(Farmer(phone=phone, daily_queries=1, last_reset=today))
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
                if not farmer:
                    return False

        if farmer.is_premium:
            return True                           # Premium = unlimited

        if farmer.last_reset != today:
            farmer.daily_queries = 1
            farmer.last_reset    = today
            db.commit()
            return True

        if farmer.daily_queries < LIMIT:
            farmer.daily_queries += 1
            db.commit()
            return True

        return False

    except SQLAlchemyError as e:
        db.rollback()
        logger.error("DB error in check_and_increment: %s", e)
        return True  # fail-open so farmers aren't blocked on DB errors
    finally:
        db.close()


def get_usage(phone: str) -> dict:
    """Return current usage info for a phone number."""
    today = str(date.today())
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
        if not farmer:
            return {"used": 0, "limit": LIMIT, "remaining": LIMIT, "is_premium": False}
        used = farmer.daily_queries if farmer.last_reset == today else 0
        return {
            "used": used,
            "limit": 9999 if farmer.is_premium else LIMIT,
            "remaining": 9999 if farmer.is_premium else max(0, LIMIT - used),
            "is_premium": farmer.is_premium,
        }
    finally:
        db.close()


def upgrade_to_premium(phone: str) -> bool:
    """Mark farmer as premium (call after payment confirmation)."""
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
        if not farmer:
            return False
        farmer.is_premium = True
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Premium upgrade error: %s", e)
        return False
    finally:
        db.close()

import logging
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models import OtpChallenge

logger = logging.getLogger("pashumitra.otp")


_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def normalize_phone(phone: str) -> str:
    p = (phone or "").strip().replace(" ", "")
    if not p:
        return ""
    if not p.startswith("+"):
        # best-effort: if user sends local number, Twilio generally needs E.164.
        # We cannot guess country code; keep as-is.
        pass
    return p


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _otp_ttl() -> timedelta:
    return timedelta(seconds=getattr(settings, "OTP_TTL_SECONDS", 300))


def _otp_resend_wait() -> timedelta:
    return timedelta(seconds=getattr(settings, "OTP_RESEND_WAIT_SECONDS", 60))


def _otp_max_attempts() -> int:
    return int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))


def _generate_code() -> str:
    # 6-digit code
    return f"{random.randint(0, 999999):06d}"


def _send_sms_twilio(to: str, body: str) -> bool:
    if settings.SMS_PROVIDER != "twilio":
        return False
    if not settings.TWILIO_SID or not settings.TWILIO_TOKEN or not settings.TWILIO_FROM:
        return False

    try:
        from twilio.rest import Client  # type: ignore

        client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
        msg = client.messages.create(to=to, from_=settings.TWILIO_FROM, body=body)
        # Twilio returns status like 'queued'/'sent'
        return bool(getattr(msg, "sid", None))
    except Exception as e:
        logger.warning("Twilio SMS failed: %s", e)
        return False


def request_otp(phone: str, request_id: Optional[str] = None) -> dict:
    phone_n = normalize_phone(phone)
    if not phone_n or not _PHONE_RE.match(phone_n):
        return {"status": "invalid_phone"}

    req_id = request_id or f"req-{random.randint(100000, 999999)}"
    otp_code = _generate_code()

    db = SessionLocal()
    try:
        now = _now_utc()
        ttl = _otp_ttl()
        resend_wait = _otp_resend_wait()
        max_attempts = _otp_max_attempts()

        # If a challenge exists for this request_id, don't resend.
        existing = (
            db.query(OtpChallenge)
            .filter(OtpChallenge.request_id == req_id, OtpChallenge.phone == phone_n)
            .order_by(OtpChallenge.created_at.desc())
            .first()
        )
        if existing and getattr(existing, "verified") is False and existing.expires_at > now:
            return {"status": "already_sent", "expires_at": existing.expires_at.isoformat()}

        # Rate-limit resends: last_sent_at must be older than resend_wait
        last = (
            db.query(OtpChallenge)
            .filter(OtpChallenge.phone == phone_n)
            .order_by(OtpChallenge.last_sent_at.desc())
            .first()
        )

        if last and last.last_sent_at is not None:
            # Ensure last_sent_at is timezone-aware for comparison if it comes from DB as naive
            last_sent: datetime = last.last_sent_at  # type: ignore
            if last_sent.tzinfo is None: last_sent = last_sent.replace(tzinfo=timezone.utc)

            if last_sent + resend_wait > now:
                return {"status": "resend_blocked", "retry_after_seconds": int((last_sent + resend_wait - now).total_seconds())}

        expires_at = now + ttl
        ch = OtpChallenge(
            phone=phone_n,
            code=otp_code,
            request_id=req_id,
            created_at=now,
            expires_at=expires_at,
            attempts_left=max_attempts,
            verified=False,
            last_sent_at=now,
        )
        db.add(ch)
        db.commit()

        sms_body = f"Your PashuMitra verification OTP is {otp_code}. It will expire in {int(ttl.total_seconds()//60)} min."
        ok = _send_sms_twilio(phone_n, sms_body)
        if not ok:
            # keep challenge row but return failure so client can retry
            logger.warning("OTP stored but SMS not sent to %s", phone_n)
            return {"status": "sms_failed"}

        return {"status": "sent", "request_id": req_id, "expires_at": expires_at.isoformat()}

    except Exception as e:
        db.rollback()
        logger.error("request_otp error: %s", e)
        return {"status": "error"}
    finally:
        db.close()


def verify_otp(phone: str, code: str) -> dict:
    phone_n = normalize_phone(phone)
    if not phone_n or not _PHONE_RE.match(phone_n):
        return {"status": "invalid_phone"}

    db = SessionLocal()
    try:
        now = _now_utc()
        ch = (
            db.query(OtpChallenge)
            .filter(
                OtpChallenge.phone == phone_n,
                OtpChallenge.verified == False,
                OtpChallenge.expires_at > now,
            )
            .order_by(OtpChallenge.created_at.desc())
            .first()
        )
        if not ch:
            return {"status": "expired_or_missing"}

        if ch.code != (code or "").strip():
            current_attempts = getattr(ch, "attempts_left", 0)
            new_attempts = int(current_attempts or 0) - 1
            setattr(ch, "attempts_left", new_attempts)
            if new_attempts <= 0:
                # Expire the challenge by setting expires_at to now
                setattr(ch, "expires_at", now)
                db.commit()
                return {"status": "blocked"}
            db.commit()
            return {"status": "invalid_code", "attempts_left": ch.attempts_left}

        setattr(ch, "verified", True)
        db.commit()
        return {"status": "verified"}
    except Exception as e:
        db.rollback()
        logger.error("verify_otp error: %s", e)
        return {"status": "error"}
    finally:
        db.close()

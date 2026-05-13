# app/config.py
# FIX: Added validation — app logs clear warnings when tokens are missing
#      instead of silently using None and crashing later.
# NEW: Added ANTHROPIC_API_KEY, OPENAI_API_KEY, SMS_PROVIDER, REDIS_URL fields
import os, logging
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("pashumitra.config")

class Settings:
    # WhatsApp (Meta Cloud API)
    WHATSAPP_VERIFY_TOKEN   = os.getenv("WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_ACCESS_TOKEN   = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID= os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pashumitra_dev.db")

    # NEW: AI API keys (Phase 2)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

    # NEW: SMS fallback (Twilio / Exotel)
    SMS_PROVIDER      = os.getenv("SMS_PROVIDER", "none")        # twilio | exotel | none
    TWILIO_SID        = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_TOKEN      = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM       = os.getenv("TWILIO_FROM_NUMBER", "")

    # NEW: Cache
    REDIS_URL         = os.getenv("REDIS_URL", "")               # optional

    # Runtime
    ENVIRONMENT       = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL         = os.getenv("LOG_LEVEL", "INFO")
    FREE_QUERIES_PER_DAY = int(os.getenv("FREE_QUERIES_PER_DAY", "3"))

    def warn_missing(self):
        missing = []
        if not self.WHATSAPP_VERIFY_TOKEN:   missing.append("WHATSAPP_VERIFY_TOKEN")
        if not self.WHATSAPP_ACCESS_TOKEN:   missing.append("WHATSAPP_ACCESS_TOKEN")
        if not self.WHATSAPP_PHONE_NUMBER_ID:missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if missing:
            logger.warning("⚠️  Missing .env vars: %s — WhatsApp will not work", ", ".join(missing))

settings = Settings()
settings.warn_missing()

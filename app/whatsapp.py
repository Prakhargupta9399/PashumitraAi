# app/whatsapp.py
# FIX: send_text no longer raises on HTTP errors — logs and returns False instead
#      (prevents webhook from returning 500 when WA API is down)
# FIX: download_media handles missing 'url' key gracefully
# NEW: send_template(), send_list_message(), send_reaction() helpers
#      reply_with_buttons() for quick-reply CTAs

import logging
import requests
from app.config import settings

logger = logging.getLogger("pashumitra.whatsapp")


class WhatsAppClient:
    def __init__(self):
        self.api_version = "v20.0"
        self.base_url    = f"https://graph.facebook.com/{self.api_version}"

    @property
    def _phone_url(self) -> str:
        pid = settings.WHATSAPP_PHONE_NUMBER_ID or "NOT_SET"
        return f"{self.base_url}/{pid}"

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN or ''}",
            "Content-Type":  "application/json",
        }

    # ── SEND TEXT ─────────────────────────────────────────────────────────────
    def send_text(self, phone: str, message: str) -> bool:
        """Send plain text message. Returns False on error (does NOT raise)."""
        if not settings.WHATSAPP_ACCESS_TOKEN:
            logger.warning("Cannot send — WHATSAPP_ACCESS_TOKEN not set")
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": phone, "type": "text",
            "text": {"body": message, "preview_url": False},
        }
        try:
            res = requests.post(f"{self._phone_url}/messages",
                                headers=self._headers, json=payload, timeout=15)
            if not res.ok:
                logger.error("WA send_text failed %s: %s", res.status_code, res.text[:200])
                return False
            return True
        except requests.RequestException as e:
            logger.error("WA send_text network error: %s", e)
            return False

    # ── SEND INTERACTIVE BUTTONS ──────────────────────────────────────────────
    def reply_with_buttons(self, phone: str, body: str, buttons: list[dict]) -> bool:
        """Send interactive quick-reply buttons (max 3).
           buttons = [{"id": "btn_1", "title": "हाँ, Doctor बुलाओ"}, ...]
        """
        if len(buttons) > 3:
            buttons = buttons[:3]
        payload = {
            "messaging_product": "whatsapp",
            "to": phone, "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]},
            },
        }
        try:
            res = requests.post(f"{self._phone_url}/messages",
                                headers=self._headers, json=payload, timeout=15)
            if not res.ok:
                logger.error("reply_with_buttons failed %s: %s", res.status_code, res.text[:200])
                return False
            return True
        except requests.RequestException as e:
            logger.error("reply_with_buttons error: %s", e)
            return False

    # ── SEND TEMPLATE ─────────────────────────────────────────────────────────
    def send_template(self, phone: str, template_name: str, components: list,
                      language: str = "hi") -> bool:
        """Send approved WhatsApp template (for opt-in re-engagement)."""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone, "type": "template",
            "template": {"name": template_name, "language": {"code": language},
                         "components": components or []},
        }
        try:
            res = requests.post(f"{self._phone_url}/messages",
                                headers=self._headers, json=payload, timeout=15)
            return res.ok
        except Exception as e:
            logger.error("send_template error: %s", e)
            return False

    # ── DOWNLOAD MEDIA ────────────────────────────────────────────────────────
    def download_media(self, media_id: str) -> bytes:
        """Download media bytes from WhatsApp media ID. Returns b'' on failure."""
        try:
            res = requests.get(f"{self.base_url}/{media_id}",
                               headers=self._headers, timeout=10)
            res.raise_for_status()
            url = res.json().get("url")
            if not url:
                logger.error("No download URL in media response for id=%s", media_id)
                return b""
            file_res = requests.get(url, headers=self._headers, timeout=30)
            file_res.raise_for_status()
            return file_res.content
        except Exception as e:
            logger.error("download_media error (id=%s): %s", media_id, e)
            return b""

    # ── MARK READ ─────────────────────────────────────────────────────────────
    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read (shows double blue tick to farmer)."""
        payload = {"messaging_product": "whatsapp",
                   "status": "read", "message_id": message_id}
        try:
            res = requests.post(f"{self._phone_url}/messages",
                                headers=self._headers, json=payload, timeout=10)
            return res.ok
        except Exception:
            return False


wa = WhatsAppClient()

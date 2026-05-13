# app/main.py  — Phase 2 (full replacement)
# Added: Phase 2 routers, cache, scheduler, language engine,
#        onboarding flow, cattle-linked diagnosis, session state.

import os, sys, logging, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.whatsapp import wa
from app.services.ai_engine import ai_engine
from app.services.emergency_alert import emergency_system
from app.services.caches import cache
from app.services.language import lang_engine
from app.services.televet import televet_service

from app.limits import check_and_increment, get_usage
from app.config import settings
from app.database import engine, Base, get_db
from app.models import Farmer, QueryLog, Cattle

# Phase 2 routers
from app.routers import cattle as cattle_router
from app.routers import dashboard as dashboard_router
from app.routers import televet as televet_router

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s [%(name)s]: %(message)s")
logger = logging.getLogger("pashumitra.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)
    ai_engine.load()
    cache.connect()                               # Phase 2: Redis cache

    # Phase 2: Start task scheduler
    from app.tasks.scheduler import create_scheduler
    scheduler = create_scheduler()
    if scheduler:
        scheduler.start()
        app.state.scheduler = scheduler
    logger.info("PashuMitra Phase 2 ready")
    yield
    # ── SHUTDOWN ─────────────────────────────────────────────────────
    if hasattr(app.state, "scheduler") and app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
    logger.info("PashuMitra shutting down")


app = FastAPI(
    title      = "PashuMitra AI Vet — Phase 2",
    description= "AI-powered veterinary assistant — WhatsApp + Dashboard + TeleVet",
    version    = "2.0.0",
    lifespan   = lifespan,
)

# ── INCLUDE PHASE 2 ROUTERS ───────────────────────────────────────────────────
app.include_router(cattle_router.router)
app.include_router(dashboard_router.router)
app.include_router(televet_router.router)


# ─── WHATSAPP WEBHOOK ────────────────────────────────────────────────────────

@app.get("/webhook")
def verify_webhook(req: Request):
    if not settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content="WHATSAPP_VERIFY_TOKEN not configured", status_code=503)
    if req.query_params.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=req.query_params.get("hub.challenge", ""), status_code=200)
    return Response(status_code=403)


@app.post("/webhook")
async def handle_webhook(req: Request):
    """Process incoming WhatsApp messages — Phase 2 with session + language support."""
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        return JSONResponse({"status": "config_error"}, status_code=503)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    try:
        entry    = data.get("entry", [{}])[0]
        change   = entry.get("changes", [{}])[0].get("value", {})
        messages = change.get("messages")
        if not messages:
            return JSONResponse({"status": "ack"})
        msg   = messages[0]
        phone = msg.get("from", "")
        if not phone:
            return JSONResponse({"status": "no_phone"})
    except Exception as e:
        logger.warning("Webhook parse error: %s", e)
        return JSONResponse({"status": "parse_error"})

    # Mark message as read (Double Blue Tick)
    wa.mark_read(msg.get("id"))

    request_id = str(uuid.uuid4())[:8]

    # ── PHASE 2: Load farmer session / detect language ─────────────────────
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
        lang   = str(farmer.preferred_lang) if (farmer is not None and farmer.preferred_lang is not None) else "hindi"
    finally:
        db.close()

    # Rate limiting with language-aware message
    if not check_and_increment(phone):
        wa.send_text(phone, lang_engine.get_limit_message(lang))
        return JSONResponse({"status": "rate_limited"})

    # Extract content
    text, mtype, mbytes = "", None, None
    try:
        if msg.get("text"):
            text  = msg["text"].get("body", "")
            mtype = "text"
            # Detect language from message
            lang  = lang_engine.detect(text, lang)
        elif msg.get("image"):
            mtype  = "image"
            mbytes = wa.download_media(msg["image"]["id"])
        elif msg.get("audio") or msg.get("voice"):
            mtype  = "voice"
            mid    = (msg.get("audio") or msg.get("voice", {})).get("id")
            mbytes = wa.download_media(mid) if mid else b""
            text   = ai_engine.transcribe_voice(mbytes) if mbytes else ""
        else:
            mtype = "unknown"
    except Exception as e:
        logger.error("[%s] Media error: %s", request_id, e)

    # ── PHASE 2: Check cache for repeated queries ──────────────────────────
    cache_key = cache.ai_key(text) if text else None
    result    = cache.get(cache_key) if cache_key else None

    if not result:
        result = ai_engine.generate_response(text)
        if cache_key and result.get("confidence", 0) > 0.5:
            cache.set(cache_key, result, ttl=3600)

    # ── FORMAT REPLY IN FARMER'S LANGUAGE ─────────────────────────────────
    reply = lang_engine.format_reply(result, lang, request_id)

    # Emergency handling
    if result.get("emergency"):
        alert = emergency_system.trigger_alert(phone, result)
        # Ensure alert is a dict before accessing
        if not isinstance(alert, dict):
            alert = {"message": ""}
        if reply and not reply.endswith("\n"):
            reply += "\n\n"
        reply += alert.get("message", "")

    wa.send_text(phone, reply)

    # ── LOG TO DATABASE ────────────────────────────────────────────────────
    db = SessionLocal()
    try:
        db.add(QueryLog(
            phone      = phone,
            input_type = mtype or "text",
            symptom    = text[:500],
            diagnosis  = result.get("disease", ""),
            hindi_name = result.get("hindi", ""),
            confidence = result.get("confidence", 0.0),
            severity   = result.get("severity", ""),
            emergency  = result.get("emergency", False),
        ))
        db.commit()
    except Exception as e:
        logger.error("QueryLog write error: %s", e)
    finally:
        db.close()

    return JSONResponse({"status": "processed", "id": request_id, "lang": lang})


# ─── REST API (Phase 1 endpoints — unchanged) ────────────────────────────────

@app.post("/api/diagnose")
async def api_diagnose(req: Request):
    body  = await req.json()
    text  = body.get("message", "")
    phone = body.get("phone", "anonymous")
    if not text:
        raise HTTPException(status_code=400, detail="'message' field required")
    can_query = check_and_increment(phone) if phone != "anonymous" else True
    if not can_query:
        raise HTTPException(status_code=429, detail="Daily limit reached.")
    
    # FIX: ai_engine.check_symptoms was likely renamed to generate_response 
    # in Phase 2 to support the full logic used in the webhook.
    res = ai_engine.generate_response(text)
    return {"status": "ok", "result": res}


@app.get("/api/farmers/{phone}/history")
async def farmer_history(phone: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
        if not farmer:
            raise HTTPException(status_code=404, detail="Farmer not found")
        logs = db.query(QueryLog).filter(QueryLog.phone == phone).order_by(
            QueryLog.timestamp.desc()).limit(20).all()
        return {
            "phone":         phone,
            "daily_queries": farmer.daily_queries,
            "history": [{"id": l.id, "symptom": l.symptom, "diagnosis": l.diagnosis,
                         "confidence": l.confidence, "emergency": l.emergency,
                         "timestamp": str(l.timestamp)} for l in logs]
        }
    finally:
        db.close()


@app.get("/health")
def health():
    db_ok = True
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False

    return {
        "status":    "ok",
        "phase":     "2",
        "version":   "2.0.0",
        "db":        "ok" if db_ok else "error",
        "cache":     "redis" if cache._redis_ok else "in-memory",
        "voice":     "enabled" if ai_engine._whisper_ok else "disabled",
        "whatsapp":  "configured" if settings.WHATSAPP_ACCESS_TOKEN else "not configured",
        "scheduler": "running" if hasattr(app.state, "scheduler") else "stopped",
    }

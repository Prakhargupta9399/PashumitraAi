# app/routers/televet.py
# NEW Phase 2: Tele-vet booking API endpoints.

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.televet import televet_service
from app.models import VetProfile
import uuid

router = APIRouter(prefix="/api/televet", tags=["TeleVet"])


class BookingRequest(BaseModel):
    farmer_phone: str
    vet_id:       str
    scheduled_at: datetime
    symptoms:     Optional[str] = ""
    cattle_id:    Optional[str] = None


class VetCreate(BaseModel):
    name:           str
    phone:          str
    district:       str
    state:          str
    specialization: Optional[str] = "General"
    lat:            Optional[float] = None
    lon:            Optional[float] = None
    charge_inr:     Optional[int] = 99


@router.get("/vets")
def list_vets(district: Optional[str] = None,
              specialization: Optional[str] = None,
              db: Session = Depends(get_db)):
    """List available vets."""
    return televet_service.find_available_vets(db, district, specialization)


@router.post("/vets")
def register_vet(data: VetCreate, db: Session = Depends(get_db)):
    """Register a new vet (admin use)."""
    vet = VetProfile(
        id             = str(uuid.uuid4()),
        name           = data.name,
        phone          = data.phone,
        district       = data.district,
        state          = data.state,
        specialization = data.specialization,
        lat            = data.lat,
        lon            = data.lon,
        charge_inr     = data.charge_inr,
    )
    db.add(vet)
    db.commit()
    return {"status": "registered", "vet_id": vet.id}


@router.post("/book")
def book_televet(req: BookingRequest, db: Session = Depends(get_db)):
    """Book a tele-vet consultation."""
    result = televet_service.create_booking(
        db, req.farmer_phone, req.vet_id,
        req.scheduled_at, req.symptoms or "", req.cattle_id
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/book/{booking_id}/confirm")
def confirm_booking(booking_id: int, db: Session = Depends(get_db)):
    """Confirm a booking (called after payment)."""
    ok = televet_service.confirm_booking(db, booking_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"status": "confirmed"}


@router.get("/farmer/{phone}/bookings")
def farmer_bookings(phone: str, db: Session = Depends(get_db)):
    """Get all bookings for a farmer."""
    return televet_service.get_farmer_bookings(db, phone)

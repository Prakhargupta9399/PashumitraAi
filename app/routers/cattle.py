# app/routers/cattle.py
# NEW Phase 2: Full cattle profile CRUD + milk/vaccination/breeding endpoints.

import uuid
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cattle, MilkRecord, VaccinationRecord, BreedingRecord
from app.services.milk_optimizer import milk_optimizer
from app.services.vaccination import vaccination_manager
from app.services.breeding import breeding_assistant

router = APIRouter(prefix="/api/cattle", tags=["Cattle"])


# ── PYDANTIC SCHEMAS ──────────────────────────────────────────────────────────

class CattleCreate(BaseModel):
    farmer_phone:  str
    name:          Optional[str] = ""
    tag_number:    Optional[str] = ""
    gender:        Optional[str] = "female"
    breed:         Optional[str] = "Other"
    dob:           Optional[date] = None
    weight_kg:     Optional[float] = 0.0
    colour:        Optional[str] = ""
    purchase_cost: Optional[float] = 0.0
    notes:         Optional[str] = ""

class MilkRecordIn(BaseModel):
    date:         date
    morning_ltrs: float
    evening_ltrs: float
    fat_pct:      Optional[float] = 0.0
    price_per_ltr: Optional[float] = 35.0

class VaccinationIn(BaseModel):
    vaccine_name: str
    given_date:   date
    given_by:     Optional[str] = ""
    batch_number: Optional[str] = ""
    is_free:      Optional[bool] = True

class InseminationIn(BaseModel):
    insemination_date: date
    bull_breed:        Optional[str] = "HF"
    method:            Optional[str] = "AI"

class CalvingUpdateIn(BaseModel):
    actual_calving: date
    calf_gender:    Optional[str] = None
    notes:          Optional[str] = ""


# ── CATTLE ENDPOINTS ──────────────────────────────────────────────────────────

@router.post("/")
def add_cattle(data: CattleCreate, db: Session = Depends(get_db)):
    """Register a new cattle animal for a farmer."""
    cattle = Cattle(
        id            = str(uuid.uuid4()),
        farmer_phone  = data.farmer_phone,
        name          = data.name,
        tag_number    = data.tag_number,
        gender        = data.gender,
        breed         = data.breed,
        dob           = data.dob,
        weight_kg     = data.weight_kg,
        colour        = data.colour,
        purchase_cost = data.purchase_cost,
        notes         = data.notes,
    )
    db.add(cattle)
    db.commit()
    db.refresh(cattle)
    return {"status": "created", "cattle_id": cattle.id, "name": cattle.name}


@router.get("/farmer/{phone}")
def get_farmer_cattle(phone: str, db: Session = Depends(get_db)):
    """Get all cattle for a farmer."""
    cattle_list = (
        db.query(Cattle)
        .filter(Cattle.farmer_phone == phone, Cattle.is_active == True)
        .all()
    )
    return [
        {
            "id":    c.id, "name": c.name, "tag_number": c.tag_number,
            "breed": c.breed, "gender": c.gender,
            "dob":   str(c.dob) if c.dob is not None else None,
            "weight_kg": c.weight_kg,
        }
        for c in cattle_list
    ]


@router.get("/{cattle_id}")
def get_cattle(cattle_id: str, db: Session = Depends(get_db)):
    """Get full cattle profile."""
    cattle = db.query(Cattle).filter(Cattle.id == cattle_id).first()
    if not cattle:
        raise HTTPException(status_code=404, detail="Cattle not found")
    return {
        "id":            cattle.id,
        "name":          cattle.name,
        "tag_number":    cattle.tag_number,
        "breed":         cattle.breed,
        "gender":        cattle.gender,
        "dob":           str(cattle.dob) if cattle.dob is not None else None,
        "weight_kg":     cattle.weight_kg,
        "colour":        cattle.colour,
        "purchase_cost": cattle.purchase_cost,
        "is_active":     cattle.is_active,
        "notes":         cattle.notes,
    }


@router.delete("/{cattle_id}")
def deactivate_cattle(cattle_id: str, db: Session = Depends(get_db)):
    """Mark cattle as sold/dead (soft delete)."""
    cattle = db.query(Cattle).filter(Cattle.id == cattle_id).first()
    if not cattle:
        raise HTTPException(status_code=404, detail="Cattle not found")
    setattr(cattle, "is_active", False)
    db.commit()
    return {"status": "deactivated"}


# ── MILK ENDPOINTS ────────────────────────────────────────────────────────────

@router.post("/{cattle_id}/milk")
def add_milk_record(cattle_id: str, data: MilkRecordIn, db: Session = Depends(get_db)):
    """Add daily milk production record."""
    record = milk_optimizer.add_record(
        db, cattle_id, data.date, data.morning_ltrs,
        data.evening_ltrs, data.fat_pct or 0.0, data.price_per_ltr or 35.0
    )
    total = float(getattr(record, "total_ltrs", 0.0) or 0.0)
    price = float(getattr(record, "price_per_ltr", 0.0) or 0.0)
    return {"status": "recorded", "total_litres": total, "revenue": round(total * price, 2)}


@router.get("/{cattle_id}/milk/trend")
def get_milk_trend(cattle_id: str, days: int = 30, db: Session = Depends(get_db)):
    """Get milk yield trend."""
    return milk_optimizer.get_trend(db, cattle_id, days)


@router.get("/{cattle_id}/milk/optimize")
def optimize_milk(cattle_id: str, db: Session = Depends(get_db)):
    """Get full milk optimization report with diet plan."""
    return milk_optimizer.optimize(db, cattle_id)


@router.get("/{cattle_id}/milk/monthly")
def monthly_milk(cattle_id: str, year: int, month: int, db: Session = Depends(get_db)):
    """Monthly milk production summary."""
    return milk_optimizer.get_monthly_summary(db, cattle_id, year, month)


# ── VACCINATION ENDPOINTS ─────────────────────────────────────────────────────

@router.post("/{cattle_id}/vaccinations")
def add_vaccination(cattle_id: str, data: VaccinationIn, db: Session = Depends(get_db)):
    """Record a vaccination for a cattle animal."""
    record = vaccination_manager.add_record(
        db, cattle_id, data.vaccine_name, data.given_date,
        data.given_by or "", data.batch_number or "", data.is_free if data.is_free is not None else True
    )
    return {"status": "recorded", "id": record.id,
            "next_due": str(record.next_due) if record.next_due is not None else "N/A"}


@router.get("/{cattle_id}/vaccinations")
def get_vaccinations(cattle_id: str, db: Session = Depends(get_db)):
    """Get vaccination history and schedule."""
    return vaccination_manager.get_cattle_schedule(db, cattle_id)


# ── BREEDING ENDPOINTS ────────────────────────────────────────────────────────

@router.post("/{cattle_id}/breeding")
def add_insemination(cattle_id: str, data: InseminationIn, db: Session = Depends(get_db)):
    """Record an insemination."""
    record = breeding_assistant.add_insemination(
        db, cattle_id, data.insemination_date, data.bull_breed or "HF", data.method or "AI"
    )
    return {"status": "recorded", "id": record.id,
            "expected_calving": str(record.expected_calving)}


@router.put("/{cattle_id}/breeding/{record_id}/calving")
def update_calving(cattle_id: str, record_id: int,
                   data: CalvingUpdateIn, db: Session = Depends(get_db)):
    """Update actual calving outcome."""
    rec = db.query(BreedingRecord).filter(
        BreedingRecord.id == record_id,
        BreedingRecord.cattle_id == cattle_id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Breeding record not found")
    setattr(rec, "actual_calving", data.actual_calving)
    setattr(rec, "calf_gender", data.calf_gender)
    setattr(rec, "outcome_notes", data.notes or "")
    setattr(rec, "pregnancy_confirmed", True)
    db.commit()
    return {"status": "updated", "calving_date": str(rec.actual_calving)}


@router.get("/{cattle_id}/breeding/summary")
def breeding_summary(cattle_id: str, db: Session = Depends(get_db)):
    """Get full breeding summary for an animal."""
    return breeding_assistant.get_cattle_breeding_summary(db, cattle_id)

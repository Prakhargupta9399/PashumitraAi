# app/routers/dashboard.py
# NEW Phase 2: Farmer dashboard REST API — summary, analytics, usage stats.

from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Farmer, Cattle, MilkRecord, QueryLog, VaccinationRecord
from app.limits import get_usage
from app.services.milk_optimizer import milk_optimizer
from app.services.vaccination import vaccination_manager

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/{phone}")
def get_dashboard(phone: str, db: Session = Depends(get_db)):
    """
    Full farmer dashboard summary.
    Returns: profile, usage, cattle count, milk summary,
             upcoming vaccinations, recent diagnoses.
    """
    farmer = db.query(Farmer).filter(Farmer.phone == phone).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    usage = get_usage(phone)

    # Active cattle
    cattle_list = (
        db.query(Cattle)
        .filter(Cattle.farmer_phone == phone, Cattle.is_active == True)
        .all()
    )

    # Today's milk total across all animals
    today_milk = (
        db.query(func.sum(MilkRecord.total_ltrs))
        .join(Cattle, MilkRecord.cattle_id == Cattle.id)
        .filter(Cattle.farmer_phone == phone, MilkRecord.date == date.today())
        .scalar() or 0.0
    )

    # This month's milk revenue
    first_of_month = date.today().replace(day=1)
    month_revenue = (
        db.query(func.sum(MilkRecord.total_ltrs * MilkRecord.price_per_ltr))
        .join(Cattle, MilkRecord.cattle_id == Cattle.id)
        .filter(Cattle.farmer_phone == phone,
                MilkRecord.date >= first_of_month)
        .scalar() or 0.0
    )

    # Upcoming vaccinations (next 30 days)
    upcoming_vax = vaccination_manager.get_due_reminders(db, days_ahead=30)
    upcoming_vax = [v for v in upcoming_vax if v["farmer_phone"] == phone]

    # Recent diagnoses (last 5)
    recent_logs = (
        db.query(QueryLog)
        .filter(QueryLog.phone == phone)
        .order_by(QueryLog.timestamp.desc())
        .limit(5)
        .all()
    )

    # 7-day milk chart data
    milk_chart = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        total = (
            db.query(func.sum(MilkRecord.total_ltrs))
            .join(Cattle, MilkRecord.cattle_id == Cattle.id)
            .filter(Cattle.farmer_phone == phone, MilkRecord.date == d)
            .scalar() or 0.0
        )
        milk_chart.append({"date": str(d), "litres": round(total, 2)})

    return {
        "farmer": {
            "phone":        farmer.phone,
            "name":         farmer.name,
            "village":      farmer.village,
            "district":     farmer.district,
            "state":        farmer.state,
            "is_premium":   farmer.is_premium,
            "language":     farmer.preferred_lang,
            "cattle_count": len(cattle_list),
            "member_since": str(farmer.created_at)[:10] if farmer.created_at is not None else "",
        },
        "usage": usage,
        "milk": {
            "today_total_litres":   round(today_milk, 2),
            "month_revenue_inr":    round(month_revenue, 2),
            "week_chart":           milk_chart,
        },
        "cattle": [
            {"id": c.id, "name": c.name, "breed": c.breed,
             "tag": c.tag_number, "gender": c.gender}
            for c in cattle_list
        ],
        "upcoming_vaccinations": upcoming_vax[:5],
        "recent_diagnoses": [
            {
                "id":        l.id,
                "symptom":   l.symptom[:80],
                "diagnosis": l.diagnosis,
                "severity":  l.severity,
                "emergency": l.emergency,
                "time":      str(l.timestamp)[:16],
            }
            for l in recent_logs
        ],
    }


@router.get("/{phone}/analytics")
def get_analytics(phone: str, db: Session = Depends(get_db)):
    """
    30-day analytics for a farmer:
    disease frequency, milk trends per animal, revenue breakdown.
    """
    since = date.today() - timedelta(days=30)

    # Disease frequency
    disease_counts = (
        db.query(QueryLog.diagnosis, func.count(QueryLog.id).label("count"))
        .filter(QueryLog.phone == phone, QueryLog.timestamp >= since)
        .group_by(QueryLog.diagnosis)
        .order_by(func.count(QueryLog.id).desc())
        .limit(5)
        .all()
    )

    # Per-animal milk trends
    cattle_list = (
        db.query(Cattle)
        .filter(Cattle.farmer_phone == phone, Cattle.is_active == True)
        .all()
    )
    cattle_milk = []
    for c in cattle_list:
        trend = milk_optimizer.get_trend(db, str(c.id), days=30)
        cattle_milk.append({
            "cattle_id":  c.id,
            "name":       c.name or c.tag_number,
            "avg_daily":  trend.get("avg_daily", 0),
            "trend":      trend.get("trend", "no_data"),
            "revenue_30d": trend.get("total_revenue", 0),
        })

    return {
        "period":          "last_30_days",
        "disease_frequency": [{"disease": r.diagnosis, "count": r.count}
                               for r in disease_counts],
        "cattle_milk":     cattle_milk,
        "total_cattle":    len(cattle_list),
    }

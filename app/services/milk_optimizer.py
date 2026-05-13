# app/services/milk_optimizer.py
# NEW Phase 2: Milk yield tracking, trend analysis, diet optimization,
# stress detection, and revenue calculation per animal.

import logging
from calendar import monthrange                  # FIX 3: moved from inside method to top-level
from datetime import date, timedelta
from typing import Dict, List                    # FIX 1: removed unused `Optional` and `Tuple`
from sqlalchemy.orm import Session
                                                 # FIX 2: removed unused `from sqlalchemy import func`
from app.models import Cattle, MilkRecord

logger = logging.getLogger("pashumitra.milk")

# ── BREED BENCHMARKS (litres/day at peak lactation) ──────────────────────────
BREED_BENCHMARKS: Dict[str, Dict] = {
    "HF Cross":       {"peak": 20.0, "avg": 14.0, "lactation_days": 305},
    "Jersey Cross":   {"peak": 16.0, "avg": 11.0, "lactation_days": 305},
    "Gir":            {"peak": 12.0, "avg":  8.0, "lactation_days": 280},
    "Sahiwal":        {"peak": 10.0, "avg":  7.0, "lactation_days": 280},
    "Murrah Buffalo": {"peak": 14.0, "avg": 10.0, "lactation_days": 270},
    "Other":          {"peak": 10.0, "avg":  7.0, "lactation_days": 280},
}

# ── DIET RECOMMENDATIONS BY YIELD ─────────────────────────────────────────────
def _get_diet_plan(current_yield: float, breed: str) -> Dict:
    """Return diet plan in Hindi based on current yield vs benchmark."""
    bench = BREED_BENCHMARKS.get(breed, BREED_BENCHMARKS["Other"])
    pct   = current_yield / bench["avg"] if bench["avg"] > 0 else 1.0

    if pct >= 1.0:
        return {
            "status":       "optimal",
            "message":      "✅ दूध उत्पादन बेहतरीन है!",
            "dry_fodder":   "4-6 kg/day (तूड़ी/भूसा)",
            "green_fodder": "20-25 kg/day (हरा चारा)",
            "concentrate":  f"{max(2.0, current_yield * 0.4):.1f} kg/day",
            "mineral_mix":  "50g/day",
            "water":        "50-60 litre/day",
            "supplements":  "Calcium bolus 2x/day during lactation",
        }
    elif pct >= 0.7:
        return {
            "status":       "below_average",
            "message":      "⚠️ दूध उत्पादन औसत से कम है। आहार बढ़ाएं।",
            "dry_fodder":   "5-7 kg/day",
            "green_fodder": "25-30 kg/day",
            "concentrate":  f"{max(3.0, current_yield * 0.5):.1f} kg/day",
            "mineral_mix":  "75g/day",
            "water":        "60-70 litre/day",
            "supplements":  "Vitamin E + Selenium injection. Liver tonic 50ml/day.",
        }
    else:
        return {
            "status":       "low",
            "message":      "🔴 दूध उत्पादन बहुत कम है! पशु चिकित्सक से मिलें।",
            "dry_fodder":   "6-8 kg/day",
            "green_fodder": "25-35 kg/day",
            "concentrate":  f"{max(4.0, current_yield * 0.6):.1f} kg/day",
            "mineral_mix":  "100g/day",
            "water":        "70-80 litre/day",
            "supplements":  "B12 injection, Calcium IV if needed. Check for mastitis!",
        }


class MilkOptimizer:

    def add_record(self, db: Session, cattle_id: str, record_date: date,
                   morning: float, evening: float,
                   fat_pct: float = 0.0, price: float = 35.0) -> MilkRecord:
        """Add daily milk record."""
        total  = morning + evening
        record = MilkRecord(
            cattle_id     = cattle_id,
            date          = record_date,
            morning_ltrs  = morning,
            evening_ltrs  = evening,
            total_ltrs    = total,
            fat_pct       = fat_pct,
            price_per_ltr = price,
        )
        db.add(record)
        # FIX 4: wrap commit so a DB failure rolls back cleanly instead of
        # leaving the session in a broken/partial state.
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return record

    def get_trend(self, db: Session, cattle_id: str, days: int = 30) -> Dict:
        """
        Returns milk yield trend for the last `days` days.
        Detects declining trend (possible mastitis / stress / nutrition).
        """
        since   = date.today() - timedelta(days=days)
        records = (
            db.query(MilkRecord)
            .filter(MilkRecord.cattle_id == cattle_id,
                    MilkRecord.date >= since)
            .order_by(MilkRecord.date.asc())
            .all()
        )

        if not records:
            # FIX 5: return ALL keys that callers rely on to avoid KeyError
            return {
                "cattle_id":     cattle_id,
                "days":          days,
                "records":       [],
                "avg_daily":     0,
                "peak_day":      0.0,
                "lowest_day":    0.0,
                "trend":         "no_data",
                "total_revenue": 0,
            }

        # FIX 6: coerce NULL total_ltrs (nullable DB column) to 0.0
        yields = [float(getattr(r, "total_ltrs", 0.0) or 0.0) for r in records]
        dates  = [str(r.date) for r in records]

        # Simple linear trend: compare first-half avg vs second-half avg
        mid          = len(yields) // 2
        avg_all      = sum(yields) / len(yields)
        trend_status = "stable"

        if mid > 0:
            avg_first  = sum(yields[:mid]) / mid
            avg_second = sum(yields[mid:]) / (len(yields) - mid)
            change_pct = ((avg_second - avg_first) / avg_first * 100) if avg_first > 0 else 0

            if change_pct < -10:
                trend_status = "declining"
            elif change_pct > 10:
                trend_status = "improving"
            else:
                trend_status = "stable"

        # FIX 6 (cont.): guard NULL price_per_ltr too
        total_revenue = sum(
            float(getattr(r, "total_ltrs", 0.0) or 0.0) * float(getattr(r, "price_per_ltr", 0.0) or 0.0)
            for r in records
        )

        return {
            "cattle_id":     cattle_id,
            "days":          days,
            "records":       [{"date": d, "yield": y} for d, y in zip(dates, yields)],
            # FIX 7: avg_all is always a float here; dropped the dead
            # `if avg_all is not None` check that could never be False.
            "avg_daily":     round(avg_all, 2),
            "peak_day":      max(yields),
            "lowest_day":    min(yields),
            "trend":         trend_status,
            "total_revenue": round(total_revenue, 2),
        }

    def get_monthly_summary(self, db: Session, cattle_id: str,
                            year: int, month: int) -> Dict:
        """Monthly milk production summary with revenue."""
        # FIX 3 (cont.): monthrange now imported at top-level
        _, last_day = monthrange(year, month)
        start = date(year, month, 1)
        end   = date(year, month, last_day)

        records = (
            db.query(MilkRecord)
            .filter(MilkRecord.cattle_id == cattle_id,
                    MilkRecord.date >= start,
                    MilkRecord.date <= end)
            .all()
        )

        # FIX 6 (cont.): guard NULL total_ltrs / price_per_ltr
        total_litres  = sum(float(getattr(r, "total_ltrs", 0.0) or 0.0) for r in records)
        total_revenue = sum(
            float(getattr(r, "total_ltrs", 0.0) or 0.0) * float(getattr(r, "price_per_ltr", 0.0) or 0.0)
            for r in records
        )

        # FIX 8 CRITICAL: original `r.fat_pct > 0` raises TypeError when
        # fat_pct is NULL (None). Must check `is not None` first.
        valid_fat = [float(getattr(r, "fat_pct", 0.0) or 0.0) for r in records if getattr(r, "fat_pct", None) is not None and float(getattr(r, "fat_pct", 0.0) or 0.0) > 0]
        avg_fat   = sum(valid_fat) / len(valid_fat) if valid_fat else 0.0

        return {
            "year":          year,
            "month":         month,
            "days_recorded": len(records),
            "total_litres":  round(total_litres, 2),
            "avg_daily":     round(total_litres / max(1, len(records)), 2),
            "avg_fat_pct":   round(avg_fat, 2),
            "total_revenue": round(total_revenue, 2),
        }

    def optimize(self, db: Session, cattle_id: str) -> Dict:
        """
        Full milk optimization report for one animal:
        trend analysis + diet recommendations + alerts.
        """
        cattle = db.query(Cattle).filter(Cattle.id == cattle_id).first()
        if not cattle:
            return {"error": "Cattle not found"}

        trend = self.get_trend(db, cattle_id, days=14)
        avg   = trend.get("avg_daily", 0)
        breed = str(cattle.breed)
        diet  = _get_diet_plan(avg, breed)

        alerts: List[Dict] = []
        if trend["trend"] == "declining":
            alerts.append({
                "type":    "milk_decline",
                "message": "⚠️ पिछले 14 दिनों में दूध कम हुआ है! थनैला / तनाव जांचें।",
                "action":  "Check for mastitis. Consult vet if decline > 20%.",
            })
        if avg < BREED_BENCHMARKS.get(breed, BREED_BENCHMARKS["Other"]).get("avg", 7) * 0.6:
            alerts.append({
                "type":    "low_yield",
                "message": "🔴 उत्पादन नस्ल औसत से 40% कम है।",
                "action":  "Review diet, check for subclinical diseases.",
            })

        return {
            "cattle_id": cattle_id,
            "name":      cattle.name,
            "breed":     cattle.breed,
            "trend":     trend,
            "diet_plan": diet,
            "alerts":    alerts,
            "monthly":   self.get_monthly_summary(
                             db, cattle_id, date.today().year, date.today().month),
        }

    def format_whatsapp(self, report: Dict) -> str:
        """Format milk optimization report for WhatsApp."""
        trend = report.get("trend", {})
        diet  = report.get("diet_plan", {})
        icon  = {"declining": "📉", "improving": "📈", "stable": "📊"}.get(
                    trend.get("trend", "stable"), "📊")

        lines = [
            f"🥛 *दूध उत्पादन रिपोर्ट — {report.get('name', 'Unnamed')}*\n",
            f"{icon} *रुझान (14 दिन):* {trend.get('trend', 'N/A').upper()}",
            f"📏 *औसत दैनिक:* {trend.get('avg_daily', 0)} लीटर",
            f"💰 *कुल आय (14 दिन):* ₹{trend.get('total_revenue', 0):.0f}\n",
            f"*{diet.get('message', '')}*\n",
            f"🌾 *सूखा चारा:* {diet.get('dry_fodder', 'N/A')}",
            f"🌿 *हरा चारा:* {diet.get('green_fodder', 'N/A')}",
            f"🌽 *दाना:* {diet.get('concentrate', 'N/A')}",
            f"🧂 *मिनरल मिक्स:* {diet.get('mineral_mix', 'N/A')}",
            f"💧 *पानी:* {diet.get('water', 'N/A')}",
        ]

        for alert in report.get("alerts", []):
            lines.append(f"\n{alert['message']}")

        return "\n".join(lines)


milk_optimizer = MilkOptimizer()
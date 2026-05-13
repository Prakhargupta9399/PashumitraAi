# app/services/breeding.py
# NEW Phase 2: Breeding assistant — heat detection, AI insemination tracker,
# calving prediction, inter-calving interval analysis.

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Cattle, BreedingRecord

logger = logging.getLogger("pashumitra.breeding")

# ── BREED-SPECIFIC CONSTANTS ──────────────────────────────────────────────────
GESTATION_DAYS: Dict[str, int] = {
    "HF Cross":     278,
    "Jersey Cross": 278,
    "Gir":          285,
    "Sahiwal":      285,
    "Murrah Buffalo": 310,
    "Other":        280,
}

HEAT_CYCLE_DAYS: Dict[str, int] = {
    "HF Cross":     21,
    "Jersey Cross": 21,
    "Gir":          21,
    "Sahiwal":      21,
    "Murrah Buffalo": 21,
    "Other":        21,
}

# Ideal inter-calving interval = 365–400 days (12–13 months)
IDEAL_ICI_MIN = 365
IDEAL_ICI_MAX = 400


class BreedingAssistant:

    def predict_calving(self, insemination_date: date, breed: str) -> date:
        """Predict calving date from insemination date + breed gestation."""
        days = GESTATION_DAYS.get(breed, 280)
        return insemination_date + timedelta(days=days)

    def predict_next_heat(self, last_calving: date, breed: str) -> date:
        """
        Predict next heat cycle.
        Rule: Cows typically return to heat 60–90 days post-calving (voluntary waiting period).
        We use 60 days as default.
        """
        return last_calving + timedelta(days=60)

    def analyze_ici(self, calving_dates: List[date]) -> Dict:
        """
        Calculate inter-calving interval (ICI) from list of calving dates.
        Returns average ICI and recommendation.
        """
        if len(calving_dates) < 2:
            return {"ici_days": None, "status": "insufficient_data", "advice": ""}

        intervals = [
            (calving_dates[i+1] - calving_dates[i]).days
            for i in range(len(calving_dates) - 1)
        ]
        avg_ici = sum(intervals) / len(intervals)

        if avg_ici < IDEAL_ICI_MIN:
            status = "too_short"
            advice = (f"⚠️ ICI बहुत कम है ({avg_ici:.0f} दिन)। "
                      "गाय को ठीक से ठीक होने का समय दें। "
                      "अगले ब्याह के बाद कम से कम 60 दिन इंतजार करें।")
        elif avg_ici > IDEAL_ICI_MAX:
            status = "too_long"
            advice = (f"⚠️ ICI बहुत अधिक है ({avg_ici:.0f} दिन)। "
                      "गाय का पोषण जांचें, vet से प्रजनन परीक्षण कराएं।")
        else:
            status = "ideal"
            advice = (f"✅ ICI आदर्श है ({avg_ici:.0f} दिन)। "
                      "उत्पादकता बेहतरीन है!")

        return {
            "ici_days": round(avg_ici, 1),
            "intervals": intervals,
            "status": status,
            "advice": advice,
        }

    def get_cattle_breeding_summary(self, db: Session, cattle_id: str) -> Dict:
        """Full breeding status for one animal."""
        cattle = db.query(Cattle).filter(Cattle.id == cattle_id).first()
        if not cattle:
            return {"error": "Cattle not found"}

        records = (
            db.query(BreedingRecord)
            .filter(BreedingRecord.cattle_id == cattle_id)
            .order_by(BreedingRecord.insemination_date.desc())
            .all()
        )

        summary: Dict = {
            "cattle_id":   cattle_id,
            "name":        cattle.name,
            "breed":       cattle.breed,
            "total_calvings": 0,
            "last_calving": None,
            "expected_calving": None,
            "next_heat_prediction": None,
            "ici_analysis": {},
            "records": [],
        }

        calving_dates = []
        for rec in records:
            r_dict = {
                "insemination_date": str(rec.insemination_date),
                "method":            rec.method,
                "bull_breed":        rec.bull_breed,
                "pregnancy_confirmed": rec.pregnancy_confirmed,
                "expected_calving":  str(rec.expected_calving) if rec.expected_calving is not None else None,
                "actual_calving":    str(rec.actual_calving) if rec.actual_calving is not None else None,
                "calf_gender":       rec.calf_gender,
            }
            summary["records"].append(r_dict)

            if rec.actual_calving is not None:
                calving_dates.append(rec.actual_calving)
                summary["total_calvings"] += 1
            elif rec.expected_calving is not None:
                summary["expected_calving"] = str(rec.expected_calving)

        if calving_dates:
            calving_dates.sort()
            last_calving = calving_dates[-1]
            summary["last_calving"]           = str(last_calving)
            summary["next_heat_prediction"]   = str(self.predict_next_heat(last_calving, str(cattle.breed)))
            summary["ici_analysis"]           = self.analyze_ici(calving_dates)

        return summary

    def add_insemination(self, db: Session, cattle_id: str,
                         insemination_date: date, bull_breed: str = "HF",
                         method: str = "AI") -> BreedingRecord:
        """Record an insemination and auto-predict calving date."""
        cattle = db.query(Cattle).filter(Cattle.id == cattle_id).first()
        breed  = str(cattle.breed) if (cattle is not None and cattle.breed is not None) else "Other"

        expected = self.predict_calving(insemination_date, breed)
        record   = BreedingRecord(
            cattle_id         = cattle_id,
            insemination_date = insemination_date,
            bull_breed        = bull_breed,
            method            = method,
            expected_calving  = expected,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("Insemination recorded: cattle=%s expected=%s", cattle_id[:8], expected)
        return record

    def format_breeding_whatsapp(self, summary: Dict) -> str:
        """Format breeding summary for WhatsApp message."""
        lines = [
            f"🐄 *प्रजनन रिपोर्ट — {summary.get('name', 'Unnamed')}*\n",
            f"🐮 नस्ल: {summary.get('breed', 'N/A')}",
            f"🍼 कुल बच्चे: {summary.get('total_calvings', 0)}",
        ]
        if summary.get("last_calving"):
            lines.append(f"📅 आखिरी बियान: {summary['last_calving']}")
        if summary.get("expected_calving"):
            lines.append(f"🐣 अगला बियान (अनुमानित): *{summary['expected_calving']}*")
        if summary.get("next_heat_prediction"):
            lines.append(f"🌡️ अगली गर्मी: *{summary['next_heat_prediction']}*")
        if summary.get("ici_analysis", {}).get("advice"):
            lines.append(f"\n{summary['ici_analysis']['advice']}")
        return "\n".join(lines)


breeding_assistant = BreedingAssistant()
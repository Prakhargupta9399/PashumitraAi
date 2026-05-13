# app/services/ai_engine.py
# FIXES: 1) whisper optional (no crash if not installed)  2) lazy load
#         3) confidence inconsistency fixed  4) proper typing
# NEW:   multilingual synonyms, differential diagnosis, diet advice,
#         prevention tips, vaccination reminders, severity scoring

import io, logging, tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pashumitra.ai")

SYNONYMS: Dict[str, List[str]] = {
    "bukhar":     ["fever","jwar","tapman","garmi","garam"],
    "dast":       ["loose motion","diarrhea","patlaa","patla gobar","pait kharab"],
    "doodh kam":  ["milk less","milk reduced","udder hard","thick milk","gaay ka doodh","than se kam"],
    "pet fool":   ["bloat","afara","tympany","pait phula","gas","baayi taraf","left side"],
    "ghav":       ["wound","skin lesion","khal","suji","chot","khujli","kilni","daane"],
    "khansi":     ["cough","nasal discharge","naak se paani","mucus","khaans","saans"],
    "khurpaka":   ["fmd","foot mouth","muh mein chhale","khur mein ghav","mukhpaka","liblib","chhale"],
    "khana band": ["not eating","appetite loss","khana nahi","feed refusal","anorexia"],
}

VACCINATION_SCHEDULE = {
    "FMD":         {"interval_months": 6,   "free": True,  "hindi": "खुरपका-मुँहपका"},
    "HS":          {"interval_months": 12,  "free": True,  "hindi": "गलघोंटू"},
    "BQ":          {"interval_months": 12,  "free": True,  "hindi": "लंगड़िया बुखार"},
    "Brucellosis": {"interval_months": 999, "free": True,  "hindi": "ब्रुसेलोसिस"},
    "Theileria":   {"interval_months": 999, "free": False, "hindi": "थिलेरिया"},
}

SYMPTOMS_DB = [
    {"kw":["pet fool","sujan","bloat","gas","pet badh","afara","pait phula","left side"],
     "disease":"Rumen Tympany / Bloat","hindi":"अफारा / पेट फूलना","conf":0.85,"severity":"critical",
     "remedy":"Hing + ajwain paste orally, walk cow 20 mins, massage left flank counterclockwise",
     "medicine":"Bloatnil / Dimethicone / Turpentine 30ml + linseed oil 250ml",
     "dosage":"50-100ml Bloatnil orally; if no relief in 30 min → CALL VET IMMEDIATELY",
     "diet":"Stop green fodder. Dry hay + straw only for 48 hrs. Reduce concentrates.",
     "prevention":"Never give wet grass on empty stomach. Dry fodder first, then green.",
     "nearest_shop":"Pashu Aushadhalay / dairy cooperative","emergency":True,"vaccinations_due":[]},

    {"kw":["bukhar","jwar","tapman","fever","garam","tapna","garmi"],
     "disease":"Fever (FMD / Tick-borne)","hindi":"बुखार","conf":0.80,"severity":"moderate",
     "remedy":"Cool water spray on body, keep in shade, fresh water + green fodder",
     "medicine":"Melonex / Metacin injection OR Paracetamol bolus",
     "dosage":"Paracetamol: 10-15 mg/kg body weight. Melonex: 0.5 mg/kg IM once. VET CONSULT REQUIRED.",
     "diet":"Soft green fodder, rice gruel, jaggery water. Avoid dry/fibrous feed.",
     "prevention":"FMD vaccine every 6 months. Tick control spray monthly.",
     "nearest_shop":"Govt PHC Vet Center","emergency":True,"vaccinations_due":["FMD","HS"]},

    {"kw":["doodh kam","milk less","udder hard","thick milk","gaay ka doodh","than se kam","mastitis","than mein","sujan than"],
     "disease":"Subclinical / Clinical Mastitis","hindi":"थनैला रोग","conf":0.88,"severity":"moderate",
     "remedy":"Warm water udder wash 3x/day, sarson tel gentle massage, haldi+ajwain water 500ml",
     "medicine":"Mastilep ointment (intramammary) OR Penicillin-Streptomycin injection",
     "dosage":"Intramammary tube after each milking × 5 days. Penicillin: 5ml IM 2x/day × 5 days.",
     "diet":"Reduce concentrate by 50%. Increase green fodder. Fresh water always.",
     "prevention":"Milk 3x/day. Teat dip in iodine after milking. Clean udder before milking.",
     "nearest_shop":"Krishi Seva Kendra / Veterinary shop","emergency":False,"vaccinations_due":[]},

    {"kw":["ghav","wound","skin lesion","tick","khal","suji","khujli","kilni","daane","rashes","chamdi"],
     "disease":"Skin Infection / Ectoparasites","hindi":"चर्म रोग / खुजली","conf":0.82,"severity":"mild",
     "remedy":"Neem oil spray, clean wound with Dettol water (1:20), ash bath weekly",
     "medicine":"Ivermectin injection + Butox/Ectomin acaricide spray",
     "dosage":"Ivermectin 0.2 mg/kg SC once. Butox: 1ml per 1L water, spray 2x/week.",
     "diet":"Balanced ration with mineral mixture. Vitamin A and zinc supplementation.",
     "prevention":"Weekly neem bath. Monthly tick powder dusting. Clean housing daily.",
     "nearest_shop":"Local Pashu Kendra / Veterinary pharmacy","emergency":False,"vaccinations_due":[]},

    {"kw":["khansi","cough","nasal discharge","naak se paani","mucus","khaans","saans","respiratory"],
     "disease":"Respiratory Infection / Pneumonia","hindi":"श्वसन रोग / निमोनिया","conf":0.78,"severity":"moderate",
     "remedy":"Keep in dry warm ventilated shelter. Steam inhalation with eucalyptus oil.",
     "medicine":"Oxytetracycline injection OR Enrofloxacin (vet prescribed)",
     "dosage":"Oxytetracycline: 10 mg/kg IM once daily × 5 days. Always vet-supervised.",
     "diet":"Warm water, soft green fodder, jaggery + ginger decoction. Avoid cold water.",
     "prevention":"HS + BQ vaccine annually. Avoid damp/cold housing. Good ventilation.",
     "nearest_shop":"Govt Veterinary dispensary","emergency":False,"vaccinations_due":["HS","BQ"]},

    {"kw":["khurpaka","fmd","foot mouth","muh mein chhale","khur mein ghav","mukhpaka","liblib","chhale"],
     "disease":"Foot and Mouth Disease (FMD)","hindi":"खुरपका-मुँहपका रोग","conf":0.91,"severity":"critical",
     "remedy":"Isolate animal immediately! Wash mouth with KMnO4 solution. Soak hooves in neem water.",
     "medicine":"Borax 5% mouth wash. Report to government vet — FMD is notifiable!",
     "dosage":"Supportive care only. Vet will prescribe. No antibiotics without vet.",
     "diet":"Soft chewable feed only. Rice gruel, cooked vegetables. Avoid dry grass.",
     "prevention":"FMD vaccine every 6 months (FREE at PHC). Isolate new animals 14 days.",
     "nearest_shop":"GOVT PHC — free FMD treatment","emergency":True,"vaccinations_due":["FMD"],
     "is_contagious":True},

    {"kw":["dast","loose motion","diarrhea","patlaa","patla gobar","pait kharab","khoon gobar"],
     "disease":"Diarrhea / Gastroenteritis","hindi":"दस्त / पतला गोबर","conf":0.84,"severity":"moderate",
     "remedy":"ORS: 1L warm water + 1 tsp salt + 4 tsp sugar. Rice starch. Bael leaf decoction.",
     "medicine":"Electral / ORS powder. Sulfaguanidine tablet. Metronidazole (vet prescribed).",
     "dosage":"ORS: 2-4 liters/day. Sulfaguanidine: 1 tablet per 10kg BW twice daily.",
     "diet":"Stop green fodder 24hrs. Hay + ORS only. Reintroduce green fodder after 2 days.",
     "prevention":"Clean water + fresh fodder only. Deworm every 6 months.",
     "nearest_shop":"Any medical shop (ORS). Vet shop (Sulfaguanidine).","emergency":False,"vaccinations_due":[]},

    {"kw":["khana band","not eating","appetite loss","khana nahi","kamzori","weakness","anorexia"],
     "disease":"Anorexia / General Weakness","hindi":"खाना न खाना / कमजोरी","conf":0.65,"severity":"moderate",
     "remedy":"Ginger + garlic + jaggery bolus. Force-feed ORS if dehydrated. Vitamin B complex injection.",
     "medicine":"Vitamin B12 injection + Liver tonic (Hematon/Ferotone)",
     "dosage":"B12: 1ml IM daily × 3 days. Liver tonic: 50ml orally twice daily.",
     "diet":"High-energy: jaggery, crushed maize, mustard oil. Green fodder when appetite returns.",
     "prevention":"Regular deworming. Mineral mixture 50g/day. Balanced ration.",
     "nearest_shop":"Veterinary pharmacy or Krishi Seva Kendra","emergency":False,"vaccinations_due":[]},
]


def _normalize(text: str) -> str:
    t = text.lower()
    for canonical, variants in SYNONYMS.items():
        for v in variants:
            if v in t:
                t += " " + canonical
    return t


def _score(text_norm: str, entry: dict) -> float:
    matched = sum(1 for kw in entry["kw"] if kw in text_norm)
    if matched == 0:
        return 0.0
    density = min(matched / max(len(entry["kw"]), 1), 1.0)
    return entry["conf"] * (0.4 + 0.6 * density)


class PashuAI:
    def __init__(self):
        self.whisper_model = None
        self._whisper_ok = None
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        try:
            import whisper  # type: ignore
            logger.info("Loading Whisper (voice)…")
            self.whisper_model = whisper.load_model("base")
            self._whisper_ok = True
            logger.info("Whisper loaded")
        except ImportError:
            self._whisper_ok = False
            logger.warning("openai-whisper not installed — voice disabled")
        except Exception as e:
            self._whisper_ok = False
            logger.error("Whisper load failed: %s", e)
        self.loaded = True
        logger.info("PashuMitra AI engine ready (voice=%s)", self._whisper_ok)

    def transcribe_voice(self, audio_bytes: bytes) -> str:
        if not self._whisper_ok or not audio_bytes or self.whisper_model is None:
            return ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_bytes)
                fname = f.name
            result = self.whisper_model.transcribe(fname, language="hi", fp16=False)
            text = result.get("text", "")
            return text.strip() if isinstance(text, str) else ""
        except Exception as e:
            logger.error("Voice error: %s", e)
            return ""

    def detect_from_photo(self, image_bytes: bytes) -> Dict[str, Any]:
        try:
            from PIL import Image  # type: ignore
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            if img.size[0] < 150 or img.size[1] < 150:
                return self._fallback("Image too small/blurry")
        except Exception as e:
            return self._fallback(f"Cannot read image: {e}")
        result = self._find_best("doodh kam ghav sujan")
        result["type"] = "image"
        result["note"] = "Phase 1 mock — Phase 2 uses ViT model"
        return result

    def check_symptoms(self, text: str) -> Dict[str, Any]:
        r = self._find_best(text)
        r["type"] = "text"
        return r

    def _find_best(self, text: str) -> Dict[str, Any]:
        norm = _normalize(text)
        scored = [(s, e) for e in SYMPTOMS_DB if (s := _score(norm, e)) > 0]
        if not scored:
            return self._fallback(text)
        scored.sort(key=lambda x: x[0], reverse=True)
        best_s, best = scored[0]
        differential = [
            {"disease": e["disease"], "hindi": e["hindi"], "probability": f"{s:.0%}"}
            for s, e in scored[1:3] if s >= best_s * 0.7
        ]
        return {
            "disease": best["disease"], "hindi": best["hindi"],
            "confidence": round(min(best_s, 0.95), 2), "severity": best["severity"],
            "home_remedy": best["remedy"], "medicine": best["medicine"],
            "dosage": best["dosage"], "diet_advice": best["diet"],
            "prevention": best["prevention"], "nearest_shop": best["nearest_shop"],
            "emergency": best.get("emergency", False),
            "is_contagious": best.get("is_contagious", False),
            "vaccinations_due": best.get("vaccinations_due", []),
            "differential": differential,
            "vaccination_schedule": {k: v for k, v in VACCINATION_SCHEDULE.items()
                                     if k in best.get("vaccinations_due", [])},
        }

    def generate_response(self, text: str, media_type: Optional[str] = None, media_bytes: Optional[bytes] = None) -> Dict[str, Any]:
        if media_type == "image" and media_bytes:
            return self.detect_from_photo(media_bytes)
        return self.check_symptoms(text or "")

    def _fallback(self, msg: str) -> Dict[str, Any]:
        return {
            "disease": "Symptoms Unclear", "hindi": "लक्षण अस्पष्ट",
            "confidence": 0.0, "severity": "unknown",
            "home_remedy": "Ensure clean water, balanced feed, monitor 24 hrs",
            "medicine": "None yet — describe more symptoms or send photo",
            "dosage": "N/A", "diet_advice": "Normal balanced ration. Fresh water always.",
            "prevention": "Regular deworming + vaccination.",
            "nearest_shop": "Check local dairy cooperative",
            "emergency": False, "is_contagious": False,
            "vaccinations_due": [], "differential": [], "vaccination_schedule": {},
            "type": "fallback", "note": f"Could not identify: '{str(msg)[:80]}'",
        }


ai_engine = PashuAI()

"""
Pydantic models for all API requests and responses.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import date


# ── Auth Models ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""
    ftp_override: Optional[int] = 0


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    email: str


class UserProfile(BaseModel):
    user_id: int
    email: str
    name: str
    ftp_override: int
    garmin_connected: bool


# ── Request Models ──────────────────────────────────────────────────────────

class CheckinRequest(BaseModel):
    date: str                  # YYYY-MM-DD
    schlaf: float              # Sleep quality 1-10
    stress: float              # Stress level 1-10
    energie: float             # Energy 1-10
    load_gestern: float        # Yesterday's load 1-10
    muskeln: float             # Muscle soreness 1-10
    ernahrung: float           # Nutrition 1-10
    mental: float              # Mental state 1-10
    gesundheit: float          # Health 1-10


class MatrixRequest(BaseModel):
    date: str                  # YYYY-MM-DD
    rpe: float                 # Hardness 1-10
    feel: float                # Suffering 1-10


class CoachRequest(BaseModel):
    message: str               # User's question or button action
    tp_context: Optional[str] = None   # Optional TrainingPeaks text context


# ── Response Models ──────────────────────────────────────────────────────────

class HRVStatus(BaseModel):
    status: str                # green / yellow / red / unknown
    color: str
    current: float
    baseline: float
    ratio: Optional[float] = None


class CombinedStatus(BaseModel):
    label: str
    color: str
    score: float
    components: dict


class DashboardResponse(BaseModel):
    ctl: float
    atl: float
    tsb: float
    ftp: float
    weekly_load: float
    hrv: HRVStatus
    status: Optional[CombinedStatus] = None
    latest_sleep: Optional[float] = None
    latest_rhr: Optional[float] = None
    latest_vo2max: Optional[float] = None


class ActivityItem(BaseModel):
    date: str
    name: str
    tss: Optional[float] = None
    norm_power: Optional[float] = None
    avg_hr: Optional[float] = None
    distance: Optional[float] = None
    cadence: Optional[float] = None


class SleepPoint(BaseModel):
    date: str
    score: float


class StepsPoint(BaseModel):
    date: str
    steps: int


class PMCPoint(BaseModel):
    date: str
    ctl: float
    atl: float
    tsb: float


class TrendsResponse(BaseModel):
    pmc: list[PMCPoint]
    vo2max: list[dict]
    ftp: float
    ftp_target: int
    training_distribution: dict    # zone -> percentage


class CheckinToday(BaseModel):
    exists: bool
    date: Optional[str] = None
    schlaf: Optional[float] = None
    stress: Optional[float] = None
    energie: Optional[float] = None
    load_gestern: Optional[float] = None
    muskeln: Optional[float] = None
    ernahrung: Optional[float] = None
    mental: Optional[float] = None
    gesundheit: Optional[float] = None
    rpe: Optional[float] = None
    feel: Optional[float] = None
    readiness_score: Optional[float] = None
    readiness_label: Optional[str] = None


class CoachResponse(BaseModel):
    briefing: str
    xml: Optional[str] = None
    xml_valid: bool = False
    xml_message: Optional[str] = None

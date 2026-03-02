"""
Skywalker FastAPI Backend – all REST endpoints for the mobile app.
Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import os
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .models import (
    CheckinRequest, MatrixRequest, CoachRequest,
    DashboardResponse, HRVStatus, CombinedStatus, ActivityItem,
    SleepPoint, StepsPoint, TrendsResponse, PMCPoint,
    CheckinToday, CoachResponse, UserCreate, UserLogin, TokenResponse, UserProfile,
)
from . import calculations as calc
from . import data_manager as dm
from .ai_coach import ask_coach
from .database import create_tables, get_db, User, user_data_path
from .auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, encrypt_garmin_pw, decrypt_garmin_pw,
)

app = FastAPI(title="Skywalker API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    create_tables()


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register", response_model=TokenResponse)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="E-Mail bereits registriert.")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name or "",
        ftp_override=body.ftp_override or 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, email=user.email)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-Mail oder Passwort falsch.")
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, email=user.email)


@app.get("/api/auth/me", response_model=UserProfile)
def get_me(current_user: User = Depends(get_current_user)):
    return UserProfile(
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        ftp_override=current_user.ftp_override,
        garmin_connected=bool(current_user.garmin_email),
    )


@app.post("/api/auth/garmin")
def connect_garmin(
    garmin_email: str,
    garmin_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.garmin_email = garmin_email
    current_user.garmin_password_enc = encrypt_garmin_pw(garmin_password)
    db.commit()
    return {"status": "Garmin-Account verbunden."}


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/api/dashboard", response_model=DashboardResponse)
def get_dashboard(current_user: User = Depends(get_current_user)):
    uid = current_user.id
    df_stats = dm.load_stats(uid)
    df_act = dm.load_activities(uid)

    ftp = current_user.ftp_override or calc.compute_ftp(df_act)
    pmc = calc.compute_ctl_atl_tsb(df_act, days=90)
    latest = pmc.iloc[-1] if not pmc.empty else None
    ctl = round(float(latest["CTL"]), 1) if latest is not None else 0.0
    atl = round(float(latest["ATL"]), 1) if latest is not None else 0.0
    tsb = round(float(latest["TSB"]), 1) if latest is not None else 0.0
    weekly_load = calc.compute_weekly_load(df_act)
    hrv_data = calc.compute_hrv_status(df_stats)
    checkin = dm.get_checkin_today(uid)
    combined = calc.compute_combined_status(hrv_data, tsb, checkin)

    # Latest single values
    latest_sleep = None
    latest_rhr = None
    latest_vo2 = None
    if not df_stats.empty:
        s = df_stats.sort_values("Date", ascending=False).iloc[0]
        latest_sleep = float(s["Sleep Score"]) if "Sleep Score" in s and pd.notna(s["Sleep Score"]) else None
        latest_rhr = float(s["RHR"]) if "RHR" in s and pd.notna(s["RHR"]) else None
        # VO2 Max: letzten vorhandenen Wert nehmen (nicht immer täglich vorhanden)
        if "VO2 Max" in df_stats.columns:
            vo2_series = pd.to_numeric(df_stats["VO2 Max"], errors="coerce").dropna()
            latest_vo2 = float(vo2_series.iloc[-1]) if not vo2_series.empty else None
        else:
            latest_vo2 = None

    return DashboardResponse(
        ctl=ctl,
        atl=atl,
        tsb=tsb,
        ftp=ftp,
        weekly_load=round(weekly_load, 1),
        hrv=HRVStatus(**hrv_data),
        status=CombinedStatus(**combined),
        latest_sleep=latest_sleep,
        latest_rhr=latest_rhr,
        latest_vo2max=latest_vo2,
    )


# ── Activities ───────────────────────────────────────────────────────────────

@app.get("/api/activities", response_model=list[ActivityItem])
def get_activities(limit: int = 20, current_user: User = Depends(get_current_user)):
    df = dm.load_activities(current_user.id)
    if df.empty:
        return []
    recent = df.sort_values("Date", ascending=False).head(limit)
    result = []
    for _, row in recent.iterrows():
        result.append(ActivityItem(
            date=str(row["Date"].date()),
            name=str(row.get("activityName", "—")),
            tss=_safe_float(row.get("activityTrainingLoad")),
            norm_power=_safe_float(row.get("normPower")),
            avg_hr=_safe_float(row.get("averageHR")),
            distance=_safe_float(row.get("distance")),
            cadence=_safe_float(row.get("avgCadence")),
        ))
    return result


# ── Sleep ────────────────────────────────────────────────────────────────────

@app.get("/api/sleep", response_model=list[SleepPoint])
def get_sleep(days: int = 90, current_user: User = Depends(get_current_user)):
    df = dm.load_stats(current_user.id)
    if df.empty or "Sleep Score" not in df.columns:
        return []
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    df = df[df["Date"] >= cutoff].sort_values("Date")
    result = []
    for _, row in df.iterrows():
        val = _safe_float(row.get("Sleep Score"))
        if val is not None and val > 0:
            result.append(SleepPoint(date=str(row["Date"].date()), score=val))
    return result


# ── Steps ────────────────────────────────────────────────────────────────────

@app.get("/api/steps", response_model=list[StepsPoint])
def get_steps(days: int = 30, current_user: User = Depends(get_current_user)):
    df = dm.load_stats(current_user.id)
    if df.empty or "Steps" not in df.columns:
        return []
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    df = df[df["Date"] >= cutoff].sort_values("Date")
    result = []
    for _, row in df.iterrows():
        val = pd.to_numeric(row.get("Steps"), errors="coerce")
        if pd.notna(val) and val > 0:
            result.append(StepsPoint(date=str(row["Date"].date()), steps=int(val)))
    return result


# ── Trends ───────────────────────────────────────────────────────────────────

@app.get("/api/trends", response_model=TrendsResponse)
def get_trends(days: int = 90, current_user: User = Depends(get_current_user)):
    df_stats = dm.load_stats(current_user.id)
    df_act = dm.load_activities(current_user.id)

    ftp = current_user.ftp_override or calc.compute_ftp(df_act)
    pmc = calc.compute_ctl_atl_tsb(df_act, days=days)

    pmc_points = [
        PMCPoint(
            date=str(row["Date"].date()),
            ctl=round(float(row["CTL"]), 1),
            atl=round(float(row["ATL"]), 1),
            tsb=round(float(row["TSB"]), 1),
        )
        for _, row in pmc.iterrows()
    ]

    # VO2 Max history (all time)
    vo2_points = []
    if not df_stats.empty and "VO2 Max" in df_stats.columns:
        vo2_df = df_stats[["Date", "VO2 Max"]].dropna()
        vo2_df = vo2_df[pd.to_numeric(vo2_df["VO2 Max"], errors="coerce") > 0]
        for _, row in vo2_df.iterrows():
            vo2_points.append({
                "date": str(row["Date"].date()),
                "vo2max": float(row["VO2 Max"]),
            })

    dist = calc.compute_training_distribution(df_act, ftp)

    return TrendsResponse(
        pmc=pmc_points,
        vo2max=vo2_points,
        ftp=ftp,
        ftp_target=250,
        training_distribution=dist,
    )


# ── Check-in ─────────────────────────────────────────────────────────────────

@app.get("/api/checkin/today", response_model=CheckinToday)
def get_checkin_today(current_user: User = Depends(get_current_user)):
    data = dm.get_checkin_today(current_user.id)
    if data is None:
        return CheckinToday(exists=False)
    score, label = calc.compute_readiness(data)
    return CheckinToday(exists=True, readiness_score=score, readiness_label=label, **data)


@app.post("/api/checkin")
def post_checkin(body: CheckinRequest, current_user: User = Depends(get_current_user)):
    try:
        dm.save_checkin(body.model_dump(), current_user.id)
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/checkin/matrix")
def post_matrix(body: MatrixRequest, current_user: User = Depends(get_current_user)):
    try:
        dm.save_matrix(body.date, body.rpe, body.feel, current_user.id)
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Coach ─────────────────────────────────────────────────────────────────

@app.post("/api/coach", response_model=CoachResponse)
def post_coach(body: CoachRequest, current_user: User = Depends(get_current_user)):
    df_stats = dm.load_stats(current_user.id)
    df_act = dm.load_activities(current_user.id)

    ftp = current_user.ftp_override or calc.compute_ftp(df_act)
    pmc = calc.compute_ctl_atl_tsb(df_act, days=90)
    latest = pmc.iloc[-1] if not pmc.empty else None
    ctl = float(latest["CTL"]) if latest is not None else 0.0
    atl = float(latest["ATL"]) if latest is not None else 0.0
    tsb = float(latest["TSB"]) if latest is not None else 0.0
    weekly_load = calc.compute_weekly_load(df_act)
    checkin = dm.get_checkin_today(current_user.id)

    try:
        result = ask_coach(
            message=body.message,
            ctl=ctl, atl=atl, tsb=tsb,
            ftp=ftp, weekly_load=weekly_load,
            df_stats=df_stats, df_act=df_act,
            checkin=checkin,
            tp_context=body.tp_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Coach error: {e}")

    return CoachResponse(**result)


# ── Delete Activity ──────────────────────────────────────────────────────────

@app.delete("/api/activities")
def delete_activity(date: str, name: str, current_user: User = Depends(get_current_user)):
    deleted = dm.delete_activity(date, name, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Aktivität nicht gefunden.")
    return {"status": "deleted"}


# ── Upload ───────────────────────────────────────────────────────────────────

@app.post("/api/upload/stats")
async def upload_stats(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    content = await file.read()
    try:
        added = dm.merge_upload(content, "stats", current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "rows_added": added}


@app.post("/api/upload/activities")
async def upload_activities(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    content = await file.read()
    try:
        added = dm.merge_upload(content, "activities", current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "rows_added": added}


# ── Services ─────────────────────────────────────────────────────────────────

@app.get("/api/services/status")
def get_services_status(current_user: User = Depends(get_current_user)):
    return {
        "garmin": {
            "connected": bool(current_user.garmin_email),
            "email": current_user.garmin_email or None,
        },
        "whoop": {
            "connected": False,  # Kommt später
        },
    }


@app.post("/api/services/garmin/connect")
def connect_garmin_service(
    garmin_email: str,
    garmin_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .garmin_sync import connect_garmin
    try:
        result = connect_garmin(current_user.id, garmin_email, garmin_password)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Garmin Login fehlgeschlagen: {e}")
    current_user.garmin_email = garmin_email
    current_user.garmin_password_enc = encrypt_garmin_pw(garmin_password)
    db.commit()
    return {"status": "verbunden", "display_name": result.get("display_name")}


@app.post("/api/services/garmin/sync")
def sync_garmin(current_user: User = Depends(get_current_user)):
    from .garmin_sync import sync_activities, sync_health
    if not current_user.garmin_email:
        raise HTTPException(status_code=400, detail="Garmin nicht verbunden.")
    try:
        acts = sync_activities(current_user.id, days=30)
        health = sync_health(current_user.id, days=7)
        return {"status": "ok", "activities_synced": acts, "health_days_synced": health}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync fehlgeschlagen: {e}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return None

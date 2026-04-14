"""
Skywalker FastAPI Backend – all REST endpoints for the mobile app.
Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import os
import threading
import time
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .models import (
    CheckinRequest, MatrixRequest, CoachRequest,
    DashboardResponse, HRVStatus, CombinedStatus, ActivityItem,
    SleepPoint, StepsPoint, TrendsResponse, PMCPoint,
    CheckinToday, CoachResponse, UserCreate, UserLogin, TokenResponse, UserProfile,
    GoalsRequest, ProfileRequest, WorkoutDownloadRequest,
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

def _sync_days_for_user(user_id: int) -> int:
    """Return 365 if user has little health data, else 30."""
    try:
        df = dm.load_stats(user_id)
        if df.empty or len(df) < 30:
            return 365
    except Exception:
        pass
    return 30


def _daily_sync_loop():
    """Background thread: sync all Garmin users once per day at ~3am."""
    from .garmin_sync import sync_activities, sync_health
    from .database import SessionLocal
    while True:
        # Warte bis 3:00 Uhr nachts
        now = datetime.now()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run.replace(day=next_run.day + 1)
        sleep_secs = (next_run - now).total_seconds()
        time.sleep(sleep_secs)

        # Alle Garmin-User syncen
        try:
            db = SessionLocal()
            users = db.query(User).filter(User.garmin_email.isnot(None)).all()
            db.close()
            for u in users:
                try:
                    days = _sync_days_for_user(u.id)
                    sync_activities(u.id, days=days)
                    sync_health(u.id, days=days)
                except Exception:
                    pass
        except Exception:
            pass


@app.on_event("startup")
def startup():
    create_tables()
    _migrate_db()
    threading.Thread(target=_daily_sync_loop, daemon=True).start()


def _migrate_db():
    """Add new columns to existing tables if they don't exist yet."""
    from .database import engine
    with engine.connect() as conn:
        existing = [row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(users)")
        )]
        migrations = [
            ("ftp_target",  "ALTER TABLE users ADD COLUMN ftp_target INTEGER DEFAULT 0"),
            ("weight_kg",   "ALTER TABLE users ADD COLUMN weight_kg REAL DEFAULT 0.0"),
            ("height_cm",   "ALTER TABLE users ADD COLUMN height_cm INTEGER DEFAULT 0"),
            ("gender",          "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''"),
            ("training_goal",   "ALTER TABLE users ADD COLUMN training_goal TEXT DEFAULT ''"),
            ("event_name",      "ALTER TABLE users ADD COLUMN event_name TEXT DEFAULT ''"),
            ("event_date",          "ALTER TABLE users ADD COLUMN event_date TEXT DEFAULT ''"),
            ("training_frequency",  "ALTER TABLE users ADD COLUMN training_frequency TEXT DEFAULT ''"),
            ("training_days",           "ALTER TABLE users ADD COLUMN training_days TEXT DEFAULT ''"),
        ("strava_access_token",     "ALTER TABLE users ADD COLUMN strava_access_token TEXT"),
        ("strava_refresh_token",    "ALTER TABLE users ADD COLUMN strava_refresh_token TEXT"),
        ("strava_expires_at",       "ALTER TABLE users ADD COLUMN strava_expires_at INTEGER"),
        ("strava_athlete_id",       "ALTER TABLE users ADD COLUMN strava_athlete_id INTEGER"),
        ("intervals_athlete_id",    "ALTER TABLE users ADD COLUMN intervals_athlete_id TEXT DEFAULT ''"),
        ]
        for col, sql in migrations:
            if col not in existing:
                conn.execute(__import__("sqlalchemy").text(sql))
        conn.commit()


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
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, email=user.email, ftp_target=user.ftp_target or 0)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-Mail oder Passwort falsch.")
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, email=user.email, ftp_target=user.ftp_target or 0)


@app.get("/api/auth/me", response_model=UserProfile)
def get_me(current_user: User = Depends(get_current_user)):
    df_act = dm.load_activities(current_user.id)
    ftp_current = current_user.ftp_override or calc.compute_ftp(df_act)
    return UserProfile(
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        ftp_override=current_user.ftp_override,
        ftp_target=current_user.ftp_target or 0,
        ftp_current=ftp_current,
        training_goal=current_user.training_goal or "",
        event_name=current_user.event_name or "",
        event_date=current_user.event_date or "",
        training_frequency=current_user.training_frequency or "",
        training_days=current_user.training_days or "",
        weight_kg=current_user.weight_kg or 0.0,
        height_cm=current_user.height_cm or 0,
        gender=current_user.gender or "",
        garmin_connected=bool(current_user.garmin_email),
        strava_connected=bool(current_user.strava_access_token),
        strava_athlete_id=current_user.strava_athlete_id,
        intervals_athlete_id=current_user.intervals_athlete_id or "",
    )


@app.patch("/api/auth/goals")
def update_goals(body: GoalsRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.ftp_target = body.ftp_target
    db.commit()
    return {"status": "saved", "ftp_target": body.ftp_target}


@app.patch("/api/auth/profile")
def update_profile(body: ProfileRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.ftp_target     is not None: current_user.ftp_target     = body.ftp_target
    if body.ftp_override   is not None: current_user.ftp_override   = body.ftp_override
    if body.training_goal  is not None: current_user.training_goal  = body.training_goal
    if body.event_name          is not None: current_user.event_name          = body.event_name
    if body.event_date          is not None: current_user.event_date          = body.event_date
    if body.training_frequency  is not None: current_user.training_frequency  = body.training_frequency
    if body.training_days       is not None: current_user.training_days       = body.training_days
    if body.weight_kg      is not None: current_user.weight_kg      = body.weight_kg
    if body.height_cm      is not None: current_user.height_cm      = body.height_cm
    if body.gender              is not None: current_user.gender              = body.gender
    if body.intervals_athlete_id is not None: current_user.intervals_athlete_id = body.intervals_athlete_id
    db.commit()
    return {"status": "saved"}


# ── intervals.icu ─────────────────────────────────────────────────────────────

@app.get("/api/intervals/plan")
def get_intervals_plan(current_user: User = Depends(get_current_user)):
    from .intervals_sync import get_planned_workouts
    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = current_user.intervals_athlete_id or ""
    if not api_key or not athlete_id:
        raise HTTPException(status_code=400, detail="intervals.icu nicht konfiguriert.")
    try:
        workouts = get_planned_workouts(athlete_id, api_key, days=7)
        return {"workouts": workouts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"intervals.icu Fehler: {e}")


# ── Strava OAuth ─────────────────────────────────────────────────────────────

@app.get("/api/strava/auth")
def strava_auth(current_user: User = Depends(get_current_user)):
    from .strava_sync import get_auth_url
    from .auth import create_access_token
    state = create_access_token(current_user.id, current_user.email)
    return {"url": get_auth_url(state)}


@app.get("/api/strava/callback")
def strava_callback(code: str, state: str, db: Session = Depends(get_db)):
    from .strava_sync import exchange_code, FRONTEND_URL
    from .auth import decode_token
    try:
        payload = decode_token(state)
        user_id = payload["user_id"]
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger State-Token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    data = exchange_code(code)
    user.strava_access_token  = data["access_token"]
    user.strava_refresh_token = data["refresh_token"]
    user.strava_expires_at    = data["expires_at"]
    user.strava_athlete_id    = data.get("athlete", {}).get("id")
    db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{FRONTEND_URL}/?strava=connected")


@app.delete("/api/strava/disconnect")
def strava_disconnect(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.strava_access_token  = None
    current_user.strava_refresh_token = None
    current_user.strava_expires_at    = None
    current_user.strava_athlete_id    = None
    db.commit()
    return {"status": "Strava getrennt"}


@app.post("/api/strava/sync")
def strava_sync_manual(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Manually backfill last 30 days of Strava activities."""
    if not current_user.strava_access_token:
        raise HTTPException(status_code=400, detail="Strava nicht verbunden")
    from .strava_sync import get_valid_token, fetch_activities, activity_to_row, save_activity_to_csv
    import time as _time
    token = get_valid_token(current_user, db)
    after_ts = int(_time.time()) - 30 * 86400
    activities = fetch_activities(token, after_ts=after_ts, per_page=50)
    ftp = current_user.ftp_override or 230
    count = 0
    for act in activities:
        row = activity_to_row(act, ftp=ftp)
        if row:
            save_activity_to_csv(row, current_user.id)
            count += 1
    return {"status": "ok", "imported": count}


# ── Strava Webhook ────────────────────────────────────────────────────────────

@app.get("/api/webhook/strava")
def strava_webhook_verify(
    hub_mode:         str = Query(None, alias="hub.mode"),
    hub_challenge:    str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Strava webhook verification handshake."""
    from .strava_sync import STRAVA_WEBHOOK_VERIFY_TOKEN
    if hub_verify_token == STRAVA_WEBHOOK_VERIFY_TOKEN and hub_mode == "subscribe":
        return {"hub.challenge": hub_challenge}
    raise HTTPException(status_code=403, detail="Verify token mismatch")


@app.post("/api/webhook/strava")
async def strava_webhook_event(request: Request, db: Session = Depends(get_db)):
    """Receive Strava activity events and import new cycling activities."""
    from .strava_sync import get_valid_token, fetch_activity, activity_to_row, save_activity_to_csv
    body = await request.json()
    # Only handle new/updated activities
    if body.get("object_type") != "activity" or body.get("aspect_type") not in ("create", "update"):
        return {"status": "ignored"}
    athlete_id = body.get("owner_id")
    activity_id = body.get("object_id")
    user = db.query(User).filter(User.strava_athlete_id == athlete_id).first()
    if not user:
        return {"status": "unknown_athlete"}
    try:
        token = get_valid_token(user, db)
        act = fetch_activity(token, activity_id)
        ftp = user.ftp_override or 230
        row = activity_to_row(act, ftp=ftp)
        if row:
            save_activity_to_csv(row, user.id)
            print(f"[STRAVA] imported activity {activity_id} for user {user.id}", flush=True)
        return {"status": "ok"}
    except Exception as e:
        print(f"[STRAVA] error processing activity {activity_id}: {e}", flush=True)
        return {"status": "error", "detail": str(e)}


@app.get("/api/strava/webhook/setup")
def strava_webhook_setup(current_user: User = Depends(get_current_user)):
    """One-time: register Strava webhook subscription."""
    from .strava_sync import register_webhook, get_webhook_subscription
    existing = get_webhook_subscription()
    if existing:
        return {"status": "already_registered", "subscription": existing}
    result = register_webhook()
    return {"status": "registered", "result": result}


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

    # Latest single values – letzten vorhandenen Wert nehmen (nicht immer täglich vorhanden)
    latest_sleep = None
    latest_rhr = None
    latest_vo2 = None
    if not df_stats.empty:
        df_sorted = df_stats.sort_values("Date")
        if "Sleep Score" in df_sorted.columns:
            s = pd.to_numeric(df_sorted["Sleep Score"], errors="coerce").dropna()
            latest_sleep = float(s.iloc[-1]) if not s.empty else None
        if "RHR" in df_sorted.columns:
            r = pd.to_numeric(df_sorted["RHR"], errors="coerce").dropna()
            latest_rhr = float(r.iloc[-1]) if not r.empty else None
        if "VO2 Max" in df_sorted.columns:
            v = pd.to_numeric(df_sorted["VO2 Max"], errors="coerce").dropna()
            latest_vo2 = float(v.iloc[-1]) if not v.empty else None

    # Fallback: VO2 Max aus Aktivitäten (Garmin schreibt es oft dort rein)
    if latest_vo2 is None and not df_act.empty and "vo2Max" in df_act.columns:
        act_vo2 = pd.to_numeric(df_act.sort_values("Date")["vo2Max"], errors="coerce").dropna()
        if not act_vo2.empty:
            latest_vo2 = float(act_vo2.iloc[-1])

    return DashboardResponse(
        ctl=ctl,
        atl=atl,
        tsb=tsb,
        ftp=ftp,
        ftp_target=current_user.ftp_target or 250,
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
        ftp_target=current_user.ftp_target or 250,
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


@app.get("/api/checkin/debug")
def debug_checkin(current_user: User = Depends(get_current_user)):
    """Debug: returns user ID, checkin file path, and raw recent checkin data."""
    from .database import user_data_path
    import os
    checkin_path = os.path.join(user_data_path(current_user.id), "daily_checkin.csv")
    raw = ""
    if os.path.exists(checkin_path):
        with open(checkin_path) as f:
            raw = f.read()
    recent = dm.get_checkin_recent(current_user.id)
    today = dm.get_checkin_today(current_user.id)
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "checkin_path": checkin_path,
        "file_exists": os.path.exists(checkin_path),
        "raw_csv": raw,
        "get_checkin_recent": recent,
        "get_checkin_today": today,
    }


@app.get("/api/checkin/matrix")
def get_matrix(current_user: User = Depends(get_current_user)):
    df = dm.load_checkins(current_user.id)
    if df.empty or "RPE" not in df.columns:
        return []
    df = df.dropna(subset=["RPE"])
    result = []
    for _, r in df.iterrows():
        rpe  = r.get("RPE")
        feel = r.get("Feel")
        if pd.isna(rpe):
            continue
        result.append({
            "date": r["Date"].strftime("%Y-%m-%d") if hasattr(r["Date"], "strftime") else str(r["Date"]),
            "rpe":  float(rpe),
            "feel": float(feel) if not pd.isna(feel) else None,
        })
    return result


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
    checkin = dm.get_checkin_recent(current_user.id)
    print(f"[COACH] user_id={current_user.id} email={current_user.email} checkin={'FOUND: '+checkin.get('date','?') if checkin else 'NONE'}", flush=True)

    # intervals.icu Wochenplan als Coach-Kontext
    intervals_context = None
    if current_user.intervals_athlete_id:
        try:
            from .intervals_sync import get_weekly_plan_text
            api_key = os.getenv("INTERVALS_API_KEY", "")
            if api_key:
                intervals_context = get_weekly_plan_text(current_user.intervals_athlete_id, api_key)
        except Exception:
            pass

    # tp_context: intervals hat Vorrang, sonst manueller tp_context
    combined_context = intervals_context or body.tp_context

    try:
        result = ask_coach(
            message=body.message,
            ctl=ctl, atl=atl, tsb=tsb,
            ftp=ftp, weekly_load=weekly_load,
            df_stats=df_stats, df_act=df_act,
            checkin=checkin,
            tp_context=combined_context,
            training_goal=current_user.training_goal or "",
            event_name=current_user.event_name or "",
            event_date=current_user.event_date or "",
            training_frequency=current_user.training_frequency or "",
            training_days=current_user.training_days or "",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Coach error: {e}")

    return CoachResponse(**result)


# ── Workout Downloads ────────────────────────────────────────────────────────

from fastapi.responses import Response as FastAPIResponse
from .workout_converter import zwo_to_erg, zwo_to_tcx, zwo_to_workout_card

@app.post("/api/workout/download/erg")
def download_erg(body: WorkoutDownloadRequest, current_user: User = Depends(get_current_user)):
    df_act = dm.load_activities(current_user.id)
    ftp = body.ftp or current_user.ftp_override or calc.compute_ftp(df_act)
    content = zwo_to_erg(body.xml, ftp=int(ftp))
    return FastAPIResponse(content=content, media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=skywalker_workout.erg"})

@app.post("/api/workout/download/tcx")
def download_tcx(body: WorkoutDownloadRequest, current_user: User = Depends(get_current_user)):
    df_act = dm.load_activities(current_user.id)
    ftp = body.ftp or current_user.ftp_override or calc.compute_ftp(df_act)
    content = zwo_to_tcx(body.xml, ftp=int(ftp))
    return FastAPIResponse(content=content, media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=skywalker_workout.tcx"})

@app.post("/api/workout/download/card")
def download_card(body: WorkoutDownloadRequest, current_user: User = Depends(get_current_user)):
    df_act = dm.load_activities(current_user.id)
    ftp = body.ftp or current_user.ftp_override or calc.compute_ftp(df_act)
    content = zwo_to_workout_card(body.xml, ftp=int(ftp))
    return FastAPIResponse(content=content, media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=skywalker_workout_card.txt"})


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


def _background_full_sync(user_id: int):
    """Sync 365 days of Garmin history in background after first connect."""
    import threading
    from .garmin_sync import sync_activities, sync_health
    def run():
        try:
            sync_activities(user_id, days=365)
            sync_health(user_id, days=365)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


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
    if result.get("needs_mfa"):
        return {"needs_mfa": True}
    current_user.garmin_email = garmin_email
    current_user.garmin_password_enc = encrypt_garmin_pw(garmin_password)
    db.commit()
    _background_full_sync(current_user.id)
    return {"status": "verbunden", "display_name": result.get("display_name")}


@app.post("/api/services/garmin/mfa")
def garmin_mfa_service(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .garmin_sync import connect_garmin_mfa
    try:
        result = connect_garmin_mfa(current_user.id, code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"MFA fehlgeschlagen: {e}")
    current_user.garmin_email = result["email"]
    current_user.garmin_password_enc = encrypt_garmin_pw(result["password"])
    db.commit()
    _background_full_sync(current_user.id)
    return {"status": "verbunden", "display_name": result.get("display_name")}


@app.post("/api/services/garmin/sync")
def sync_garmin(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .garmin_sync import sync_activities, sync_health, connect_garmin
    if not current_user.garmin_email:
        raise HTTPException(status_code=400, detail="Garmin nicht verbunden.")

    def _do_sync():
        acts = sync_activities(current_user.id, days=30)
        health = sync_health(current_user.id, days=30)
        return acts, health

    try:
        acts, health = _do_sync()
    except Exception as e:
        err = str(e).lower()
        if "authenticated" in err or "invalidtoken" in err or "invalid" in str(type(e).__name__).lower():
            raise HTTPException(status_code=503, detail="Garmin-Verbindung abgelaufen. Bitte unter Einstellungen → Garmin neu verbinden.")
        if "429" in err or "rate limit" in err:
            raise HTTPException(status_code=503, detail="Garmin blockiert aktuell Anfragen (Rate Limit). Bitte später nochmal versuchen.")
        raise HTTPException(status_code=500, detail=f"Sync fehlgeschlagen: {e}")

    return {"status": "ok", "activities_synced": acts, "health_days_synced": health}




# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return None

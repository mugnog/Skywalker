"""
SQLite database setup – stores user accounts only.
Training data stays in per-user CSV directories.
"""
import os
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SAVE_PATH = os.getenv("SAVE_PATH", os.path.expanduser("~/Documents/AI_Fitness-main"))
DB_PATH = os.path.join(SAVE_PATH, "skywalker_users.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, default="")
    garmin_email = Column(String, default="")
    garmin_password_enc = Column(String, default="")   # Fernet encrypted
    ftp_override = Column(Integer, default=0)           # 0 = auto-berechnen
    ftp_target = Column(Integer, default=0)             # 0 = noch nicht gesetzt
    training_goal = Column(String, default="")          # ftp / endurance / weight / race / health
    event_name = Column(String, default="")             # z.B. "Alpenbrevet"
    event_date = Column(String, default="")             # ISO: YYYY-MM-DD
    training_frequency = Column(String, default="")     # low / mid / high
    training_days = Column(String, default="")           # e.g. "mon,wed,fri,sat,sun"
    strava_access_token  = Column(String, default=None)
    strava_refresh_token = Column(String, default=None)
    strava_expires_at    = Column(Integer, default=None)  # Unix timestamp
    strava_athlete_id    = Column(Integer, default=None)
    weight_kg = Column(Float, default=0.0)
    height_cm = Column(Integer, default=0)
    gender = Column(String, default="")                 # male / female / other
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Datenpfad pro User
def user_data_path(user_id: int) -> str:
    path = os.path.join(SAVE_PATH, "users", str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

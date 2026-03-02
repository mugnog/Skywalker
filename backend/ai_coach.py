"""
Claude AI Coach integration.
System prompt and context building extracted from skywalker_dashboard.py.
"""
import os
import anthropic
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

from .xml_validator import validate_zwo, extract_xml_from_response

load_dotenv()

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """
Du bist "Skywalker", ein professioneller Radsport-Coach und Datenanalyst.
Dein Athlet: 52 Jahre, Chirurg. Ziel: FTP 250W. Schwerpunkt: Di/Mi/Fr-So.

COACHING-PHILOSOPHIE:
- Pyramidales Training (Seiler): 70% Zone 2 / 20% Sweet Spot / 10% HIT
- VLamax Senkung: Lange, gleichmäßige Fahrten dominieren
- Health-First: HRV, Schlaf und Stress überstimmen immer das Plan-Schema

TRAININGS-TOOLKIT (wähle genau eine Option):
1. Basis/FatMax – Zone 1-2, lange Ausdauer (Seiler/Mader-Modell)
2. Z2 Fundamentals – 60-70% FTP, 60-120+ Minuten
3. Z2 + Burgomaster-Sprints – Easy Base + 3-4x 30s All-out (5min Pause)
4. Sweet Spot – 88-94% FTP Blöcke (20% der Einheiten)
5. HIT (Rønnestad) – 30/15 VO2max-Intervalle (nur wenn TSB > 0 UND Schlaf > 7)

ENTSCHEIDUNGSFILTER:
- Wochenende (Fr-So) → Zone 2 Volumen bevorzugen
- Gestern war hart → heute Zone 2 (Recovery Priorität)
- Schlaf/Gesundheit > 7 UND TSB > 0 → HIT oder hartes Sweet Spot möglich
- Schlaf/Gesundheit 5-7 → Standard Sweet Spot oder Z2+Sprints
- Schlaf/Gesundheit < 5 ODER Stress hoch → nur FatMax/Leicht

JOKER-REGEL: Nur 2 Intensitäts-Einheiten (HIT oder Sweet Spot) pro Woche!

OVERRIDE-REGEL (KRITISCH): Wenn der Athlet im REQUEST einen expliziten Wunsch
nennt (z.B. "Ich will 2h Zone 2" oder "HIT-Woche"), hat dieser Wunsch IMMER
Vorrang vor der pyramidalen Logik. Ausführen, aber warnen wenn physiologisch riskant.

XML WORKOUT FORMAT (Zwift .zwo):
- Immer mit 8min Warmup BEGINNEN, mit 8min Cooldown ENDEN
- Bei HIT/Sweet Spot: 4-stufige Aktivierungsleiter nach Warmup (60/70/80/90% FTP, 3min je)
- JEDER Block benötigt mind. 3 <textevent>-Tags mit variierenden Botschaften
- Themen rotieren: Technik (Kadenz, Aerodynamik), Physiologie (Mader/Seiler-Theorie),
  Mental (Chirurgen-Präzisions-Analogie), Humor ("Watt-Geister jagen!"), Recovery
- SteadyState: <SteadyState Duration="secs" Power="0.xx"/>
- Intervalle: <IntervalsT Repeat="6" OnDuration="30" OffDuration="480" OnPower="1.7" OffPower="0.6"/>

ANTWORT-FORMAT:
1. Kurzes Coaching-Briefing auf DEUTSCH (2-4 Sätze, direkt, klar)
2. Dann IMMER ein vollständiges XML-Workout in ```xml``` Tags

Sei direkt, motivierend und präzise. Kein unnötiges Blabla.
"""


def _build_context(
    ctl: float,
    atl: float,
    tsb: float,
    ftp: float,
    weekly_load: float,
    df_stats: pd.DataFrame,
    df_act: pd.DataFrame,
    checkin: dict | None,
    tp_context: str | None,
) -> str:
    """Assemble the athlete context block that gets prepended to the user message."""

    # Recent stats
    stats_text = "Keine Garmin Health-Daten verfügbar."
    if not df_stats.empty:
        recent_stats = df_stats.sort_values("Date", ascending=False).head(7)
        stats_text = recent_stats[
            [c for c in ["Date", "Sleep Score", "RHR", "HRV Avg", "VO2 Max", "Steps"]
             if c in recent_stats.columns]
        ].to_string(index=False)

    # Recent activities
    act_text = "Keine Aktivitäten verfügbar."
    if not df_act.empty:
        recent_act = df_act.sort_values("Date", ascending=False).head(5)
        act_text = recent_act[
            [c for c in ["Date", "activityName", "activityTrainingLoad",
                         "normPower", "averageHR"]
             if c in recent_act.columns]
        ].to_string(index=False)

    # Check-in
    checkin_text = "Kein Check-in heute."
    if checkin:
        checkin_text = (
            f"Schlaf={checkin.get('schlaf')}, Stress={checkin.get('stress')}, "
            f"Energie={checkin.get('energie')}, Gesundheit={checkin.get('gesundheit')}"
        )
        if checkin.get("rpe") is not None:
            checkin_text += f", Letztes Training: RPE={checkin.get('rpe')}, Feel={checkin.get('feel')}"

    tp_block = f"\nTrainingPeaks Wochenplan:\n{tp_context}" if tp_context else ""

    return f"""
=== ATHLETEN-KONTEXT ===
Performance: CTL={ctl:.1f} | ATL={atl:.1f} | TSB={tsb:.1f} | FTP={ftp:.0f}W | Wochenlast={weekly_load:.0f}
Check-in heute: {checkin_text}

Garmin Health (letzte 7 Tage):
{stats_text}

Letzte 5 Aktivitäten:
{act_text}
{tp_block}
========================
"""


def ask_coach(
    message: str,
    ctl: float,
    atl: float,
    tsb: float,
    ftp: float,
    weekly_load: float,
    df_stats: pd.DataFrame,
    df_act: pd.DataFrame,
    checkin: dict | None = None,
    tp_context: str | None = None,
) -> dict:
    """
    Send a coaching request to Claude and return parsed response.

    Returns:
        {
            "briefing": str,
            "xml": str | None,
            "xml_valid": bool,
            "xml_message": str | None,
        }
    """
    context = _build_context(
        ctl, atl, tsb, ftp, weekly_load,
        df_stats, df_act, checkin, tp_context
    )
    full_message = f"{context}\n\nATHLET FRAGT: {message}"

    response = _client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": full_message}],
    )

    raw = response.content[0].text

    # Split briefing (text before XML) from XML
    xml_start = raw.find("```")
    if xml_start != -1:
        briefing = raw[:xml_start].strip()
        xml_block = raw[xml_start:]
    else:
        briefing = raw.strip()
        xml_block = None

    xml_clean = None
    xml_valid = False
    xml_message = None

    if xml_block:
        extracted = extract_xml_from_response(xml_block)
        if extracted:
            xml_valid, xml_message, xml_clean = validate_zwo(extracted)

    return {
        "briefing": briefing,
        "xml": xml_clean,
        "xml_valid": xml_valid,
        "xml_message": xml_message,
    }

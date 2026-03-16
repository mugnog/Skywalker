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
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

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

XML WORKOUT FORMAT (Zwift .zwo) – EXAKTE STRUKTUR PFLICHT:
Vorlage (IMMER exakt so aufgebaut):
  <?xml version="1.0" encoding="utf-8"?>
  <workout_file>
    <author>Skywalker Coach</author>
    <name>Skywalker Z2 Fundamentals</name>
    <description>Zone 2 Ausdauer</description>
    <sportType>bike</sportType>
    <tags/>
    <workout>
      <Warmup Duration="480" PowerLow="0.25" PowerHigh="0.75">
        <textevent timeoffset="10" message="Locker einfahren!"/>
      </Warmup>
      <SteadyState Duration="3600" Power="0.65">
        <textevent timeoffset="60" message="Zone 2 halten!"/>
        <textevent timeoffset="1800" message="Halbzeit – Kadenz 90 rpm!"/>
        <textevent timeoffset="3300" message="Fast geschafft!"/>
      </SteadyState>
      <Cooldown Duration="480" PowerLow="0.50" PowerHigh="0.25">
        <textevent timeoffset="10" message="Ausfahren und erholen."/>
      </Cooldown>
    </workout>
  </workout_file>

REGELN:
- PFLICHT: author, name, description, sportType, tags/, workout – alle 6 Metadaten immer vorhanden
- <name> je nach Typ: "Skywalker Z2 Fundamentals" / "Skywalker Sweet Spot" / "Skywalker Z2+Sprints" / "Skywalker HIT Rønnestad" / "Skywalker FatMax"
- Warmup/Cooldown: NUR <Warmup> und <Cooldown> Tags (NIEMALS SteadyState als Warmup/Cooldown!)
- textevent: IMMER mit timeoffset-Attribut: <textevent timeoffset="60" message="Text"/>
- JEDER Block: mind. 3 textevent-Tags, Themen: Technik, Physiologie, Mental, Humor
- SteadyState: <SteadyState Duration="secs" Power="0.xx"/>
- Intervalle: <IntervalsT Repeat="6" OnDuration="30" OffDuration="480" OnPower="1.7" OffPower="0.6"/>
- Bei HIT/Sweet Spot: 4-stufige Aktivierungsleiter nach Warmup (60/70/80/90% FTP, 3min je)

ANTWORT-FORMAT:
1. Kurzes Coaching-Briefing auf DEUTSCH (2-4 Sätze, direkt, klar)
   → PFLICHT: Erste Zeile immer: "⏱ Dauer: XX min" (Gesamtdauer inkl. Warmup + Cooldown)
2. Dann IMMER ein vollständiges XML-Workout in ```xml``` Tags

Sei direkt, motivierend und präzise. Kein unnötiges Blabla.
"""


GOAL_DESCRIPTIONS = {
    "ftp":       "FTP steigern – Schwerpunkt Sweet Spot & Intervalle (Seiler-Pyramide)",
    "endurance": "Ausdauer – maximales Zone-2-Volumen, lange gleichmäßige Fahrten",
    "weight":    "Abnehmen – FatMax-Training, hohe Fettverbrennung, moderates Tempo",
    "race":      "Wettkampf-Vorbereitung – Periodisierung, Peaking, spezifische Einheiten",
    "health":    "Gesundheit & Fitness – ausgewogenes Training, Erholung hat Priorität",
}

FREQUENCY_DESCRIPTIONS = {
    "low":  "1–2x pro Woche (wenig Zeit, maximale Effizienz)",
    "mid":  "3–5x pro Woche (solide Basis, gute Fortschritte)",
    "high": "Täglich (hohes Volumen, Erholung besonders beachten)",
}

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
    training_goal: str = "",
    event_name: str = "",
    event_date: str = "",
    training_frequency: str = "",
    training_days: str = "",
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
    checkin_text = "KEIN CHECK-IN – bitte darauf hinweisen, dass ein Check-in sinnvoll wäre."
    if checkin:
        checkin_text = (
            f"✅ CHECK-IN VORHANDEN [{checkin.get('date')}]: "
            f"Schlaf={checkin.get('schlaf')}/10, Energie={checkin.get('energie')}/10, "
            f"Muskeln={checkin.get('muskeln')}/10, Mental={checkin.get('mental')}/10, "
            f"Gesundheit={checkin.get('gesundheit')}/10, Ernährung={checkin.get('ernahrung')}/10"
        )
        if checkin.get("rpe") is not None:
            checkin_text += f" | Post-Workout: RPE={checkin.get('rpe')}/10, Feel={checkin.get('feel')}/10"

    tp_block = f"\nTrainingPeaks Wochenplan:\n{tp_context}" if tp_context else ""

    goal_keys = [g.strip() for g in training_goal.split(",") if g.strip()] if training_goal else []
    if goal_keys:
        goal_text = " + ".join(GOAL_DESCRIPTIONS.get(k, k) for k in goal_keys)
    else:
        goal_text = "Kein Ziel definiert"
    freq_text = FREQUENCY_DESCRIPTIONS.get(training_frequency, "Nicht angegeben")

    DAY_LABELS = {"mon": "Mo", "tue": "Di", "wed": "Mi", "thu": "Do", "fri": "Fr", "sat": "Sa", "sun": "So"}
    if training_days:
        days_list = [DAY_LABELS.get(d, d) for d in training_days.split(",") if d]
        days_text = ", ".join(days_list) if days_list else "Nicht angegeben"
    else:
        days_text = "Nicht angegeben"

    event_text = "Kein Event eingetragen."
    if event_name and event_date:
        try:
            from datetime import date
            ev = date.fromisoformat(event_date)
            days_left = (ev - date.today()).days
            weeks_left = days_left // 7
            if days_left < 0:
                event_text = f"{event_name} (war am {event_date} – vergangen)"
            elif days_left == 0:
                event_text = f"{event_name} – HEUTE! 🏁"
            else:
                event_text = f"{event_name} am {event_date} → noch {weeks_left} Wochen ({days_left} Tage)"
        except Exception:
            event_text = f"{event_name} am {event_date}"
    elif event_name:
        event_text = event_name

    return f"""
=== ATHLETEN-KONTEXT ===
Trainingsziel: {goal_text}
Trainingsfrequenz: {freq_text}
Bevorzugte Trainingstage: {days_text}
Hauptevent: {event_text}
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
    training_goal: str = "",
    event_name: str = "",
    event_date: str = "",
    training_frequency: str = "",
    training_days: str = "",
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
        df_stats, df_act, checkin, tp_context,
        training_goal, event_name, event_date, training_frequency, training_days
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
    print(f"[COACH] response tokens={response.usage.output_tokens} stop={response.stop_reason} has_xml={'```' in raw}", flush=True)

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
        print(f"[COACH] extracted={'YES('+str(len(extracted))+')' if extracted else 'NONE'}", flush=True)
        if extracted:
            xml_valid, xml_message, xml_clean = validate_zwo(extracted)
            print(f"[COACH] xml_valid={xml_valid} xml_clean_len={len(xml_clean) if xml_clean else 0} msg={xml_message}", flush=True)

    return {
        "briefing": briefing,
        "xml": xml_clean,
        "xml_valid": xml_valid,
        "xml_message": xml_message,
    }

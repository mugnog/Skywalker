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
Dein Athlet: 52 Jahre, Chirurg. Schwerpunkt: Di/Mi/Fr-So.

HEALTH-FIRST (gilt immer, überstimmt jeden Modus):
- HRV, Schlaf < 5 oder Stress hoch → nur leichtes Z2, kein HIT
- Gesundheit < 5 → Ruhe empfehlen, kein Workout vorschlagen

═══════════════════════════════════════════
MODUS 1: FTP-STEIGERUNG
Aktivieren wenn Ziel = "ftp" oder "race"
═══════════════════════════════════════════
Philosophie: Pyramidales Training (Seiler) – 70% Z2 / 20% Sweet Spot / 10% HIT
Ziel: Funktionelle Schwelle erhöhen, VLamax senken

Workout-Toolkit (genau eine wählen):
- Z2 Fundamentals – 60–70% FTP, 60–90 min, aerobe Basis
- Z2 + Burgomaster-Sprints – Z2 + 3–4× 30s All-out (5 min Pause), neuromuskulär
- Sweet Spot – 88–94% FTP Blöcke, 2×20 min, Schwellentoleranz
- Sweet Spot Push (SS-P) – 92–96% FTP, 2×6 min kurz oder 2×14 min lang
- HIT Rønnestad – 30s/15s, 3× 10 Wdh. @135% FTP, nur TSB > 0 + Schlaf > 7

Entscheidungsfilter:
- Wochenende → Z2 Volumen bevorzugen
- Gestern hart → heute Z2 (Recovery)
- Schlaf > 7 + TSB > 0 → HIT oder Sweet Spot Push möglich
- Schlaf 5–7 → Sweet Spot oder Z2+Sprints
- Schlaf < 5 → nur Z2 Fundamentals

═══════════════════════════════════════════
MODUS 2: VO2MAX-STEIGERUNG
Aktivieren wenn Ziel = "vo2max"
═══════════════════════════════════════════
Philosophie: Kurze, sehr intensive Blöcke nahe VO2max (105–120% FTP)
Ziel: Kardiale Kapazität und maximale Sauerstoffaufnahme steigern
Frequenz: MAX 1–2× pro Woche, Rest Z2

Workout-Toolkit (genau eine wählen):
- VO2max Lang – 4×8 min @105–110% FTP, 4 min aktive Pause @50% (klassisch)
- VO2max Kurz – 5×5 min @110–115% FTP, 3 min Pause @50%
- HIT 30-15 – 3× (10× 30s @135% / 15s @50%), 5 min Satzpause (Rønnestad)
- Kraft-Ausdauer K3 – 6×6 min @86–91% FTP, 50–60 rpm, 3 min @45% Pause
- Drift Intervals – 6×8 min progressiv 79%→86% FTP, 5 min @45% Pause (Schwellenübergänge)

Entscheidungsfilter:
- TSB < 0 ODER Schlaf < 7 → kein VO2max, stattdessen Z2
- TSB > 0 + Schlaf > 7 → VO2max Lang oder HIT 30-15
- TSB > 5 + Schlaf > 8 → VO2max Kurz oder K3 möglich
- Nach 2 VO2max-Einheiten in einer Woche → Pflichtpause, nur Z2

═══════════════════════════════════════════
MODUS 3: ULTRACYCLING / LANGE AUSDAUER
Aktivieren wenn Ziel = "ultracycling" oder "endurance"
═══════════════════════════════════════════
Philosophie: Fettstoffwechsel, Ermüdungsresistenz, Back-to-Back-Fähigkeit
Ziel: Lange konstante Leistung, LT1-Entwicklung, mehrstündige Belastung
Basis: LT1 ~67% FTP, LT2 ~100% FTP

Workout-Toolkit (genau eine wählen):
- BM-Base – 65–72% FTP, 90–180 min, SteadyState, Fettstoffwechsel-Fokus
- BM-Nüchtern – 61–65% FTP, 60–90 min, erste 30 min ohne Carbs
- Z2 Back-to-Back – BM-Base Sa + So hintereinander (Ermüdungsresistenz)
- Drift Intervals – 6×8 min progressiv 79%→86% FTP (Schwellenübergänge trainieren)
- K3 Kraft-Ausdauer – 6×6 min @86–91% FTP, 50–60 rpm, 3 min @45% Pause
- Sweet Spot 2×20 – 88–92% FTP, 60–70 rpm (max 1× Woche)

Entscheidungsfilter:
- Wochenende → BM-Base oder Back-to-Back (Volumen priorisieren)
- Gestern lang gefahren (>2h) → heute BM-Base weitermachen (Ermüdungsresistenz)
- Schlaf > 7 + TSB > 0 → Drift Intervals oder Sweet Spot 2×20 möglich
- Schlaf 5–7 → BM-Base oder BM-Nüchtern
- Schlaf < 5 → nur leichte BM-Base, 60–90 min

═══════════════════════════════════════════
GLOBALE REGELN
═══════════════════════════════════════════
JOKER-REGEL: Max. 2 Intensitäts-Einheiten (HIT / VO2max / Sweet Spot) pro Woche!
OVERRIDE: Expliziter Athletenwunsch hat immer Vorrang – ausführen, aber warnen wenn riskant.

XML WORKOUT FORMAT (Zwift .zwo) – EXAKTE STRUKTUR PFLICHT:
Vorlage:
  <workout_file>
    <author>Skywalker Coach</author>
    <name>Skywalker Z2 Fundamentals</name>
    <description>Zone 2 Ausdauer – aerobe Basis</description>
    <sportType>bike</sportType>
    <tags>
        <tag name="skywalker"/>
    </tags>
    <workout>
      <Warmup Duration="480" PowerLow="0.43" PowerHigh="0.75" pace="0">
        <textevent timeoffset="10" message="Locker einfahren – Beine wecken!"/>
        <textevent timeoffset="120" message="Kadenz 90 rpm anstreben."/>
        <textevent timeoffset="360" message="Gleich geht es los – bereit machen!"/>
      </Warmup>
      <SteadyState Duration="3600" Power="0.65" pace="0">
        <textevent timeoffset="60" message="Zone 2 halten – unter 165W bleiben!"/>
        <textevent timeoffset="900" message="Seiler-Prinzip: 70% der Einheiten hier."/>
        <textevent timeoffset="1800" message="Halbzeit! Chirurgen-Präzision – Watt konstant halten."/>
        <textevent timeoffset="2700" message="Noch 15 min – aerobe Effizienz aufbauen!"/>
        <textevent timeoffset="3300" message="Letzter Push – du wirst stärker!"/>
      </SteadyState>
      <Cooldown Duration="480" PowerLow="0.55" PowerHigh="0.43" pace="0">
        <textevent timeoffset="10" message="Ausfahren – Laktat abbauen."/>
        <textevent timeoffset="240" message="Super Arbeit heute!"/>
      </Cooldown>
    </workout>
  </workout_file>

XML-REGELN:
- FTP-DYNAMIK: Power = Zielwatt / FTP (z.B. 165W / 255W = 0.647) – immer neu berechnen!
- PFLICHT: author, name, description, sportType, tags (<tag name="skywalker"/>), workout
- JEDER Block: pace="0" Attribut pflicht
- Cooldown: PowerLow > PowerHigh (rampt runter, z.B. PowerLow="0.55" PowerHigh="0.43")
- JEDER Block: mind. 3 textevent-Tags (Themen: Technik, Physiologie, Mental)
- Bei HIT/VO2max: 4-stufige Aktivierungsleiter nach Warmup (60/70/80/90% FTP, je 3 min)
- Workout-Namen: "Skywalker Z2 Fundamentals" / "Skywalker Sweet Spot" / "Skywalker Sweet Spot 2x20" / "Skywalker HIT Rønnestad" / "Skywalker FatMax" / "Skywalker BM-Base" / "Skywalker BM-Nüchtern" / "Skywalker VO2max Lang" / "Skywalker VO2max Kurz" / "Skywalker Drift Intervals" / "Skywalker K3 Kraft" / "Skywalker HIT 30-15"

ZWO-BEISPIELE:

DRIFT INTERVALS (66 min) – jedes Intervall HÖHER als das vorherige:
  <Warmup Duration="480" PowerLow="0.43" PowerHigh="0.60" pace="0">...</Warmup>
  <SteadyState Duration="480" Power="0.79" pace="0"><textevent timeoffset="10" message="Intervall 1/6 – 79% FTP, locker starten"/></SteadyState>
  <SteadyState Duration="300" Power="0.45" pace="0"><textevent timeoffset="10" message="Erholung – nächstes Intervall wird höher!"/></SteadyState>
  <SteadyState Duration="480" Power="0.81" pace="0"><textevent timeoffset="10" message="Intervall 2/6 – 81% FTP"/></SteadyState>
  <SteadyState Duration="300" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="480" Power="0.83" pace="0"><textevent timeoffset="10" message="Intervall 3/6 – 83% FTP"/></SteadyState>
  <SteadyState Duration="300" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="480" Power="0.84" pace="0"><textevent timeoffset="10" message="Intervall 4/6 – 84% FTP, Halbzeit"/></SteadyState>
  <SteadyState Duration="300" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="480" Power="0.85" pace="0"><textevent timeoffset="10" message="Intervall 5/6 – 85% FTP"/></SteadyState>
  <SteadyState Duration="300" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="480" Power="0.86" pace="0"><textevent timeoffset="10" message="Intervall 6/6 – 86% FTP, alles raus!"/></SteadyState>
  <Cooldown Duration="480" PowerLow="0.55" PowerHigh="0.43" pace="0">...</Cooldown>

VO2MAX LANG (72 min, 4×8 min):
  <Warmup Duration="600" PowerLow="0.43" PowerHigh="0.65" pace="0">...</Warmup>
  <SteadyState Duration="180" Power="0.60" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.70" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.80" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.90" pace="0"><textevent timeoffset="10" message="Letzte Stufe – gleich gehts los!"/></SteadyState>
  <IntervalsT Repeat="4" OnDuration="480" OffDuration="240" OnPower="1.07" OffPower="0.50" pace="0">
    <textevent timeoffset="10" message="VO2max – Sauerstoff maximieren!"/>
    <textevent timeoffset="240" message="Halbzeit – Rhythmus halten!"/>
    <textevent timeoffset="420" message="Noch 1 min – alles raus!"/>
  </IntervalsT>
  <Cooldown Duration="600" PowerLow="0.55" PowerHigh="0.43" pace="0">...</Cooldown>

HIT 30-15 (82 min, 3 Sätze à 10×30/15):
  <Warmup Duration="600" PowerLow="0.43" PowerHigh="0.65" pace="0">...</Warmup>
  <SteadyState Duration="180" Power="0.60" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.70" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.80" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.90" pace="0">...</SteadyState>
  <IntervalsT Repeat="10" OnDuration="30" OffDuration="15" OnPower="1.35" OffPower="0.50" pace="0">
    <textevent timeoffset="5" message="Satz 1 – explodieren!"/>
  </IntervalsT>
  <SteadyState Duration="300" Power="0.50" pace="0"><textevent timeoffset="10" message="Satzpause – tief durchatmen."/></SteadyState>
  <IntervalsT Repeat="10" OnDuration="30" OffDuration="15" OnPower="1.35" OffPower="0.50" pace="0">
    <textevent timeoffset="5" message="Satz 2 – du kannst das!"/>
  </IntervalsT>
  <SteadyState Duration="300" Power="0.50" pace="0">...</SteadyState>
  <IntervalsT Repeat="10" OnDuration="30" OffDuration="15" OnPower="1.35" OffPower="0.50" pace="0">
    <textevent timeoffset="5" message="Satz 3 – letzter Einsatz!"/>
  </IntervalsT>
  <Cooldown Duration="600" PowerLow="0.55" PowerHigh="0.43" pace="0">...</Cooldown>

K3 KRAFT-AUSDAUER (70 min, 6×6 min):
  <Warmup Duration="480" PowerLow="0.43" PowerHigh="0.65" pace="0">...</Warmup>
  <SteadyState Duration="360" Power="0.88" pace="0"><textevent timeoffset="10" message="50–60 rpm – Kraft, nicht Kadenz!"/></SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="360" Power="0.88" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="360" Power="0.88" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="360" Power="0.88" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="360" Power="0.88" pace="0">...</SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <SteadyState Duration="360" Power="0.88" pace="0"><textevent timeoffset="10" message="Letzter Satz – Drehmoment bis zum Ende!"/></SteadyState>
  <SteadyState Duration="180" Power="0.45" pace="0">...</SteadyState>
  <Cooldown Duration="480" PowerLow="0.55" PowerHigh="0.43" pace="0">...</Cooldown>

ANTWORT-FORMAT:
1. Kurzes Coaching-Briefing auf DEUTSCH (2–4 Sätze, direkt, klar)
   → PFLICHT: Erste Zeile immer: "⏱ Dauer: XX min"
2. Dann IMMER ein vollständiges XML-Workout in ```xml``` Tags

Sei direkt, motivierend und präzise. Kein unnötiges Blabla.
WICHTIG: Keine Emojis in Überschriften oder Fließtext.
"""


GOAL_DESCRIPTIONS = {
    "ftp":          "MODUS FTP – Schwelle steigern: Sweet Spot, HIT Rønnestad, Z2-Basis (Seiler-Pyramide)",
    "vo2max":       "MODUS VO2MAX – Maximale Sauerstoffaufnahme: 4×8 min @107% FTP, HIT 30-15, K3, max. 2× pro Woche",
    "ultracycling": "MODUS ULTRACYCLING – Lange Ausdauer: BM-Base 90–180 min, Back-to-Back, Drift Intervals, Fettstoffwechsel, LT1-Entwicklung",
    "endurance":    "MODUS ULTRACYCLING – Lange Ausdauer: BM-Base 90–180 min, Back-to-Back, Drift Intervals, Fettstoffwechsel, LT1-Entwicklung",
    "weight":       "Abnehmen – FatMax-Training, hohe Fettverbrennung, moderates Tempo",
    "race":         "MODUS FTP – Wettkampf-Vorbereitung: Periodisierung, Peaking, Sweet Spot & HIT",
    "health":       "Gesundheit & Fitness – ausgewogenes Training, Erholung hat Priorität",
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

    tp_block = f"\nintervals.icu / Trainingsplan (NUR ALS KONTEXT – du erstellst trotzdem eigene Empfehlung + XML wie gewohnt, kannst aber auf den Plan eingehen oder Alternativen vorschlagen):\n{tp_context}" if tp_context else ""

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


import streamlit as st
import pandas as pd
import plotly.express as px
import re
import xml.etree.ElementTree as ET
import PIL.Image
from datetime import datetime
from dotenv import load_dotenv
import anthropic
import base64
import os
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from streamlit_plotly_events import plotly_events
load_dotenv()
uploaded_tp_image = None

# =====================================================
# 0. DESIGN-UPGRADE & GRUNDSETUP
# =====================================================
load_dotenv()

# WICHTIG: Die Page Config muss vor dem ersten CSS-Block stehen
st.set_page_config(page_title="Skywalker Fitness Dashboard", layout="wide")

# Hier kommt das CSS für die großen Tabs und den fetten Balken hin
st.markdown("""
    <style>
    /* 1. Schriftgröße der Tabs oben massiv vergrößern */
    button[data-baseweb="tab"] p {
        font-size: 26px !important; 
        font-weight: 800 !important;
        margin-bottom: 0px;
    }

    /* 2. Den FTP-Balken (Progress Bar) richtig fett machen */
    .stProgress > div > div > div > div {
        height: 45px !important; /* Sehr dick */
        border-radius: 12px !important;
        background-image: linear-gradient(to right, #00C853, #b2ff59) !important;
    }
    
    /* Hintergrund des Balkens */
    .stProgress > div > div {
        background-color: #262626 !important;
        height: 45px !important;
        border-radius: 12px !important;
    }

    /* Farbe für den aktiven Tab (Grün) */
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #00C853 !important;
    }
    </style>
""", unsafe_allow_html=True)

API_KEY = os.getenv("ANTHROPIC_API_KEY")
SAVE_PATH = os.getenv("SAVE_PATH")

if not API_KEY:
    st.error("ANTHROPIC_API_KEY fehlt in der .env")
    st.stop()

if not SAVE_PATH:
    st.error("SAVE_PATH fehlt in der .env")
    st.stop()


# =====================================================
# 1. CLAUDE SETUP
# =====================================================
client = anthropic.Anthropic(api_key=API_KEY)

# =====================================================
# 2. DATEIPFADE & SIDEBAR FUNKTION
# =====================================================
FILE_STATS = os.path.join(SAVE_PATH, "garmin_stats.csv")
FILE_ACT = os.path.join(SAVE_PATH, "garmin_activities.csv")
FILE_CHECKIN = os.path.join(SAVE_PATH, "daily_checkin.csv")

def manual_data_upload():
    st.sidebar.header("📥 Daten-Import")
    uploaded_file = st.sidebar.file_uploader("Garmin CSV-Export hochladen", type=["csv"])

    if uploaded_file is not None:
        try:
            df_new = pd.read_csv(uploaded_file, encoding='utf-8-sig')

            # Robuste Erkennung: Mehrere Indikatoren prüfen
            STATS_INDICATORS = ["Sleep Score", "Schlafwert", "RHR", "HRV Avg", "HRV Status",
                                "Steps", "Schritte", "Sleep Total"]
            ACT_INDICATORS = ["activityName", "activityTrainingLoad", "normPower", "Aktivitätsname"]

            stats_hits = sum(1 for col in STATS_INDICATORS if col in df_new.columns)
            act_hits = sum(1 for col in ACT_INDICATORS if col in df_new.columns)

            if stats_hits >= act_hits:
                target_file = FILE_STATS
                st.sidebar.success(f"Gesundheitsdaten erkannt! ({stats_hits} Merkmale)")
            else:
                target_file = FILE_ACT
                st.sidebar.success(f"Aktivitäten erkannt! ({act_hits} Merkmale)")

            # Daten zusammenführen
            if os.path.exists(target_file):
                df_old = pd.read_csv(target_file, encoding='utf-8-sig')
                df_final = pd.concat([df_new, df_old]).drop_duplicates(subset=["Date"], keep="first")
                df_final.to_csv(target_file, index=False)
                st.sidebar.info("Daten wurden aktualisiert!")
                st.rerun()
                
        except Exception as e:
            st.sidebar.error(f"Fehler beim Lesen: {e}")

    # --- TRAININGPEAKS SEKTION ---
    st.sidebar.divider()
    st.sidebar.header("📸 TrainingPeaks Screenshot")
    
    # Der Uploader für das Workout-Bild
    uploaded_tp_image = st.sidebar.file_uploader(
        "Workout-Foto hochladen", 
        type=["png", "jpg", "jpeg"]
    )
    
    # Optionaler Text-Bereich bleibt als Backup
    tp_plan_text = st.sidebar.text_area(
        "Oder Plan als Text:",
        placeholder="z.B. Dienstag: 3x10min SweetSpot...",
        height=100
    )
    st.session_state['tp_plan_context'] = tp_plan_text
    
    return uploaded_tp_image

# HIER wird die Funktion aufgerufen (Ganz am linken Rand!)
uploaded_tp_image = manual_data_upload()

# =====================================================
# 3. DATEN LADEN (BACK TO BASICS - OHNE REINIGUNGS-FEHLER)
# =====================================================
def get_file_mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0

@st.cache_data
def load_all_data(_mtime_stats, _mtime_act, _mtime_checkin):
    df_s = pd.read_csv(FILE_STATS, encoding='utf-8-sig', on_bad_lines='warn') if os.path.exists(FILE_STATS) else None
    df_a = pd.read_csv(FILE_ACT, encoding='utf-8-sig', on_bad_lines='warn') if os.path.exists(FILE_ACT) else None
    df_c = pd.read_csv(FILE_CHECKIN, encoding='utf-8-sig', on_bad_lines='warn') if os.path.exists(FILE_CHECKIN) else None

    if df_s is not None:
        df_s["Date"] = pd.to_datetime(df_s["Date"], dayfirst=False).dt.normalize()
        
        step_col = "Steps" if "Steps" in df_s.columns else "Schritte"
        if step_col in df_s.columns:
            # Da deine Datei laut Screenshot reine Zahlen hat: Direkt umwandeln!
            df_s["Steps_num"] = pd.to_numeric(df_s[step_col], errors="coerce").fillna(0).astype(int)
        
        # Falls ein Tag doppelt vorkommt: Wir nehmen den ersten Eintrag (alle Spalten bleiben erhalten)
        df_s = df_s.sort_values("Date").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)
        
        # DEIN WUNSCH: Neu oben für die Tabellen-Ansicht
        df_s = df_s.sort_values("Date", ascending=False)
        
        df_s["Sleep_num"] = pd.to_numeric(df_s["Sleep Score"], errors="coerce")
        df_s["RHR_num"] = pd.to_numeric(df_s["RHR"], errors="coerce")

    if df_a is not None:
        df_a["Date"] = pd.to_datetime(df_a["Date"], dayfirst=False).dt.normalize()
        # Neu oben
        df_a = df_a.sort_values("Date", ascending=False)
        if "distance" in df_a.columns:
            df_a["KM"] = (pd.to_numeric(df_a["distance"], errors="coerce") / 1000).round(2)

    return df_s, df_a, df_c

# Variablen-Zuweisung
df_stats, df_act, df_checkin = load_all_data(
    get_file_mtime(FILE_STATS),
    get_file_mtime(FILE_ACT),
    get_file_mtime(FILE_CHECKIN)
)

# =====================================================
# ZENTRALE PERFORMANCE-BERECHNUNG (FIX: df_data definiert)
# =====================================================
curr_ctl, curr_atl, curr_tsb, weekly_load = 0, 0, 0, 0
est_ftp = 230
df_data = pd.DataFrame()
one_week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)

if df_act is not None and not df_act.empty:
    # 1. Wir erstellen die chronologische Arbeitskopie
    df_perf = df_act.sort_values("Date", ascending=True).copy()
    
    # 2. WICHTIG: Wir definieren df_data, damit der Rest des Codes funktioniert
    df_data = df_perf.copy() 
    
    # --- FTP SCHÄTZUNG ---
    thirty_days_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
    recent_acts = df_data[df_data['Date'] >= thirty_days_ago].copy()
    recent_acts['normPower'] = pd.to_numeric(recent_acts['normPower'], errors='coerce')
    
    if not recent_acts.empty and recent_acts['normPower'].max() > 0:
        est_ftp = int(recent_acts['normPower'].max() * 0.95)

    # --- WOCHEN-LOAD ---
    df_data['Load'] = pd.to_numeric(df_data['activityTrainingLoad'], errors='coerce').fillna(0)
    one_week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
    weekly_load = round(df_data[df_data['Date'] >= one_week_ago]['Load'].sum(), 1)
    
    # --- CTL/ATL/TSB BERECHNUNG ---
    daily_load = df_data.groupby('Date')['Load'].sum().reset_index()
    if not daily_load.empty:
        idx = pd.date_range(daily_load['Date'].min(), pd.Timestamp.now())
        daily_load = daily_load.set_index('Date').reindex(idx, fill_value=0).reset_index()
        daily_load.columns = ['Date', 'Load']
        
        daily_load['ATL'] = daily_load['Load'].ewm(span=7, adjust=False).mean()
        daily_load['CTL'] = daily_load['Load'].ewm(span=42, adjust=False).mean()
        daily_load['TSB'] = daily_load['CTL'].shift(1) - daily_load['ATL'].shift(1)
        
        curr_ctl = round(daily_load['CTL'].iloc[-1], 1)
        curr_atl = round(daily_load['ATL'].iloc[-1], 1)
        curr_tsb = round(daily_load['TSB'].iloc[-1] if not pd.isna(daily_load['TSB'].iloc[-1]) else 0, 1)


# =====================================================
# 4. ZWO VALIDATOR (SKYWALKER PRO EDITION)
# =====================================================
    
def validate_zwo(xml_string: str):
    """
    Validiert das von der KI generierte XML für Zwift.
    Gibt IMMER (bool, str, str) zurück.
    """
    try:
        # 1. Reinigung
        if not xml_string or "<workout_file>" not in xml_string:
            return False, "Kein gültiger XML-Code gefunden.", xml_string

        start_idx = xml_string.find("<workout_file>")
        end_idx = xml_string.find("</workout_file>") + 15
        xml_clean = xml_string[start_idx:end_idx]

        # 2. Parsen
        root = ET.fromstring(xml_clean)
        workout_node = root.find("workout")
        
        # 3. Sicherheits-Checks
        if workout_node is not None:
            # Check auf leere Repeats
            for repeat in workout_node.findall("Repeat"):
                if len(list(repeat)) == 0:
                    # Wenn wir hier einen Fehler finden, geben wir ihn sofort zurück
                    return False, "⚠️ Fehler: Leerer <Repeat>-Tag (keine Intervalle)!", xml_clean
            
            # Check ob überhaupt Inhalt da ist
            if len(list(workout_node)) == 0:
                return False, "⚠️ Fehler: Das Workout hat keine Trainingsschritte!", xml_clean

        # 4. Struktur neu aufbauen (Säuberung)
        new_root = ET.Element("workout_file")
        ET.SubElement(new_root, "author").text = root.findtext("author") or "Skywalker"
        ET.SubElement(new_root, "name").text = root.findtext("name") or "Skywalker Session"
        ET.SubElement(new_root, "description").text = root.findtext("description") or "Training by Skywalker"
        ET.SubElement(new_root, "sportType").text = "bike"
        
        new_workout = ET.SubElement(new_root, "workout")
        if workout_node is not None:
            for child in workout_node:
                step_node = ET.SubElement(new_workout, child.tag, child.attrib)
                for subchild in child:
                    ET.SubElement(step_node, subchild.tag, subchild.attrib)

        # 5. Finalisierung
        ET.indent(new_root, space="    ", level=0)
        final_xml = ET.tostring(new_root, encoding="unicode", method="xml")
        
        # WICHTIG: Der Erfolgs-Rückgabewert
        return True, "XML ist valide und bereit für Zwift.", final_xml

    except Exception as e:
        # WICHTIG: Der Fehler-Rückgabewert (falls beim Parsen was schiefgeht)
        return False, f"Strukturfehler im XML: {str(e)}", xml_string

# =====================================================
# 5. PROMPT
# =====================================================
heute_str = datetime.now().strftime("%A, %d.%m.%Y")
BASE_PROMPT = """
Du bist "Skywalker", ein professioneller Coach. 
Nutzer: 52 Jahre, Chirurg, Ziel FTP 250, Fokus Di/Mi und Fr-So.

WICHTIGE REGEL FÜR DEINE ANALYSE:
1. Priorität (80% Gewichtung): Nutze die Garmin-Daten. Das sind die Fakten.
2. Priorität (20% Gewichtung): Nutze das subjektive Daily Check-in als Ergänzung.

Regeln: Einfaches Deutsch, kein Smalltalk, nur XML bei Workouts.
"""

# =====================================================
# 6. UI HEADER (NEU OBEN LOGIK)
# =====================================================
st.title("🚀 Skywalker Fitness Dashboard")

if df_stats is not None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        # Neu oben: iloc[0] ist der aktuellste Wert
        s = df_stats.dropna(subset=["Sleep_num"])
        st.metric("Schlafwert (Aktuell)", int(s.iloc[0]["Sleep_num"]) if not s.empty else 0)
    with c2:
        a = df_act.dropna(subset=["activityTrainingLoad"]) if df_act is not None else pd.DataFrame()
        st.metric("Letzter Load", round(a.iloc[0]["activityTrainingLoad"], 1) if not a.empty else 0)
    with c3:
        r = df_stats.dropna(subset=["RHR_num"])
        st.metric("Ruhepuls", int(r.iloc[0]["RHR_num"]) if not r.empty else 0)
    with c4:
        yesterday_steps = 0
        label = "Schritte (Gestern)"
        # Nur Tage mit echten Schrittzahlen (> 0) nehmen
        s_stps = df_stats[df_stats["Steps_num"] > 0]
        if len(s_stps) >= 2:
            yesterday_steps = s_stps.iloc[1]["Steps_num"]
        elif not s_stps.empty:
            yesterday_steps = s_stps.iloc[0]["Steps_num"]
            label = "Schritte (Aktuell)"

        st.metric(label, f"{int(yesterday_steps):,}".replace(",", "."))

# =====================================================
# 7. TABS
# =====================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🤖 Coach", "🚴 Aktivitäten", "😴 Schlaf", "🏃 Schritte", "📈 Trends"])

# =====================================================
# TAB 1 – SKYWALKER COACH (KORRIGIERTE EINRÜCKUNG)
# =====================================================

with tab1:
    # --- A. CSS & DESIGN (Slider-Styling für Check-in) ---
    st.markdown("""
        <style>
        /* ===== SLIDER TRACK (Hintergrund-Schiene) ===== */
        [data-baseweb="slider"] [role="slider"] {
            width: 24px !important;
            height: 24px !important;
            background: white !important;
            border: 3px solid #444 !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5) !important;
            top: -8px !important;
        }
        /* Track-Gesamthöhe */
        [data-baseweb="slider"] > div > div {
            height: 10px !important;
            border-radius: 6px !important;
        }
        /* Inaktiver Teil (rechts vom Thumb) */
        [data-baseweb="slider"] > div > div:first-child {
            background: linear-gradient(90deg, #FF1744, #FF9100, #FFD600, #00E676) !important;
            height: 10px !important;
            border-radius: 6px !important;
            opacity: 0.25 !important;
        }
        /* Aktiver Teil (links vom Thumb) */
        [data-baseweb="slider"] > div > div:nth-child(2) {
            height: 10px !important;
            border-radius: 6px !important;
            background: linear-gradient(90deg, #FF1744, #FF9100, #FFD600, #00E676) !important;
        }
        /* Min/Max Labels ausblenden */
        [data-testid="stTickBarMin"], [data-testid="stTickBarMax"] {
            display: none !important;
        }
        /* Aktuellen Wert über dem Thumb ausblenden (redundant wegen Badge) */
        [data-testid="stThumbValue"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("🤖 Skywalker AI Coaching Netzwerk")
    
    # --- B. HEADER METRIKEN ---
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    c_m1.metric("Fitness (CTL)", curr_ctl)
    c_m2.metric("Ermüdung (ATL)", curr_atl)
    
    tsb_status, tsb_color = ("🔴 Überlastet", "inverse") if curr_tsb < -25 else (("🟢 Erholt", "normal") if curr_tsb > 5 else ("⚖️ Neutral", "off"))
    c_m3.metric("Form (TSB)", curr_tsb, delta=tsb_status, delta_color=tsb_color)
    c_m4.metric("Wochen-Load", weekly_load)

    st.divider()

    # =====================================================
    # NEU: AUTOMATISCHER FRESHNESS-CHECK
    # =====================================================
    st.subheader("🛡️ Skywalker Belastungs-Check")

    if df_stats is not None and df_act is not None:
        # Prüfung auf deine Spalte 'HRV Avg'
        if 'HRV Avg' in df_stats.columns and 'activityTrainingLoad' in df_act.columns:
            df_health = df_stats[['Date', 'HRV Avg']].dropna()
            df_load = df_act[['Date', 'activityTrainingLoad']].dropna()
            df_ready = pd.merge(df_health, df_load, on='Date', how='inner')

            if not df_ready.empty:
                hrv_baseline = df_ready['HRV Avg'].rolling(window=7).mean().iloc[-1]
                hrv_today = df_ready['HRV Avg'].iloc[-1]

                col_a1, col_a2 = st.columns([1, 2])
                with col_a1:
                    if hrv_today >= hrv_baseline * 0.95:
                        st.success("🟢 GRÜNES LICHT")
                        st.write("Bereit für Intensität (HIT/SweetSpot).")
                    elif hrv_today >= hrv_baseline * 0.85:
                        st.warning("🟡 GELBES LICHT")
                        st.write("Leichte Ermüdung. Fokus auf Zone 2.")
                    else:
                        st.error("🔴 ROTES LICHT")
                        st.write("Körper im Stress. Nur locker ausrollen!")

                with col_a2:
                    fig_ready = go.Figure()
                    fig_ready.add_trace(go.Scatter(x=df_ready['Date'], y=df_ready['HRV Avg'], name="HRV", line=dict(color="#00f2ff")))
                    fig_ready.add_trace(go.Bar(x=df_ready['Date'], y=df_ready['activityTrainingLoad'], name="Load", opacity=0.3, marker_color="#39FF14"))
                    fig_ready.update_layout(height=200, margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
                    st.plotly_chart(fig_ready, use_container_width=True)
        else:
            st.info("Datenquellen für HRV-Check werden synchronisiert...")
    
    st.divider()

    # --- C. MORNING CHECK-IN ---
    st.markdown("### ☀️ Morning Check-in (Heute)")
    c_date = st.date_input("Datum", datetime.now(), key="checkin_date_picker")
    c_date_pure = c_date.strftime("%Y-%m-%d")

    col_checkin, col_radar = st.columns([1.2, 1])

    with col_checkin:
        def val_color(v, invert=False):
            v_eff = 11 - v if invert else v
            if v_eff >= 8: return "#00E676"
            if v_eff >= 6: return "#FFD600"
            if v_eff >= 4: return "#FF9100"
            return "#FF1744"

        checkin_items = [
            {"key": "s1",      "label": "😴 Schlaf",    "default": 7, "invert": False},
            {"key": "s2_val",  "label": "🧠 Stress",    "default": 8, "invert": True},
            {"key": "s3",      "label": "⚡ Energie",    "default": 8, "invert": False},
            {"key": "s_load",  "label": "🏋️ Last",      "default": 5, "invert": True},
            {"key": "s4",      "label": "💪 Muskeln",   "default": 8, "invert": False},
            {"key": "s5",      "label": "🥗 Ernährung", "default": 7, "invert": False},
            {"key": "s6",      "label": "🎯 Mental",    "default": 7, "invert": False},
            {"key": "s_health","label": "❤️ Gesundheit", "default": 10, "invert": False},
        ]
        checkin_vals = {}
        for item in checkin_items:
            col_sl, col_badge = st.columns([6, 1])
            with col_sl:
                v = st.slider(item["label"], 1, 10, item["default"], key=f"ci_{item['key']}")
                checkin_vals[item["key"]] = v
            with col_badge:
                c = val_color(v, item["invert"])
                st.markdown(f"""
                <div style="margin-top:28px; text-align:center;">
                    <span style="display:inline-block; width:40px; height:40px; line-height:40px;
                        border-radius:50%; background:{c}18; border:2px solid {c};
                        color:{c}; font-weight:800; font-size:17px;">{v}</span>
                </div>""", unsafe_allow_html=True)

    s1 = checkin_vals["s1"]
    s2_val = checkin_vals["s2_val"]
    s2 = 11 - s2_val
    s3 = checkin_vals["s3"]
    s_load_est = checkin_vals["s_load"]
    s4 = checkin_vals["s4"]
    s5 = checkin_vals["s5"]
    s6 = checkin_vals["s6"]
    s_health = checkin_vals["s_health"]

    with col_radar:
        # Readiness Score
        all_vals = [s1, 11 - s2_val, s3, 11 - s_load_est, s4, s5, s6, s_health]
        readiness = round(sum(all_vals) / len(all_vals), 1)

        if readiness >= 8:
            r_color, r_status = "#00E676", "RACE READY"
        elif readiness >= 6:
            r_color, r_status = "#FFD600", "SOLID"
        elif readiness >= 4:
            r_color, r_status = "#FF9100", "MÜDE"
        else:
            r_color, r_status = "#FF1744", "RUHETAG"

        st.markdown(f"""
        <div style="text-align:center; padding: 10px 0;">
            <span style="font-size:48px; font-weight:900; color:{r_color};">{readiness}</span>
            <span style="font-size:16px; color:{r_color};">/10</span>
            <br><span style="font-size:14px; color:{r_color}; letter-spacing:3px;">{r_status}</span>
        </div>
        """, unsafe_allow_html=True)

        # Radar Chart
        radar_labels = ["Schlaf", "Stress", "Energie", "Erholung", "Muskeln", "Ernährung", "Mental", "Gesundheit"]
        radar_vals = all_vals + [all_vals[0]]  # Kreis schließen
        radar_labels_closed = radar_labels + [radar_labels[0]]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=radar_vals, theta=radar_labels_closed,
            fill='toself',
            fillcolor=f'rgba({int(r_color[1:3],16)},{int(r_color[3:5],16)},{int(r_color[5:7],16)},0.15)',
            line=dict(color=r_color, width=2.5),
            marker=dict(size=6, color=r_color),
            name='Heute'
        ))
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 10], showticklabels=False,
                    gridcolor='rgba(255,255,255,0.08)'),
                angularaxis=dict(gridcolor='rgba(255,255,255,0.08)',
                    tickfont=dict(size=11, color='#aaa')),
                bgcolor='rgba(0,0,0,0)'
            ),
            showlegend=False, height=320,
            margin=dict(l=40, r=40, t=20, b=20),
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_radar, width='stretch')

    if st.button("💾 Morning Stats speichern", type="primary"):
        checkin_row = {
            "Date": c_date_pure, "Schlaf": s1, "Stress": s2, "Energie": s3,
            "Load_Gestern": s_load_est, "Muskeln": s4, "Ernahrung": s5,
            "Mental": s6, "Gesundheit": s_health, "RPE": 0, "Feel": 0
        }
        if os.path.exists(FILE_CHECKIN):
            df_ci = pd.read_csv(FILE_CHECKIN, encoding='utf-8-sig')
            mask = df_ci["Date"] == c_date_pure
            if mask.any():
                for k, v in checkin_row.items():
                    if k != "Date":
                        df_ci.loc[mask, k] = v
            else:
                df_ci = pd.concat([df_ci, pd.DataFrame([checkin_row])], ignore_index=True)
        else:
            df_ci = pd.DataFrame([checkin_row])
        df_ci.to_csv(FILE_CHECKIN, index=False)
        st.success("Check-in gespeichert!")
        st.rerun()

    st.divider()

    # --- D. ACTIVITY REVIEW & MATRIX ---
    # ... (Hier kommt dein restlicher Code für die Matrix und die KI-Logik hin)
    # WICHTIG: Alles muss diese 4 Leerzeichen Einrückung behalten!

    # --- D. ACTIVITY REVIEW (INVERTED MATRIX - NATIVE) ---
    st.markdown("### 🚴 Activity Review & Strain Matrix")
    
    if df_act is not None and not df_act.empty:
        last_act = df_act.sort_values("Date", ascending=False).iloc[0]
        act_date = pd.to_datetime(last_act['Date']).strftime("%Y-%m-%d")
        act_name = last_act.get('activityName', 'Training')
        act_load = round(last_act.get('activityTrainingLoad', 0), 1)
        
        st.info(f"Bewerte: **{act_name}** am **{act_date}** (TSS: {act_load})")
        
        # State Initialisierung
        if 'rpe_val' not in st.session_state: st.session_state.rpe_val = 5
        if 'feel_val' not in st.session_state: st.session_state.feel_val = 2 

        col_g1, col_g2 = st.columns([1, 1.5])
        
        with col_g2:
            import numpy as np

            # Heatmap-Daten: Smooth Gradient über 100x100 Grid
            grid_size = 50
            x_grid = np.linspace(1, 10, grid_size)
            y_grid = np.linspace(1, 10, grid_size)
            z_grid = np.array([[(x + y) / 20.0 for x in x_grid] for y in y_grid])

            fig_matrix = go.Figure()

            # 1. Smooth Heatmap als Hintergrund
            fig_matrix.add_trace(go.Heatmap(
                x=x_grid, y=y_grid, z=z_grid,
                colorscale=[
                    [0.0, '#0d4f1c'], [0.25, '#1a8a3a'],
                    [0.45, '#c8b800'], [0.65, '#e87a1e'],
                    [0.85, '#c92a2a'], [1.0, '#7a0000']
                ],
                showscale=False, opacity=0.5,
                hoverinfo='none'
            ))

            # 2. Unsichtbares Klick-Gitter (für Punkt-Auswahl)
            grid_clicks_x = []
            grid_clicks_y = []
            for gx in [i * 0.5 for i in range(2, 21)]:
                for gy in [i * 0.5 for i in range(2, 21)]:
                    grid_clicks_x.append(gx)
                    grid_clicks_y.append(gy)
            fig_matrix.add_trace(go.Scatter(
                x=grid_clicks_x, y=grid_clicks_y,
                mode='markers',
                marker=dict(size=18, color='rgba(0,0,0,0)', symbol='square'),
                hoverinfo='text',
                text=[f"Intensität: {x}, Leiden: {y}" for x, y in zip(grid_clicks_x, grid_clicks_y)],
                name='Grid'
            ))

            # 4. Zonen-Trennlinien
            for val in [3.5, 5.5, 7.5]:
                fig_matrix.add_shape(type="line", x0=val, x1=val, y0=0.5, y1=10.5,
                    line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dot"))
                fig_matrix.add_shape(type="line", x0=0.5, x1=10.5, y0=val, y1=val,
                    line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dot"))

            # 5. Zonen-Labels
            zones = [
                dict(x=2, y=2, text="FRESH", color="#00E676"),
                dict(x=8.5, y=2, text="PUSH", color="#FFD600"),
                dict(x=2, y=8.5, text="TIRED", color="#FF9100"),
                dict(x=8.5, y=8.5, text="DANGER", color="#FF1744"),
            ]
            for z in zones:
                fig_matrix.add_annotation(
                    x=z["x"], y=z["y"], text=z["text"], showarrow=False,
                    font=dict(size=14, color=z["color"], family="Arial Black"),
                    opacity=0.4
                )

            # 6. Glow-Ring um den Spieler-Punkt
            px_val = st.session_state.rpe_val
            py_val = st.session_state.feel_val
            curr_score = (px_val + py_val) / 2
            glow_color = "#00E676" if curr_score < 4 else ("#FFD600" if curr_score < 6 else ("#FF9100" if curr_score < 8 else "#FF1744"))

            fig_matrix.add_trace(go.Scatter(
                x=[px_val], y=[py_val], mode='markers',
                marker=dict(size=55, color='rgba(0,0,0,0)',
                    line=dict(width=3, color=glow_color)),
                hoverinfo='none', name='Glow'
            ))

            # 7. Spieler-Punkt
            fig_matrix.add_trace(go.Scatter(
                x=[px_val], y=[py_val],
                mode='markers+text',
                marker=dict(size=38, color='#111111',
                    line=dict(width=2.5, color='white')),
                text=["DU"], textposition="middle center",
                textfont=dict(color='white', size=13, family="Arial Black"),
                hoverinfo='none', name='Player'
            ))

            fig_matrix.update_layout(
                xaxis=dict(range=[0.5, 10.5], title="Intensität", showgrid=False,
                    zeroline=False, fixedrange=True, color='#888',
                    tickvals=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
                yaxis=dict(range=[0.5, 10.5], title="Leiden", showgrid=False,
                    zeroline=False, fixedrange=True, color='#888',
                    tickvals=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
                width=420, height=420,
                margin=dict(l=40, r=15, t=15, b=40),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False, dragmode=False
            )

            event = st.plotly_chart(fig_matrix, on_select="rerun", selection_mode="points", key="matrix_select")

            if event and event["selection"]["points"]:
                clicked_point = event["selection"]["points"][0]
                new_x = round(clicked_point["x"] * 2) / 2
                new_y = round(clicked_point["y"] * 2) / 2
                if new_x != st.session_state.rpe_val or new_y != st.session_state.feel_val:
                    st.session_state.rpe_val = new_x
                    st.session_state.feel_val = new_y
                    st.rerun()

        with col_g1:
            st.write("### Matrix Analyse")
            curr_x = st.session_state.rpe_val
            curr_y = st.session_state.feel_val
            strain_score = (curr_x + curr_y) / 2
            
            col_res1, col_res2 = st.columns(2)
            col_res1.metric("Intensität", curr_x)
            col_res2.metric("Wohlbefinden", f"{curr_y} ", help="1=Super, 10=Schlecht")
            
            if strain_score >= 8:
                status, note, color = "💀 GEFAHR", "Hohe Last + Schlechtes Gefühl.", "red"
            elif strain_score >= 6:
                status, note, color = "🔥 HARDCORE", "Du ziehst durch, trotz Schmerz.", "orange"
            elif strain_score >= 4:
                status, note, color = "✅ SOLID", "Training wirkt, Gefühl ok.", "yellow"
            else:
                status, note, color = "💎 FRESH", "Alles locker, top Gefühl.", "green"
                
            st.markdown(f"### Score: :{color}[{strain_score:.1f}]")
            st.markdown(f"**Status:** {status}")
            st.caption(note)

            if st.button(f"💾 Matrix für {act_date} speichern", type="primary"):
                if os.path.exists(FILE_CHECKIN):
                    df_old = pd.read_csv(FILE_CHECKIN, encoding='utf-8-sig')
                    for col in ["RPE", "Feel"]: 
                        if col not in df_old.columns: df_old[col] = 0
                    
                    mask = df_old['Date'] == act_date
                    if mask.any():
                        df_old.loc[mask, 'RPE'] = curr_x
                        df_old.loc[mask, 'Feel'] = curr_y 
                        df_old.to_csv(FILE_CHECKIN, index=False)
                        st.success(f"Gespeichert!")
                    else:
                        new_row = {col: 0 for col in df_old.columns}
                        new_row['Date'] = act_date
                        new_row['RPE'] = curr_x
                        new_row['Feel'] = curr_y
                        new_row['Schlaf'] = 7
                        new_row['Gesundheit'] = 8
                        df_final = pd.concat([df_old, pd.DataFrame([new_row])], ignore_index=True)
                        df_final.to_csv(FILE_CHECKIN, index=False)
                        st.success(f"Neu angelegt!")
                else:
                    st.error("Erst Morning Check-in machen!")

    else:
        st.warning("Keine Aktivitäten gefunden.")

    st.divider()

    # --- E. KI-LOGIK (MIT ZWIFT SCHUTZ & AGENTEN) ---
    heute_jetzt = datetime.now().strftime("%A, %d.%m.%Y")
    
    garmin_perf_ctx = "KEINE DATEN"
    if df_act is not None:
        cols = ["Date", "activityName", "activityTrainingLoad", "normPower", "averageHR"]
        avail = [c for c in cols if c in df_act.columns]
        garmin_perf_ctx = df_act[avail].head(5).to_string(index=False)

    garmin_stats_ctx = df_stats.iloc[:7].to_string(index=False) if df_stats is not None else "KEINE STATS"
    
    checkin_hist = "KEIN CHECK-IN"
    if os.path.exists(FILE_CHECKIN):
        checkin_hist = pd.read_csv(FILE_CHECKIN, encoding='utf-8-sig').tail(7).to_string(index=False)

    base_ftp = 230
    
  
# ZWIFT XML REGELN (SKYWALKER PRO-EDITION)
    ZWO_SCHEMA = """
    ERSTELLE DAS WORKOUT IM .ZWO (XML) FORMAT NACH DIESEN STRENGEN VORGABEN:
    1. FORMATIERUNG: Nutze Einrückungen (Indentation) für die Lesbarkeit.
    2. METADATEN: 
       - <author> ist "Skywalker".
       - <description> enthält das Trainingsziel (z.B. VLamax-Senkung nach Mader).
       - <tags> enthält <tag name="..."/> (z.B. SweetSpot, FTPBuilder).
    3. LIVE-COACHING (Textevents): 
       - JEDER Block (Warmup, SteadyState, etc.) MUSS mindestens 3 <textevent> enthalten.
       - Diese müssen INNERHALB des Intervall-Tags stehen.
    4. Jedes Workout muss mit <Warmup> beginnen und mit <Cooldown> enden, jeweils 8 MInuten.
    5. Nach dem WarmUp muss eine Aktivierung erfolgen, wenn ein HIT oder Sweet Spot Intervall vorgeschlagen wird, in der Form
       AKTIVIERUNGS-TREPPE (Standard)
       - 3 Min @ 60% FTP
       - 3 Min @ 70% FTP
       - 3 Min @ 80% FTP
       - 3 Min @ 90% FTP
       Nutze hierfür ausschließlich <SteadyState> Blöcke.
    6. TEXTEVENTS: Die Texte in den <textevent> Tags müssen bei jedem Workout variieren. 
    7. THEMEN-POOLS: Wechsle zwischen verschiedenen Coaching-Stilen:
       - Technisch: Fokus auf Trittfrequenz, Aerodynamik und runden Tritt.
       - Physiologisch: Erklärungen zu Mitochondrien, VLamax und Fettstoffwechsel (Mader/Seiler).
       - Mental: Motivation für einen Chirurgen ("Konzentration wie im OP", "Präzision im Tritt").
       - Humorvoll: Leichte Sprüche ("Pedalritter, auf zum FTP-Kreuzzug!", "Heute jagen wir die Wattgeister!").
       - Ruhe: Einfach nur Ruhephasen ankündigen.
    8. KORREKTES STRUKTUR-BEISPIEL:
       <workout_file>
         <author>Skywalker</author>
         <name>Skywalker_Session</name>
         <description>FTP-Aufbau nach Coggan-Modell.</description>
         <sportType>bike</sportType>
         <tags><tag name="SweetSpot"/></tags>
         <workout>
           <Warmup Duration="600" PowerLow="0.5" PowerHigh="0.75">
             <textevent timeoffset="0" message="Willkommen, Skywalker! Fokus auf den Tritt."/>
             <textevent timeoffset="300" message="Hälfte vom Warmup. Schultern locker lassen."/>
             <textevent timeoffset="580" message="Bereit machen für den Hauptteil!"/>
           </Warmup> 
        <SteadyState Duration="180" Power="0.6" pace="0"/>
        <SteadyState Duration="180" Power="0.7" pace="0"/>
        <SteadyState Duration="180" Power="0.8" pace="0"/>
        <SteadyState Duration="180" Power="0.9" pace="0"/>
        <SteadyState Duration="300" Power="0.55" pace="0"/>
           <SteadyState Duration="1200" Power="0.9">
             <textevent timeoffset="0" message="Start Sweet Spot! Wir bauen deine 250W FTP."/>
             <textevent timeoffset="600" message="Halbzeit! Bleib stabil, das ist der Mader-Reiz."/>
             <textevent timeoffset="1180" message="Gleich hast du Pause!"/>
           </SteadyState>
           <CoolDown Duration="600" PowerLow="0.75" PowerHigh="0.4">
             <textevent timeoffset="0" message="Starke Leistung! Jetzt locker ausrollen."/>
           </CoolDown>
         </workout>
       </workout_file>
    9. Ein <Repeat>-Tag darf NIEMALS allein stehen. Er muss <IntervalsT> umschließen oder durch <IntervalsT> ersetzt werden.
    10. Für Sprints (Burgomaster/HIT) nutze AUSSCHLIESSLICH: 
       <IntervalsT Repeat="6" OnDuration="30" OffDuration="480" OnPower="1.7" OffPower="0.6" />
    """

    curr_rpe = st.session_state.get('rpe_val', 5)
    curr_feel = st.session_state.get('feel_val', 2)

    # --- HIER IST DAS "GEHIRN" MIT DER NEUEN VORFAHRTSREGEL ---
    skywalker_instruction = """
    Du bist Skywalker, ein professioneller Radsport-Coach.
    Deine Philosophie: Pyramidal (70/20/10) nach Seiler/Mader/Coggan.

    DEINE AUFGABE:
    Analysiere die Daten des Athleten (Sleep Score, HRV, Daily Check-in) und passe die Einheit exakt an den Frischezustand an.

    DEINE PRIORITÄTEN (STRENG EINHALTEN):
    1. DAS WOCHEN-BUDGET: Ein Athlet hat meist nur 2 "Joker" pro Woche für Intensität (Sweet Spot oder HIT). 
    2. DER VOLUMEN-FOKUS: Da das Ziel 4-6h Fahrten sind, ist Zone 2 (Z2) dein Standard-Werkzeug. 
    3. VLAMAX-KONTROLLE: Wir wollen die VLamax senken. Das erfordert lange, ruhige Fahrten.

    LOGIK-FILTER FÜR DEINE ENTSCHEIDUNG:
    - IST ES WOCHENENDE (FR-SO)? -> Schlage vor allem langes Zone 2 Training vor (Volumen vor Intensität).
    - WAR GESTERN SCHON HART? -> Heute dann eher Zone 2, egal wie gut der Schlaf war.

    DEINE WERKZEUGKISTE (Nur diese Optionen nutzen):
    1. Basis & FatMax (Seiler/Mader): Lange, ruhige Fahrten (Zone 1/2) für Fettstoffwechsel, das soll 70% aller Empfehlungen ausmachen,
    2. z2 Grundlagenfahrten mit 60-70% der FTP 
    3. Z2 + Burgomaster-Sprints: Grundlagenfahrt mit 3-4 kurzen "All-out" Sprints (30s), um Mitochondrien zu triggern ohne Ermüdung. Zwichen den Sprints bitte 5 Minuten normale Grundlagenfahrt.
    3. Sweet Spot (Coggan): Blöcke im Bereich 88-94% FTP zur VLamax-Senkung und Effizienz-Steigerung.
    4. HIT (Rønnestad): 30/15 Intervalle für maximale VO2max (nur wenn Athlet frisch!).Nur wenn TSB positiv (>0) UND Schlaf > 7

    LOGIK FÜR DIE INTENSITÄT (AUTOMATIK):
    - Wenn Sleep/Gesundheit > 7 & TSB positiv -> Wähle HIT oder harten Sweet Spot.
    - Wenn Sleep/Gesundheit 5-7 -> Wähle Standard Sweet Spot oder Z2+Sprints.
    - Wenn Sleep/Gesundheit < 5 oder Stress hoch -> Wähle NUR FatMax/Basis.

    !!! WICHTIGE VORFAHRTSREGEL (MANUELLE WÜNSCHE) !!!:
    Wenn der Athlet in der 'ANFRAGE' einen spezifischen Wunsch äußert (z.B. "Ich will heute 2h Zone 2" oder "Nur HIT Woche"), dann hat dieser Wunsch IMMER Vorrang vor der Pyramiden-Logik und den Gesundheitsdaten. Führe den Wunsch des Athleten aus, aber warne kurz, falls es physiologisch riskant ist.
    """

    DYNAMIC_PROMPT = f"""
    {BASE_PROMPT}
    HEUTE IST: {heute_jetzt}
    
    {skywalker_instruction}

    WICHTIGE UNTERSCHEIDUNG (Arbeitsteilung):
    1. STRATEGIE (Garmin-Daten): Nutze CTL ({curr_ctl}), ATL ({curr_atl}) und TSB ({curr_tsb}), um zu entscheiden, OB und WAS trainiert wird.
    2. AUSFÜHRUNG (Base FTP): Nutze für die Erstellung der XML-Intervalle AUSSCHLIESSLICH {base_ftp}W als 100% Referenz.
    
    DATEN-KONTEXT:
    - Garmin: {garmin_stats_ctx} | {garmin_perf_ctx}
    - Check-in Heute: Schlaf {s1}/10, Stress {s2}/10, Energie {s3}/10, Gesundheit {s_health}/10
    - Matrix Letztes Training: Härte {curr_rpe}/10, Leiden {curr_feel}/10.
    
    {ZWO_SCHEMA}

    ANWEISUNG: Antworte als Skywalker. Kurz, präzise, chirurgisch. 
    1. Struktur: 'ANALYSE', 'PLAN' & 'FTP-SCHÄTZUNG'
    2. BRIEFING: Erkläre dem Athleten das Workout in normalen Worten (Was, Warum, Dauer).
    3. XML: Der Code für Zwift.
    """

    # --- F. COACHING AKTIONEN ---
    if "last_answer" not in st.session_state: st.session_state.last_answer = ""
    
    final_query = ""
    b1, b2, b3 = st.columns(3)
    if b1.button("📊 Profi-Analyse"): final_query = "Führe eine Agenten-Analyse meiner aktuellen Form durch und plane das optimale Training für heute."
    if b2.button("📅 5-Tage-Plan"): final_query = "Erstelle einen 5-Tage-Periodisierungsplan inklusive heutigem XML."
    if b3.button("🛋️ Erholungstipps"): final_query = "Berechne eine optimale Erholungsstrategie."
    
    user_text = st.text_input("Eigene Frage an das Skywalker Netzwerk")
    send = st.button("Senden")

    st.write("Spezielle Trainingswünsche:")
    cw1, cw2, cw3 = st.columns(3)
    if cw1.button("🚲 2h Zone 2"): final_query = "Ich möchte heute unbedingt 2 Stunden locker in Zone 2 fahren. Erstelle das XML."
    if cw2.button("🔥 Kurze Intervalle"): final_query = "Plane heute eine Einheit mit kurzen, harten Intervallen (z.B. 30/30s)."
    if cw3.button("🚀 FTP Test"): final_query = "Ich fühle mich stark. Plane einen 20-minütigen FTP-Test."

    if not final_query and user_text and send:
        final_query = user_text

    # --- G. KI AUSFÜHRUNG (BEREINIGT) ---
    if final_query:
        with st.spinner("Das Skywalker Agenten-Netzwerk analysiert alle Datenpunkte..."):
            try:
                # 1. Prompt bauen
                user_content = []

                # 2. Bild hinzufügen (falls hochgeladen)
                if uploaded_tp_image:
                    img_bytes = uploaded_tp_image.getvalue()
                    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
                    media_type = "image/png"
                    if uploaded_tp_image.name:
                        ext = uploaded_tp_image.name.rsplit(".", 1)[-1].lower()
                        if ext in ("jpg", "jpeg"):
                            media_type = "image/jpeg"
                    user_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": img_b64}
                    })

                user_content.append({"type": "text", "text": f"{DYNAMIC_PROMPT}\n\nANFRAGE: {final_query}"})

                # 3. KI Aufruf (Claude Opus)
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    temperature=0,
                    messages=[{"role": "user", "content": user_content}]
                )

                # 4. Ergebnis speichern
                st.session_state.last_answer = response.content[0].text

            except Exception as e:
                st.error(f"Agenten-Fehler: {e}")

    # --- H. ANTWORT & XML (DEEP-CLEAN VERSION) ---
    if st.session_state.last_answer:
        st.info("🤖 Skywalkers Coaching-Feedback")
        
        raw_text = st.session_state.last_answer
        
        # 1. Alles ab dem ersten XML-Tag hart abschneiden
        if "<workout_file>" in raw_text:
            briefing_part = raw_text.split("<workout_file>")[0]
        else:
            briefing_part = raw_text
            
        # 2. Markdown-Code-Blöcke und Umbrüche säubern
        briefing_part = briefing_part.replace("```xml", "").replace("```", "").strip()
        
        # 3. ZEILEN-SCAN: Wir filtern von unten nach oben
        forbidden_words = ["XML", "CODE", "DATEI", "WORKOUT", "HIER IST", "3.", "ANHANG"]
        lines = briefing_part.split('\n')
        
        # Wir behalten nur Zeilen, die NICHT wie eine XML-Überschrift aussehen
        clean_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Wenn die Zeile leer ist, ignorieren wir sie vorerst
            if not stripped_line:
                clean_lines.append(line)
                continue
                
            # Check: Ist die Zeile eine der typischen "Hier kommt XML"-Überschriften?
            # Wir prüfen, ob die Zeile sehr kurz ist und eines der verbotenen Wörter enthält
            upper_line = stripped_line.upper()
            is_junk = any(word in upper_line for word in forbidden_words) and len(stripped_line) < 25
            
            if not is_junk:
                clean_lines.append(line)
        
        # Wieder zusammenbauen und unnötige Leerzeichen am Ende killen
        final_briefing = "\n".join(clean_lines).strip()
        
        # 4. Anzeige des sauberen Briefings
        if len(final_briefing) > 5:
            st.subheader("📋 Coach-Briefing")
            st.markdown(final_briefing)
        
        # 5. XML extrahieren & Download Button (Bleibt im Hintergrund)
        xml_match = re.search(r"(<workout_file>.*?</workout_file>)", raw_text, re.DOTALL)
        
        if xml_match:
            raw_xml = xml_match.group(1)
            valid, msg, final_xml = validate_zwo(raw_xml)
            
            if valid:
                try:
                    root = ET.fromstring(final_xml)
                    name_tag = root.find("name")
                    w_name = name_tag.text if name_tag is not None else "Skywalker_Workout"
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', w_name)
                except:
                    w_name = "Workout"
                    clean_name = "Skywalker_Workout"
                
                st.divider()
                st.success(f"🚀 Workout '{w_name}' ist bereit!")
                
                st.download_button(
                    label=f"📥 DOWNLOAD: {clean_name}.zwo", 
                    data=final_xml, 
                    file_name=f"{clean_name}.zwo", 
                    mime="application/xml",
                    type="primary"
                )
            else:
                st.warning(f"XML-Fehler: {msg}")
                st.code(raw_xml, language="xml")

# =====================================================
# TAB 2 – AKTIVITÄTEN (KORRIGIERTE GARMIN-VERSION)
# =====================================================
with tab2:
    if df_act is not None:
        # 1. Kopie und Spaltennamen säubern
        df_display = df_act.sort_values("Date", ascending=False).head(20).copy()
        
        # 2. Erweiterter Dolmetscher (Deutsch & Englisch)
        # Wir fügen hier "Ø Trittfrequenz" und andere Garmin-Namen hinzu
        mapping = {
            "Datum": "Date",
            "Titel": "Name",
            "Ø Trittfrequenz": "Cadence",
            "avgCadence": "Cadence",
            "Durchschn. Trittfrequenz": "Cadence",
            "Ø Herzfrequenz": "HF (Avg)",
            "Distanz": "Distanz (km)",
            "Normalized Power® (NP®)": "NP",
            "Training Stress Score®": "TSS",
            "activityTrainingLoad": "TSS",
            "Ø Leistung": "Watt (Avg)",
            "averagePower": "Watt (Avg)"
        }
        
        # Umbenennen
        df_display = df_display.rename(columns={k: v for k, v in mapping.items() if k in df_display.columns})
        
        # 3. Datentypen korrigieren & Reinigung (Wichtig für '--' Werte von Garmin)
        possible_cols = ["Cadence", "NP", "TSS", "Watt (Avg)", "HF (Avg)"]
        for col in possible_cols:
            if col in df_display.columns:
                # Ersetze '--' durch nichts, damit pd.to_numeric funktioniert
                df_display[col] = df_display[col].replace('--', pd.NA)
                df_display[col] = pd.to_numeric(df_display[col], errors='coerce')

        # 4. Runden (Nur für Zahlen-Spalten)
        num_cols = df_display.select_dtypes(include=['number']).columns
        for col in num_cols:
            # Wir runden auf 0 Nachkommastellen für die Tabelle
            df_display[col] = df_display[col].fillna(0).round(0).astype(int)
        
        # 5. Anzeige der Tabelle
        st.dataframe(df_display, use_container_width=True)
        
        # Debug-Info (nur falls Cadence immer noch fehlt)
        if "Cadence" not in df_display.columns:
            st.warning(f"Spalte für Trittfrequenz nicht erkannt. Vorhandene Spalten: {list(df_act.columns)}")
            
    else:
        st.info("Noch keine Aktivitäten geladen.")
# =====================================================
# TAB 3 – SCHLAF
# =====================================================
with tab3:
    if df_stats is not None:
        # FIX: Erst sortieren (alt -> neu), dann die letzten 90 nehmen
        df_sleep = df_stats.sort_values("Date", ascending=True).dropna(subset=["Sleep_num"]).tail(90)
        
        if not df_sleep.empty:
            fig_sleep = px.area(df_sleep, x="Date", y="Sleep_num", color_discrete_sequence=['#00f2ff'])
            # Range auf 0-100 begrenzen, damit man Schwankungen besser sieht
            fig_sleep.update_layout(yaxis=dict(range=[0, 105]), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_sleep, width='stretch')

# =====================================================
# TAB 4 – SCHRITTE (STRIKTE ABSOLUTWERTE)
# =====================================================
with tab4:
    if df_stats is not None:
        # Nur Tage mit echten Schrittzahlen, zeitlich sortiert
        df_chart = df_stats[df_stats["Steps_num"] > 0].sort_values("Date", ascending=True).tail(30)
        
        fig_steps = px.bar(
            df_chart, 
            x="Date", 
            y="Steps_num", # EXAKT die Spalte mit den echten Zahlen
            title="Schritte (Absoluter Wert)",
            color_discrete_sequence=['#39FF14']
        )
        
        # WICHTIG: Keine automatische Abkürzung (kein 7.7k), sondern echte Zahlen
        fig_steps.update_traces(texttemplate='%{y}', textposition='outside')
        
        fig_steps.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)',
            yaxis_title="Schritte",
            hovermode="x unified"
        )
        st.plotly_chart(fig_steps, use_container_width=True)

# =====================================================
# TAB 5 – TRENDS & PERFORMANCE (CTL/ATL/TSB)
# =====================================================
with tab5:
    st.header("📈 Performance Management (CTL / ATL / TSB)")
    
    if df_act is not None and not df_act.empty:
        # 1. Daten für Performance-Metriken vorbereiten
        df_perf = df_act.copy()
        df_perf['Date'] = pd.to_datetime(df_perf['Date'])
        df_perf['activityTrainingLoad'] = pd.to_numeric(df_perf['activityTrainingLoad'], errors='coerce').fillna(0)
        
        # Tägliche Last aggregieren
        daily_load = df_perf.groupby('Date')['activityTrainingLoad'].sum().reset_index()
        
        # Zeitreihe lückenlos machen
        idx = pd.date_range(daily_load['Date'].min(), daily_load['Date'].max())
        daily_load = daily_load.set_index('Date').reindex(idx, fill_value=0).reset_index()
        daily_load.columns = ['Date', 'Load']
        
        # 2. CTL, ATL und TSB berechnen
        daily_load['ATL'] = daily_load['Load'].ewm(span=7, adjust=False).mean()
        daily_load['CTL'] = daily_load['Load'].ewm(span=42, adjust=False).mean()
        daily_load['TSB'] = daily_load['CTL'].shift(1) - daily_load['ATL'].shift(1)
        
        # 3. Großes Performance Chart
        fig_perf = px.line(daily_load.tail(90), x='Date', y=['CTL', 'ATL'], 
                           title="Fitness (CTL) vs. Ermüdung (ATL) - Letzte 90 Tage",
                           labels={'value': 'Training Stress', 'variable': 'Metrik'},
                           color_discrete_map={'CTL': '#00FF00', 'ATL': '#FF0000'})
        
        # TSB (Form) als Balken hinzufügen
        fig_perf.add_bar(x=daily_load.tail(90)['Date'], y=daily_load.tail(90)['TSB'], name='Form (TSB)', 
                         marker_color=daily_load.tail(90)['TSB'].apply(lambda x: 'rgba(0, 255, 255, 0.4)' if x >= 0 else 'rgba(255, 165, 0, 0.4)'))
        
        # FIX: width='stretch' statt use_container_width
        st.plotly_chart(fig_perf, width='stretch')
        
        # 4. Aktuelle Werte als Metriken
        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
            st.metric("Fitness (CTL)", round(curr_ctl, 1), help="Deine langfristige Belastbarkeit.")
        with c_m2:
            st.metric("Ermüdung (ATL)", round(curr_atl, 1), help="Deine kurzfristige Belastung.")
        with c_m3:
            tsb_state = "Frisch" if curr_tsb > 5 else ("Ermüdet" if curr_tsb < -20 else "Optimales Training")
            st.metric("Form (TSB)", round(curr_tsb, 1), delta=tsb_state, delta_color="normal" if curr_tsb > -20 else "inverse")

    st.divider()

    # --- ZIELE & FORTSCHRITT SEKTION ---
    st.header("🎯 Ziele & Fortschritt")
    
    col_t1, col_t2 = st.columns([1.6, 1])
    
    with col_t1:
        # VO2 Max Daten kommen aus der garmin_stats.csv
        if df_stats is not None:
            df_vo2 = df_stats.copy()
            df_vo2['Date'] = pd.to_datetime(df_vo2['Date'])
            vo2_col_name = "VO2 Max" 
            
            if vo2_col_name in df_vo2.columns:
                df_vo2[vo2_col_name] = pd.to_numeric(df_vo2[vo2_col_name], errors='coerce')
                df_vo2 = df_vo2.dropna(subset=[vo2_col_name])
                df_vo2 = df_vo2.sort_values('Date')
                
                if not df_vo2.empty:
                    fig_vo2 = px.line(df_vo2, x='Date', y=vo2_col_name, title="VO2Max Reise (seit 2020)",
                                      markers=True, color_discrete_sequence=['#FF69B4'])
                    fig_vo2.update_traces(line=dict(width=2), marker=dict(size=4))
                    fig_vo2.update_xaxes(range=["2020-01-01", datetime.now().strftime("%Y-%m-%d")],
                                         tickformat="%Y", dtick="M12", gridcolor='#333')
                    fig_vo2.update_layout(height=400, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                                          hovermode="x unified", yaxis_title="VO2 Max")
                    st.plotly_chart(fig_vo2, width='stretch')

    with col_t2:
        st.subheader("🚀 Aktuelle Power-Schätzung")
        # Hier nutzen wir jetzt den zentralen Wert 'est_ftp'
        st.metric("Geschätzte FTP", f"{est_ftp} W", delta=f"{est_ftp - 230} W vs. Start")
        st.write("Basis: 95% deiner besten NP (letzte 30 Tage).")

    st.markdown("---")
    
    # --- DIE GROSSE GRAFISCHE FTP-WALL ---
    st.header("🏁 Der Weg zur 250-Watt-Marke")
    
    target_ftp = 250
    start_point = 150 
    
    total_range = target_ftp - start_point
    current_progress = est_ftp - start_point
    progress_percent = min(max(current_progress / total_range, 0.0), 1.0)
    
    st.write(f"Dein aktueller Stand: **{est_ftp} Watt**")
    st.progress(progress_percent)
    
    c_s1, c_s2 = st.columns([1, 1])
    c_s1.caption(f"Basis: {start_point}W")
    c_s2.markdown(f"<p style='text-align: right; color: #00C853; font-size: 20px; font-weight: bold;'>Ziel: {target_ftp}W</p>", unsafe_allow_html=True)

    st.divider()
    st.header("📊 Trainings-Verteilung (Last 7 Days)")

    if df_act is not None and not df_act.empty:
        # Wir kategorisieren die Einheiten grob nach Intensität (basierend auf IF/NP falls vorhanden, sonst Schätzung)
        df_dist = df_data[df_data['Date'] >= one_week_ago].copy()
        
        # Einfache Logik: Wir schauen uns das Verhältnis von Last zu Dauer an oder nutzen die Namen
        # Hier eine simple Kategorisierung für das Dashboard:
        def categorize_load(row):
            name = str(row['activityName']).lower()
            if any(x in name for x in ['sweet', 'intervals', 'hit', 'vo2', 'sprint', 'test']):
                return "Intensität (HIT/SS)"
            return "Basis (Zone 2)"

        df_dist['Type'] = df_dist.apply(categorize_load, axis=1)
        dist_chart = px.pie(df_dist, values='Load', names='Type', 
                            title="Pyramiden-Check (Ziel: 80% Basis)",
                            color='Type',
                            color_discrete_map={'Basis (Zone 2)': '#00C853', 'Intensität (HIT/SS)': '#D50000'})
        
        st.plotly_chart(dist_chart, use_container_width=True)
        
        z2_share = (df_dist[df_dist['Type'] == "Basis (Zone 2)"]['Load'].sum() / df_dist['Load'].sum()) * 100 if df_dist['Load'].sum() > 0 else 0
        if z2_share < 70:
            st.warning(f"Achtung: Nur {z2_share:.1f}% Basis-Training. Du trainierst zu hart für das Mader-Modell!")
        else:
            st.success(f"Top! {z2_share:.1f}% im Basis-Bereich. Deine Mitochondrien danken es dir.")

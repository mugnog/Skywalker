import streamlit as st
import pandas as pd
import plotly.express as px
import re
import xml.etree.ElementTree as ET
import PIL.Image
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
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

API_KEY = os.getenv("GOOGLE_API_KEY")
SAVE_PATH = os.getenv("SAVE_PATH")

if not API_KEY:
    st.error("GOOGLE_API_KEY fehlt in der .env")
    st.stop()

if not SAVE_PATH:
    st.error("SAVE_PATH fehlt in der .env")
    st.stop()


# =====================================================
# 1. GEMINI SETUP
# =====================================================
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

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
            df_new = pd.read_csv(uploaded_file)
            
            # Check: Sind es Schlafdaten oder Aktivitäten?
            if "Sleep Score" in df_new.columns or "Schlafwert" in df_new.columns:
                target_file = FILE_STATS
                st.sidebar.success("Schlafdaten erkannt!")
            else:
                target_file = FILE_ACT
                st.sidebar.success("Aktivität erkannt!")

            # Daten zusammenführen
            if os.path.exists(target_file):
                df_old = pd.read_csv(target_file)
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
# 3. DATEN LADEN
# =====================================================
@st.cache_data(ttl=60)
def load_all_data():
    df_s = pd.read_csv(FILE_STATS) if os.path.exists(FILE_STATS) else None
    df_a = pd.read_csv(FILE_ACT) if os.path.exists(FILE_ACT) else None
    df_c = pd.read_csv(FILE_CHECKIN) if os.path.exists(FILE_CHECKIN) else None

    if df_s is not None:
        df_s["Date"] = pd.to_datetime(df_s["Date"])
        df_s["Sleep_num"] = pd.to_numeric(df_s["Sleep Score"], errors="coerce")
        df_s["RHR_num"] = pd.to_numeric(df_s["RHR"], errors="coerce")
        df_s["Steps_num"] = pd.to_numeric(df_s["Steps"], errors="coerce")

    if df_a is not None:
        df_a["Date"] = pd.to_datetime(df_a["Date"])
        if "distance" in df_a.columns:
            df_a["KM"] = (pd.to_numeric(df_a["distance"], errors="coerce") / 1000).round(2)

    if df_c is not None:
        df_c["Date"] = pd.to_datetime(df_c["Date"])

    return df_s, df_a, df_c

df_stats, df_act, df_checkin = load_all_data()


# =====================================================
# ZENTRALE PERFORMANCE-BERECHNUNG (Inkl. FTP-Schätzung Fix)
# =====================================================
curr_ctl, curr_atl, curr_tsb, weekly_load = 0, 0, 0, 0
est_ftp = 230  # Standardwert als Fallback

if df_act is not None and not df_act.empty:
    df_perf = df_act.copy()
    df_perf['Date'] = pd.to_datetime(df_perf['Date'])
    
    # Wir nehmen die Daten (iloc[1:] überspringt die Einheiten-Zeile)
    df_data = df_perf.iloc[1:].copy()
    
    # --- 1. FTP SCHÄTZUNG (JETZT GANZ OBEN BERECHNET) ---
    thirty_days_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
    recent_acts = df_data[df_data['Date'] >= thirty_days_ago].copy()
    recent_acts['normPower'] = pd.to_numeric(recent_acts['normPower'], errors='coerce')
    
    if not recent_acts.empty and recent_acts['normPower'].max() > 0:
        est_ftp = int(recent_acts['normPower'].max() * 0.95)

    # --- 2. WOCHEN-LOAD BERECHNEN ---
    df_data['Load'] = pd.to_numeric(df_data['activityTrainingLoad'], errors='coerce').fillna(0)
    one_week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
    weekly_load = round(df_data[df_data['Date'] >= one_week_ago]['Load'].sum(), 1)
    
    # --- 3. CTL/ATL/TSB BERECHNUNG ---
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
    try:
        # 1. Reinigung
        if "<workout_file>" in xml_string:
            xml_string = xml_string[xml_string.find("<workout_file>"):]
        if "</workout_file>" in xml_string:
            xml_string = xml_string[:xml_string.find("</workout_file>") + 15]

        # 2. Parsen
        root = ET.fromstring(xml_string)
        new_root = ET.Element("workout_file")
        
        # --- METADATEN ---
        ET.SubElement(new_root, "author").text = root.findtext("author") or "Skywalker"
        ET.SubElement(new_root, "name").text = root.findtext("name") or "Skywalker Workout"
        
        desc_text = root.findtext("description") or "Professionelles Training by Skywalker"
        ET.SubElement(new_root, "description").text = desc_text
        
        ET.SubElement(new_root, "sportType").text = "bike"
        
        # Tags übernehmen
        tags_node = root.find("tags")
        new_tags = ET.SubElement(new_root, "tags")
        if tags_node is not None:
            for t in tags_node.findall("tag"):
                ET.SubElement(new_tags, "tag", t.attrib)
        
        # --- WORKOUT-BEREICH (MIT TEXT-EVENTS) ---
        workout_node = root.find("workout")
        new_workout = ET.SubElement(new_root, "workout")

        if workout_node is not None:
            for child in workout_node:
                new_attrs = {}
                for k, v in child.attrib.items():
                    kl = k.lower()
                    if kl == "duration": new_attrs["Duration"] = v
                    elif kl == "power": new_attrs["Power"] = v
                    elif kl == "powerlow": new_attrs["PowerLow"] = v
                    elif kl == "powerhigh": new_attrs["PowerHigh"] = v
                    elif kl in ["repeat", "onpower", "offpower", "onduration", "offduration"]:
                        new_attrs[k[0].upper() + k[1:]] = v
                    else:
                        new_attrs[k] = v
                
                new_attrs["pace"] = "0"
                step_node = ET.SubElement(new_workout, child.tag, new_attrs)
                
                # WICHTIG: Hier werden die Coaching-Nachrichten gerettet!
                for subchild in child.findall("textevent"):
                    ET.SubElement(step_node, "textevent", subchild.attrib)

        # 3. Schöne Formatierung
        ET.indent(new_root, space="    ", level=0)
        final_xml = ET.tostring(new_root, encoding="unicode", method="xml")
        
        return True, "OK", final_xml

    except Exception as e:
        return False, str(e), xml_string

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
# 6. UI HEADER
# =====================================================
st.title("🚀 Skywalker Fitness Dashboard")

if df_stats is not None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        s = df_stats.dropna(subset=["Sleep_num"]).sort_values("Date")
        st.metric("Letzter Schlaf", int(s.iloc[-1]["Sleep_num"]) if not s.empty else 0)
    with c2:
        a = df_act.dropna(subset=["activityTrainingLoad"]) if df_act is not None else pd.DataFrame()
        st.metric("Letzter Load", round(a.iloc[-1]["activityTrainingLoad"], 1) if not a.empty else 0)
    with c3:
        r = df_stats.dropna(subset=["RHR_num"]).sort_values("Date")
        st.metric("Ruhepuls", int(r.iloc[-1]["RHR_num"]) if not r.empty else 0)
    with c4:
        st.metric("Schritte", int(df_stats.iloc[-1]["Steps_num"]) if df_stats is not None else 0)

# =====================================================
# 7. TABS
# =====================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🤖 Coach", "🚴 Aktivitäten", "😴 Schlaf", "🏃 Schritte", "📈 Trends"])

# =====================================================
# TAB 1 – SKYWALKER COACH (KORRIGIERTE EINRÜCKUNG)
# =====================================================

with tab1:
    # --- A. CSS & DESIGN ---
    st.markdown("""
        <style>
        div[data-baseweb="slider"] > div:first-child > div:first-child {
            height: 12px !important; 
            border-radius: 6px !important;
            background: linear-gradient(to right, #00C853, #FFD600, #D50000) !important;
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
    
    col_left, col_right = st.columns(2)
    with col_left:
        s1 = st.slider("Schlafqualität", 1, 10, 7)
        s2_val = st.slider("Stress-Level", 1, 10, 8)
        s2 = 11 - s2_val 
        s3 = st.slider("Physische Energie", 1, 10, 8)
        s_load_est = st.slider("Gefühlte Last gestern", 1, 10, 5)

    with col_right:
        s4 = st.slider("Muskelzustand", 1, 10, 8)
        s5 = st.slider("Ernährung", 1, 10, 7) 
        s6 = st.slider("Mentale Frische", 1, 10, 7)
        s_health = st.slider("Gesundheit", 1, 10, 10)

    if st.button("💾 Morning Stats speichern"):
        # ... (Dein Speicher-Code bleibt gleich, achte nur auf die Einrückung)
        pass

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
            x_vals = []
            y_vals = []
            colors = []
            
            steps = [i * 0.5 for i in range(2, 21)] 
            
            for x in steps:
                for y in steps:
                    x_vals.append(x)
                    y_vals.append(y)
                    # ALGO: (Intensität + Invertiertes Wohlbefinden) / 20 -> 0 bis 1
                    score = (x + y) / 20.0
                    colors.append(score)

            fig_matrix = go.Figure()

            # 1. Heatmap
            fig_matrix.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode='markers',
                marker=dict(
                    symbol='square', size=18, color=colors,
                    colorscale='RdYlGn_r', # Grün (Low) -> Rot (High)
                    cmin=0.1, cmax=0.9,
                    showscale=False, opacity=0.4
                ),
                hoverinfo='none', name='Heatmap'
            ))

            # 2. Dein Punkt
            fig_matrix.add_trace(go.Scatter(
                x=[st.session_state.rpe_val], 
                y=[st.session_state.feel_val], 
                mode='markers+text',
                marker=dict(size=40, color='#262626', line=dict(width=3, color='white')),
                text=["DU"], textposition="middle center", textfont=dict(color='white', size=12, weight='bold'),
                hoverinfo='none', name='Selection'
            ))

            fig_matrix.update_layout(
                xaxis=dict(range=[0.5, 10.5], title="Intensität (Watt)", showgrid=False, zeroline=False, fixedrange=True),
                yaxis=dict(range=[0.5, 10.5], title="Wohlbefinden (1=Gut ... 10=Schlecht)", showgrid=False, zeroline=False, fixedrange=True),
                width=400, height=400,
                margin=dict(l=20, r=20, t=20, b=20),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False, dragmode=False 
            )

            # --- HIER IST DER UNTERSCHIED ---
            # Wir nutzen st.plotly_chart mit on_select="rerun"
            # Das ist NATIVE STREAMLIT (kein Plugin nötig)
            event = st.plotly_chart(fig_matrix, on_select="rerun", selection_mode="points", key="matrix_select")

            if event and event["selection"]["points"]:
                clicked_point = event["selection"]["points"][0]
                new_x = clicked_point["x"]
                new_y = clicked_point["y"]
                # Runden auf 0.5
                new_x = round(new_x * 2) / 2
                new_y = round(new_y * 2) / 2
                
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
                    df_old = pd.read_csv(FILE_CHECKIN)
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
        checkin_hist = pd.read_csv(FILE_CHECKIN).tail(7).to_string(index=False)

    base_ftp = 230
    est_ftp = base_ftp 
    
  
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
    4. KORREKTES STRUKTUR-BEISPIEL:
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
    """

    curr_rpe = st.session_state.get('rpe_val', 5)
    curr_feel = st.session_state.get('feel_val', 2)

    # --- HIER IST DAS "GEHIRN" MIT DER NEUEN VORFAHRTSREGEL ---
    skywalker_instruction = """
    Du bist Skywalker, ein professioneller Radsport-Coach.
    Deine Philosophie: Pyramidal (70/20/10) nach Seiler/Mader/Coggan.

    DEINE AUFGABE:
    Analysiere die Daten des Athleten (Sleep Score, HRV, Daily Check-in) und passe die Einheit exakt an den Frischezustand an.

    DEINE WERKZEUGKISTE (Nur diese Optionen nutzen):
    1. Basis & FatMax (Seiler/Mader): Lange, ruhige Fahrten (Zone 1/2) für Fettstoffwechsel.
    2. z2 Grundlagenfahrten mit 60-70% der FTP 
    3. Z2 + Burgomaster-Sprints: Grundlagenfahrt mit 3-4 kurzen "All-out" Sprints (30s), um Mitochondrien zu triggern ohne Ermüdung.
    3. Sweet Spot (Coggan): Blöcke im Bereich 88-94% FTP zur VLamax-Senkung und Effizienz-Steigerung.
    4. HIT (Rønnestad): 30/15 Intervalle für maximale VO2max (nur wenn Athlet frisch!).

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
                prompt_parts = [f"{DYNAMIC_PROMPT}\n\nANFRAGE: {final_query}"]
                
                # 2. Bild hinzufügen (falls hochgeladen)
                if uploaded_tp_image:
                    img = PIL.Image.open(uploaded_tp_image)
                    prompt_parts.append(img)
                
                # 3. KI Aufruf (Mit Temperature 0.1 für Stabilität)
                response = client.models.generate_content(
                    model="models/gemini-2.0-flash", 
                    contents=prompt_parts,
                    config=types.GenerateContentConfig(
                        temperature=0,  # Stabil & Konsistent
                        top_p=0.95,
                        top_k=40
                    )
                )
                
                # 4. Ergebnis speichern
                st.session_state.last_answer = response.text

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
# TAB 4 – SCHRITTE
# =====================================================
with tab4:
    if df_stats is not None:
        # FIX: Auch hier erst sortieren
        df_steps = df_stats.sort_values("Date", ascending=True).tail(30)
        
        fig_steps = px.bar(df_steps, x="Date", y="Steps_num", color_discrete_sequence=['#39FF14'], text_auto='.2s')
        fig_steps.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_steps, width='stretch')

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
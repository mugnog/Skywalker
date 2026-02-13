import streamlit as st
import pandas as pd
import plotly.express as px
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from google.genai import Client
from streamlit_autorefresh import st_autorefresh

# 1. EINSTELLUNGEN & PFADE
load_dotenv()
st.set_page_config(page_title="Skywalker Fitness Dashboard", layout="wide")
save_path_env = os.getenv("SAVE_PATH")

if not save_path_env:
    st.error("SAVE_PATH fehlt in der .env!")
    st.stop()

FILE_STATS = os.path.join(save_path_env, "garmin_stats.csv")
FILE_ACT = os.path.join(save_path_env, "garmin_activities.csv")
FILE_CHECKIN = os.path.join(save_path_env, "daily_checkin.csv")

st_autorefresh(interval=24 * 60 * 60 * 1000, key="dailyupdate")

# 2. DATEN LADEN (ROBUST)
@st.cache_data(ttl=60)
def load_all_data():
    df_s = pd.read_csv(FILE_STATS) if os.path.exists(FILE_STATS) else None
    df_a = pd.read_csv(FILE_ACT) if os.path.exists(FILE_ACT) else None
    df_c = pd.read_csv(FILE_CHECKIN) if os.path.exists(FILE_CHECKIN) else None
    
    if df_s is not None:
        df_s['Date'] = pd.to_datetime(df_s['Date'])
        df_s['Sleep_num'] = pd.to_numeric(df_s['Sleep Score'], errors='coerce')
        df_s['RHR_num'] = pd.to_numeric(df_s['RHR'], errors='coerce')
        df_s['Steps_num'] = pd.to_numeric(df_s['Steps'], errors='coerce')
        
    if df_a is not None:
        df_a['Date'] = pd.to_datetime(df_a['Date'])
        if 'distance' in df_a.columns:
            df_a['KM'] = (pd.to_numeric(df_a['distance'], errors='coerce') / 1000).round(2)
            
    if df_c is not None:
        df_c['Date'] = pd.to_datetime(df_c['Date'])
        
    return df_s, df_a, df_c

df_stats, df_act, df_checkin = load_all_data()

# --- HEADER METRIKEN ---
st.title("🚀 Skywalker Fitness Dashboard")

if df_stats is not None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        valid_sleep = df_stats.dropna(subset=['Sleep_num']).sort_values('Date')
        s_val = int(valid_sleep.iloc[-1]['Sleep_num']) if not valid_sleep.empty else 0
        st.metric("Letzter Schlaf Score", f"{s_val} Pkt")
    with c2: 
        load_val = 0.0
        if df_act is not None and not df_act.empty:
            valid_act = df_act.dropna(subset=['activityTrainingLoad']).sort_values('Date')
            if not valid_act.empty:
                load_val = round(float(valid_act.iloc[-1]['activityTrainingLoad']), 1)
        st.metric("Letzter Load", f"{load_val}")
    with c3:
        valid_rhr = df_stats.dropna(subset=['RHR_num']).sort_values('Date')
        r_val = int(valid_rhr.iloc[-1]['RHR_num']) if not valid_rhr.empty else 0
        st.metric("Letzter Ruhepuls", f"{r_val} bpm")
    with c4:
        valid_steps = df_stats.dropna(subset=['Steps_num']).sort_values('Date')
        st_val = int(valid_steps.iloc[-1]['Steps_num']) if not valid_steps.empty else 0
        st.metric("Letzte Schritte", f"{st_val:,}")

# --- TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🤖 Coach Skywalker", "🚴 Aktivitäten", "😴 Schlaf & Gesundheit", "🏃 Schritte", "📈 Langzeit-Trends"
])

# TAB 1: COACH & CHECK-IN (MIT ECHTER KI)
with tab1:
    st.header("🤖 Dein Coach Skywalker")
    with st.expander("📝 Täglicher Check-in", expanded=False):
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            s_stress = st.slider("Mentaler Stress heute", 1, 10, 5)
            s_muskel = st.slider("Muskelgefühl heute", 1, 10, 3)
            s_load_yd = st.slider("Belastung gestern", 1, 10, 5)
        with col_r2:
            s_nahrung = st.slider("Nahrung/Trinken gestern", 1, 10, 8)
            s_energie = st.slider("Energie heute", 1, 10, 7)
            s_gesamt = st.slider("Gesamtgefühl", 1, 10, 7)
        krank = st.checkbox("Krank? 🤒")
        
        if st.button("Check-in speichern"):
            heute_tag = datetime.now().strftime("%Y-%m-%d")
            neue_zeile = pd.DataFrame([{"Date": heute_tag, "Stress": s_stress, "Muskeln": s_muskel, "Load_Gestern": s_load_yd, "Nahrung": s_nahrung, "Energie": s_energie, "Gesamt": s_gesamt, "Krank": krank}])
            if os.path.exists(FILE_CHECKIN):
                df_old = pd.read_csv(FILE_CHECKIN)
                pd.concat([df_old, neue_zeile]).drop_duplicates('Date', keep='last').to_csv(FILE_CHECKIN, index=False)
            else:
                neue_zeile.to_csv(FILE_CHECKIN, index=False)
            st.success("Werte gespeichert!")
            st.cache_data.clear()
            st.rerun()

    if df_checkin is not None and not df_checkin.empty:
        l = df_checkin.iloc[-1]
        st.subheader("⚡ Skywalker Sofort-Check")
        if l['Krank']: st.error("🔴 Trainingsverbot!")
        elif l['Stress'] > 8: st.warning("🟡 Zu viel Stress.")
        else: st.info("🟢 Alles okay.")

    # --- KI LOGIK MIT DATEN-ÜBERGABE ---
    if 'ki_antwort' not in st.session_state: st.session_state.ki_antwort = ""
    if 'last_api_call' not in st.session_state: st.session_state.last_api_call = 0
    
    c_b1, c_b2, c_b3 = st.columns(3)
    b1 = c_b1.button("📊 Analyse & Trend")
    b2 = c_b2.button("📅 Plan (5 Tage)")
    b3 = c_b3.button(" Erholungstipps")

    u_frage = st.text_input("Spezielle Wünsche?", key="c_input")
    b_send = st.button("Frage senden")

    if b1 or b2 or b3 or b_send:
        jetzt = time.time()
        if jetzt - st.session_state.last_api_call < 10:
            st.warning("⏳ Kurz warten...")
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                try:
                    st.session_state.last_api_call = jetzt
                    client = Client(api_key=api_key)
                    
                    # Hier bauen wir den Kontext aus deinen echten CSV-Daten
                    stats_context = df_stats.tail(7).to_string() if df_stats is not None else "Keine Daten"
                    act_context = df_act.tail(5).to_string() if df_act is not None else "Keine Aktivitäten"
                    
                    mode = "Analyse deiner Form"
                    if b2: mode = "Erstellung eines 5-Tage-Plans"
                    if b3: mode = "Tipps zur Erholung"
                    if b_send: mode = f"Beantwortung der Frage: {u_frage}"

                    prompt = f"""
                    Du bist Coach Skywalker. Dein Athlet (Skywalker) hat ein FTP-Ziel von 250 (aktuell 230).
                    Er bereitet sich auf 4-6h Fahrten vor. Fokus-Tage: Fr-So, Di/Mi Abends.
                    Daten der letzten Tage: {stats_context}
                    Letzte Aktivitäten: {act_context}
                    
                    Deine Aufgabe: {mode}. 
                    Antworte kurz, präzise und motivierend.
                    """
                    
                    with st.spinner("Skywalker rechnet..."):
                        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                        st.session_state.ki_antwort = response.text
                except Exception as e: st.error(f"KI Fehler: {e}")
            else:
                st.error("GEMINI_API_KEY fehlt in der .env Datei!")

    if st.session_state.ki_antwort:
        st.markdown("---")
        st.markdown(st.session_state.ki_antwort)

# (Der Rest bleibt wie in deinem Code für die Tabs 2-5)
with tab2:
    st.subheader("Die letzten 20 Trainingseinheiten")
    if df_act is not None and not df_act.empty:
        df_display = df_act.sort_values('Date', ascending=False).head(20).copy()
        df_display['Datum'] = df_display['Date'].dt.strftime('%d.%m.%Y')
        cols = [c for c in ['Datum', 'activityName', 'KM', 'activityTrainingLoad'] if c in df_display.columns]
        st.dataframe(df_display[cols], use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Trend: Schlaf & Ruhepuls")
    if df_stats is not None:
        c_h1, c_h2 = st.columns(2)
        with c_h1:
            df_sleep_plot = df_stats.dropna(subset=['Sleep_num']).tail(30)
            st.plotly_chart(px.area(df_sleep_plot, x='Date', y='Sleep_num', title="Schlaf Score (30 Tage)"), use_container_width=True)
        with c_h2:
            df_rhr_plot = df_stats.dropna(subset=['RHR_num']).tail(30)
            st.plotly_chart(px.line(df_rhr_plot, x='Date', y='RHR_num', title="Ruhepuls (30 Tage)"), use_container_width=True)

with tab4:
    if df_stats is not None:
        st.plotly_chart(px.bar(df_stats.tail(30), x='Date', y='Steps_num', title="Schritte", color_discrete_sequence=['#39FF14']), use_container_width=True)

with tab5:
    st.header("📈 Langzeit-Trends")
    if df_act is not None and not df_act.empty:
        df_l = df_act.dropna(subset=['activityTrainingLoad']).sort_values('Date')
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.plotly_chart(px.line(df_l, x='Date', y='activityTrainingLoad', title="Belastung"), use_container_width=True)
        with col_t2:
            if 'vo2Max' in df_l.columns:
                st.plotly_chart(px.scatter(df_l.dropna(subset=['vo2Max']), x='Date', y='vo2Max', trendline="lowess", title="Fitness (VO2Max)"), use_container_width=True)
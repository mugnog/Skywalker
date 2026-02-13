#!/bin/bash 
cd /Users/mugnog/Downloads/AI_Fitness-main 
source venv/bin/activate 
python3 update_yesterday_garmin.py 
python3 update_yesterday_hevy.py 
streamlit run skywalker_dashboard.py
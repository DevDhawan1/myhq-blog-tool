@echo off
echo Starting myHQ Blog Drafting Tool...
cd /d "%~dp0"
python -m streamlit run app.py
pause

@echo off
REM Windows: schedule this with Task Scheduler (trigger: every 10 minutes, "run whether user is logged on").
REM Or run once from a terminal to register it:
REM   schtasks /create /tn "IdeaPipeline" /tr "\"%~f0\"" /sc minute /mo 10
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
python -m ideapipe run >> .state\run.log 2>&1

@echo off
setlocal

cd /d "%~dp0.."
python run_all.py --config config.json --web-config web_config.json

endlocal

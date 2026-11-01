import os, subprocess

startup_dir = os.path.expanduser('~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup')
bat_path = os.path.join(startup_dir, 'SK_Gold_AutoStart.bat')

content = """@echo off
cd /d "C:\\Users\\princ\\.gemini\\antigravity\\scratch\\trading_signal_app"
start "" wscript.exe "C:\\Users\\princ\\.gemini\\antigravity\\scratch\\trading_signal_app\\run_silent_background.vbs"
exit
"""

with open(bat_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Startup bat created successfully at:", bat_path)

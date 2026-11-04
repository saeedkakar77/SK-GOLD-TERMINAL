Set WshShell = CreateObject("WScript.Shell")
appDir = "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"
pyExe = "C:\Users\princ\AppData\Local\Programs\Python\Python312\python.exe"
nodeExe = "C:\Users\princ\tools\node\node.exe"

WshShell.CurrentDirectory = appDir

' Start server.py hidden (0 = hidden window) with full absolute path
WshShell.Run """" & pyExe & """ -u """ & appDir & "\server.py""", 0, False
WScript.Sleep 2500

' Start ngrok_tunnel.js hidden (0 = hidden window) with full absolute path
WshShell.Run """" & nodeExe & """ """ & appDir & "\ngrok_tunnel.js""", 0, False

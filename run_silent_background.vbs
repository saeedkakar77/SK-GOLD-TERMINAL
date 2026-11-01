Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"
WshShell.Run "cmd /c python server.py", 0, False
WScript.Sleep 2000
WshShell.Run "cmd /c node ngrok_tunnel.js", 0, False

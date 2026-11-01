import os
import sys
import json
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Protect stdout/stderr for windowless background execution and UTF-8 encoding
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
else:
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
else:
    try:
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

from core.engine import SignalEngine

# Initialize the master trading engine
engine = SignalEngine()

PORT = int(os.environ.get("PORT", 5000))
HTML_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

class TradingAppHandler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception:
            pass

    def _send_json(self, data, status=200):
        try:
            response = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception:
            pass

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/index.html":
                if os.path.exists(HTML_PATH):
                    with open(HTML_PATH, "r", encoding="utf-8") as f:
                        content = f.read().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.send_error(404, "index.html template not found")
            elif self.path == "/api/strategies":
                self._send_json(engine.get_strategy_statuses())
            elif self.path == "/api/market":
                self._send_json(engine.get_market_overview())
            elif self.path == "/api/signals":
                self._send_json({
                    "active": engine.get_active_signals(),
                    "history": engine.get_signal_history(),
                    "stats": engine.get_history_stats()
                })
            elif self.path == "/api/signals/active":
                self._send_json(engine.get_active_signals())
            elif self.path == "/api/signals/history":
                self._send_json(engine.get_signal_history())
            elif self.path == "/api/bias":
                self._send_json(engine.get_bias_report())
            elif self.path == "/api/pairs":
                self._send_json(engine.get_pairs())
            elif self.path == "/api/info":
                ip = get_local_ip()
                online_url = None
                url_file = os.path.join(os.path.dirname(__file__), "online_url.txt")
                if os.path.exists(url_file):
                    try:
                        with open(url_file, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content.startswith("http"):
                                online_url = content
                    except Exception:
                        pass
                self._send_json({
                    "pc_url": f"http://127.0.0.1:{PORT}",
                    "mobile_url": f"http://{ip}:{PORT}",
                    "online_url": online_url,
                    "local_ip": ip,
                    "port": PORT
                })
            elif self.path == "/manifest.json":
                manifest = {
                    "name": "SK Gold Institutional Terminal",
                    "short_name": "SK Gold",
                    "description": "16 SMC Strategies Real-Time Gold Terminal",
                    "start_url": "/",
                    "display": "standalone",
                    "orientation": "portrait",
                    "background_color": "#0b1120",
                    "theme_color": "#f59e0b",
                    "icons": [
                        {
                            "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>👑</text></svg>",
                            "sizes": "192x192 512x512",
                            "type": "image/svg+xml",
                            "purpose": "any maskable"
                        }
                    ]
                }
                self._send_json(manifest)
            elif self.path == "/sw.js":
                sw_script = "self.addEventListener('fetch', function(e) {});"
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", str(len(sw_script)))
                self.end_headers()
                self.wfile.write(sw_script.encode("utf-8"))
            else:
                self.send_error(404, "Endpoint not found")
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                payload = {}

            if self.path == "/api/strategies/toggle":
                strategy_id = payload.get("strategy_id")
                enabled = payload.get("enabled", True)
                if strategy_id:
                    engine.set_strategy_status(strategy_id, enabled)
                self._send_json({"status": "ok", "strategy_id": strategy_id, "enabled": enabled})

            elif self.path == "/api/market/select":
                symbol = payload.get("symbol")
                timeframe = payload.get("timeframe")
                if symbol:
                    engine.active_symbol = symbol
                if timeframe:
                    engine.active_timeframe = timeframe
                self._send_json({"status": "ok", "symbol": engine.active_symbol, "timeframe": engine.active_timeframe})

            elif self.path == "/api/test-signal":
                sig = engine.add_demo_signal()
                self._send_json({"status": "ok", "signal": sig})

            elif self.path == "/api/pairs/toggle":
                symbol = payload.get("symbol")
                enabled = payload.get("enabled")
                if symbol:
                    if enabled is None:
                        for p in engine.pairs:
                            if p["symbol"].upper() == symbol.upper():
                                enabled = not p["enabled"]
                                break
                    engine.set_pair_status(symbol, enabled if enabled is not None else True)
                self._send_json({"status": "ok", "symbol": symbol, "enabled": enabled})
            else:
                self.send_error(404, "Endpoint not found")
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def log_message(self, format, *args):
        # Keep console output clean
        return

def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def start_background_tunnel():
    """Keeps the worldwide online tunnel permanently connected and auto-reconnecting."""
    import re
    import subprocess
    import threading

    desktop_dir = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if not os.path.exists(desktop_dir):
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    url_file = os.path.join(os.path.dirname(__file__), "online_url.txt")
    desktop_shortcut = os.path.join(desktop_dir, "ONLINE_MOBILE_LINK.url")
    desktop_txt = os.path.join(desktop_dir, "ONLINE_MOBILE_LINK.txt")

    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
        "-R", "80:127.0.0.1:5000", "nokey@localhost.run"
    ]
    url_pattern = re.compile(r"https://[a-zA-Z0-9\.\-]+\.lhr\.life")

    while True:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in iter(proc.stdout.readline, ""):
                match = url_pattern.search(line)
                if match:
                    url = match.group(0)
                    print(f"\n[+] WORLDWIDE ONLINE URL ACTIVE: {url}", flush=True)
                    with open(url_file, "w", encoding="utf-8") as f:
                        f.write(url)
                    try:
                        with open(desktop_shortcut, "w", encoding="utf-8") as f:
                            f.write(f"[InternetShortcut]\nURL={url}\nIconIndex=0\n")
                        with open(desktop_txt, "w", encoding="utf-8") as f:
                            f.write(f"SK GOLD TERMINAL ONLINE WORLDWIDE LINK:\n{url}\n\nIs link ko apne mobile phone mein open karein (4G/5G/Wi-Fi kahin bhi).")
                    except Exception:
                        pass
            proc.wait()
        except Exception as e:
            print(f"[!] Tunnel background error: {e}", flush=True)
        import time
        time.sleep(5)

class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    # Start the signal analysis engine in background
    engine.start()

    # Start the automatic Worldwide Online Tunnel if on local PC
    is_cloud = bool(os.environ.get("RENDER") or os.environ.get("DYNO") or os.environ.get("KOYEB_APP_NAME") or os.environ.get("SPACE_ID"))
    if not is_cloud:
        import threading
        tunnel_thread = threading.Thread(target=start_background_tunnel, daemon=True)
        tunnel_thread.start()

    # Bind to 0.0.0.0 so PC and Mobile devices on local network can both connect
    server = ReusableThreadingServer(("0.0.0.0", PORT), TradingAppHandler)
    local_url = f"http://127.0.0.1:{PORT}"
    local_ip = get_local_ip()
    mobile_url = f"http://{local_ip}:{PORT}"

    print("=" * 65, flush=True)
    print(f"[*] SK INSTITUTIONAL TRADING TERMINAL (PC + MOBILE READY)!", flush=True)
    print(f"[*] PC Local URL:    {local_url}", flush=True)
    print(f"[*] Mobile Phone URL: {mobile_url} (Same Wi-Fi / Hotspot)", flush=True)
    print("=" * 65, flush=True)

    # Automatically open in user's browser
    try:
        webbrowser.open(local_url)
    except Exception:
        pass

    while True:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server...", flush=True)
            break
        except Exception as e:
            print(f"[Server Warning] Handled socket error: {e}", flush=True)
            import time
            time.sleep(0.5)
    
    engine.stop()
    try:
        server.server_close()
    except Exception:
        pass

if __name__ == "__main__":
    main()

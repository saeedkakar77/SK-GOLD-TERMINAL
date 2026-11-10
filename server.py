import os
import sys
import json
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Safe stdout/stderr writer for 24/7 windowless background execution
class SafeWriter:
    def __init__(self, log_path=None):
        self.log_file = None
        if log_path:
            try:
                self.log_file = open(log_path, "a", encoding="utf-8", buffering=1)
            except Exception:
                pass
    def write(self, s):
        if self.log_file:
            try:
                self.log_file.write(s)
            except Exception:
                pass
    def flush(self):
        if self.log_file:
            try:
                self.log_file.flush()
            except Exception:
                pass

log_dir = os.path.dirname(__file__)
sys.stdout = SafeWriter(os.path.join(log_dir, "server_stdout.log"))
sys.stderr = SafeWriter(os.path.join(log_dir, "server_stderr.log"))

import gzip
from core.engine import SignalEngine

# Initialize the master trading engine
engine = SignalEngine()

# Initialize 24/7 background auto-updater for live CME COMEX Gold Open Interest
try:
    from core.cme_fetcher import CMEGoldDataFetcher
    CMEGoldDataFetcher.start_background_updater()
except Exception:
    pass

PORT = int(os.environ.get("PORT", 5000))
HTML_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

class TradingAppHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

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
            accept_encoding = self.headers.get("Accept-Encoding", "")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("ngrok-skip-browser-warning", "true")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")

            # Compress JSON if client supports gzip and payload > 400 bytes
            if "gzip" in accept_encoding and len(response) > 400:
                compressed = gzip.compress(response, compresslevel=6)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(compressed)))
                self.end_headers()
                self.wfile.write(compressed)
            else:
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception:
            pass

    def do_GET(self):
        try:
            clean_path = self.path.split("?")[0].rstrip("/")
            if clean_path in ["", "/index.html"]:
                if os.path.exists(HTML_PATH):
                    with open(HTML_PATH, "r", encoding="utf-8") as f:
                        raw_content = f.read().encode("utf-8")
                    
                    accept_encoding = self.headers.get("Accept-Encoding", "")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("ngrok-skip-browser-warning", "true")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    
                    if "gzip" in accept_encoding:
                        compressed = gzip.compress(raw_content, compresslevel=6)
                        self.send_header("Content-Encoding", "gzip")
                        self.send_header("Content-Length", str(len(compressed)))
                        self.end_headers()
                        self.wfile.write(compressed)
                    else:
                        self.send_header("Content-Length", str(len(raw_content)))
                        self.end_headers()
                        self.wfile.write(raw_content)
                else:
                    self.send_error(404, "index.html template not found")
            elif clean_path == "/api/poll" or clean_path == "/api/state":
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
                    "market": engine.get_market_overview(),
                    "signals": {
                        "active": engine.get_active_signals(),
                        "history": engine.get_signal_history(),
                        "stats": engine.get_history_stats()
                    },
                    "bias": engine.get_bias_report(),
                    "info": {
                        "pc_url": f"http://127.0.0.1:{PORT}",
                        "mobile_url": f"http://{ip}:{PORT}",
                        "online_url": online_url,
                        "local_ip": ip,
                        "port": PORT
                    }
                })
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
            elif self.path in ["/api/cme/sync", "/api/cme/live"]:
                from core.cme_fetcher import CMEGoldDataFetcher
                cme_data = CMEGoldDataFetcher.get_cme_analysis(force_refresh=True)
                engine.cached_bias = None
                self._send_json({"status": "ok", "cme": cme_data})
            elif self.path == "/api/bias":
                self._send_json(engine.get_bias_report())
            elif self.path == "/api/pinescript":
                pine_file = os.path.join(os.path.dirname(__file__), "SK_PERFECT_ENTRY_WITH_LIVE_PNL_TRADINGVIEW.pine")
                script_txt = ""
                if os.path.exists(pine_file):
                    with open(pine_file, "r", encoding="utf-8") as pf:
                        script_txt = pf.read()
                self._send_json({"script": script_txt, "filename": "SK_PERFECT_ENTRY_WITH_LIVE_PNL_TRADINGVIEW.pine"})
            elif self.path == "/api/filter/status":
                self._send_json({
                    "strict_institutional_filter": engine.strict_institutional_filter,
                    "stats": engine.get_history_stats()
                })
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
                sw_script = """self.addEventListener('install', function(e) {
    self.skipWaiting();
});
self.addEventListener('activate', function(e) {
    e.waitUntil(self.clients.claim());
});
self.addEventListener('notificationclick', function(e) {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({ type: 'window' }).then(function(clientList) {
            for (var i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if ('focus' in client) return client.focus();
            }
            if (clients.openWindow) return clients.openWindow('/');
        })
    );
});
self.addEventListener('fetch', function(e) {});"""
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Cache-Control", "no-cache")
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
                if strategy_id == "all":
                    with engine.lock:
                        for s in engine.strategies.values():
                            s.enabled = bool(enabled)
                elif strategy_id:
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

            elif self.path == "/api/filter/toggle":
                strict = payload.get("strict")
                if strict is None:
                    engine.strict_institutional_filter = not engine.strict_institutional_filter
                else:
                    engine.strict_institutional_filter = bool(strict)
                self._send_json({"status": "ok", "strict_institutional_filter": engine.strict_institutional_filter})

            elif self.path in ["/api/cme/update", "/api/cme/sync"]:
                from core.cme_fetcher import CMEGoldDataFetcher
                updated_report = CMEGoldDataFetcher.update_cme_report(payload)
                engine.cached_bias = None
                self._send_json({"status": "ok", "cme": updated_report})

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
        except (KeyboardInterrupt, SystemExit):
            # In 24/7 background mode, ignore accidental launcher close interrupts
            import time
            time.sleep(1)
            continue
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

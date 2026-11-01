import os
import re
import sys
import time
import subprocess
import webbrowser

APP_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(APP_DIR, "online_url.txt")

# Desktop path detection
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
if not os.path.exists(DESKTOP_DIR):
    DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")

DESKTOP_URL_SHORTCUT = os.path.join(DESKTOP_DIR, "ONLINE_MOBILE_LINK.url")
DESKTOP_TXT_FILE = os.path.join(DESKTOP_DIR, "ONLINE_MOBILE_LINK.txt")
D_PERSONAL_DIR = r"D:\Personal"

def start_tunnel():
    print("=" * 65)
    print("   SK INSTITUTIONAL GOLD TERMINAL — WORLDWIDE TUNNEL")
    print("=" * 65)
    print("[*] Connecting to Worldwide Secure Edge Tunnel...")

    # Primary: Built-in Windows OpenSSH reverse proxy via localhost.run (IPv4 explicit 127.0.0.1)
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
        "-R", "80:127.0.0.1:5000", "nokey@localhost.run"
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        url_pattern = re.compile(r"https://[a-zA-Z0-9\.\-]+\.lhr\.life")
        start_time = time.time()
        for line in iter(proc.stdout.readline, ""):
            line_clean = line.strip()
            match = url_pattern.search(line_clean)
            if match:
                return match.group(0), proc
            if time.time() - start_time > 20:
                break
    except Exception as e:
        print(f"[!] Primary tunnel failed: {e}")

    # Fallback: Cloudflare quick tunnel if available
    cf_bin = os.path.join(APP_DIR, "cloudflared.exe")
    if os.path.exists(cf_bin):
        print("[*] Trying Cloudflare Edge Tunnel fallback...")
        try:
            cf_proc = subprocess.Popen(
                [cf_bin, "tunnel", "--url", "http://127.0.0.1:5000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            cf_pattern = re.compile(r"https://(?!api\.)[a-zA-Z0-9\-]+\.trycloudflare\.com")
            start_time = time.time()
            for line in iter(cf_proc.stdout.readline, ""):
                match = cf_pattern.search(line.strip())
                if match:
                    return match.group(0), cf_proc
                if time.time() - start_time > 20:
                    break
        except Exception:
            pass

    return None, None

def main():
    # Clear previous online url
    if os.path.exists(URL_FILE):
        try:
            os.remove(URL_FILE)
        except Exception:
            pass

    found_url, proc = start_tunnel()
    if not found_url:
        print("\n[!] Tunnel connect nahi ho saka. Internet connection check karein.")
        input("Press Enter to exit...")
        return

    # 1. Save locally for server.py API
    with open(URL_FILE, "w", encoding="utf-8") as f:
        f.write(found_url)

    # 2. Save Desktop .url Internet Shortcut
    shortcut_content = f"[InternetShortcut]\nURL={found_url}\nIconIndex=0\n"
    try:
        with open(DESKTOP_URL_SHORTCUT, "w", encoding="utf-8") as f:
            f.write(shortcut_content)
    except Exception:
        pass

    # 3. Save Desktop text instructions
    txt_content = (
        "===========================================================\n"
        "   SK INSTITUTIONAL GOLD TERMINAL — WORLDWIDE ONLINE LINK  \n"
        "===========================================================\n\n"
        f"Aap ka 24/7 Worldwide Online Link:\n{found_url}\n\n"
        "Is link ko aap dunya mein kahin bhi hon, 4G/5G mobile data ya kisi\n"
        "bhi Wi-Fi par apne mobile browser (Chrome/Safari) mein open kar sakte hain!\n\n"
        "Mobile App banane ka tareeqa:\n"
        "1. Apne mobile phone par ye link open karein.\n"
        "2. Browser menu khol kar 'Add to Home Screen' ya 'Install App' tap karein.\n"
        "3. Ye direct aapke phone par native app ban jayegi aur audio alerts degi!\n"
    )
    try:
        with open(DESKTOP_TXT_FILE, "w", encoding="utf-8") as f:
            f.write(txt_content)
    except Exception:
        pass

    # 4. Copy to D:\Personal if available
    if os.path.exists(D_PERSONAL_DIR):
        try:
            with open(os.path.join(D_PERSONAL_DIR, "ONLINE_MOBILE_LINK.txt"), "w", encoding="utf-8") as f:
                f.write(txt_content)
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(" [SUCCESS] AAP KA WORLDWIDE ONLINE LINK ACTIVE HAI!")
    print(f" [URL]     {found_url}")
    print("=" * 65)
    print("[*] Desktop Shortcut: ONLINE_MOBILE_LINK.url")
    print("[*] Desktop Instructions: ONLINE_MOBILE_LINK.txt")
    print("[*] Ye window minimized rakhein taake tunnel active rahe.")
    print("=" * 65 + "\n")

    # Automatically open in browser
    try:
        webbrowser.open(found_url)
    except Exception:
        pass

    # Keep tunnel process alive
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()

if __name__ == "__main__":
    main()

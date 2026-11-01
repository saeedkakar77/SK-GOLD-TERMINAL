# 👑 SK Institutional Gold Trading Terminal (V2.2)

> **24/7 Institutional Gold (XAUUSD) Real-Time Scanner**  
> Powered by 16 Smart Money Concepts (SMC) & ICT Algorithms, TradingView Pro Live Chart, and TradeNuro-Style Audio & Push Notifications.

---

## 🌟 Key Features

1. **👑 100% Pure Gold (XAUUSD) Focus:**
   * Precision scanning engineered exclusively for Spot Gold & Futures.
   * Multi-timeframe execution: M3, M5, M15, M30, H1, H4, Daily, Weekly, Monthly.

2. **📊 TradingView Pro Advanced Live Chart:**
   * Embedded official real-time TradingView Chart (`OANDA:XAUUSD`).
   * Complete professional technical drawing tools toolbar (Trendlines, Fibonacci, Pitchforks, Zones).
   * Multiple timeframe switching directly inside the chart.
   * Pre-configured RSI and MACD indicators with custom indicator support.

3. **⚙️ 16 SMC Institutional Strategies Daba (Popup Box):**
   * Neatly organized into a popup modal drawer so your chart view remains clutter-free.
   * Individual ON/OFF switches for each strategy.
   * Quick `ALL ON` and `ALL OFF` master toggles.
   * Strategies include:
     1. True Order Block (OB) Retest with FVG Origin
     2. Fair Value Gap (FVG) 50% CE Retest
     3. SMT Divergence (Gold vs Silver / DXY)
     4. Session Liquidity Sweep (Turtle Soup)
     5. HTF Major Liquidity Sweep (1H, 4H, 1D)
     6. EMA 144 Channel Retest + 5/8/13/21 Cross
     7. Price Action Structure: IDM + Valid OB (OTE)
     8. SMC Structure: IDM OB & EXT OB
     9. DEMA 21/89 Cross & Retest (M5 / M15)
     10. MSNR: CL, OCL, SBR & RBS Flips (M30 - Monthly)
     11. Cascaded WMA Directional Volume Divergence
     12. AOX Model: NY Expansion + Mandatory Vol Div (M5)
     13. CRT Setup: C1-C2-C3 Candle Range Theory Multi-TF
     14. EF Setup: Failed Engulfing Retest + Vol Div
     15. BBMA Oma Ally Multi-TF Triads (REM, RRE, REE, RMEE)
     16. Unicorn Setup: Breaker Block + iFVG + Multi-Candle Confirmation

4. **🔔 TradeNuro Audio & Push Notification System:**
   * Multi-tone institutional chime synthesis (Web Audio API) for Buy, Sell, and TP hits.
   * Hardware vibration on mobile phones (`navigator.vibrate`).
   * Sliding in-app notification banner at the top of the terminal.
   * Background Push Notifications via Service Worker (`sw.js`).
   * Win/Loss History Tracker with TP1 (1:1.5 RR) and TP2 (1:3.0 RR) performance scorecard.

5. **📱 Mobile Ready (Progressive Web App):**
   * Open the link on any Android or iPhone and tap **"Add to Home Screen"** or **"Install App"**.
   * Runs in full-screen standalone mode like a native app.

---

## 🚀 How to Run Locally

```bash
# 1. Clone repository
git clone https://github.com/saeedkakar77/SK-GOLD-TERMINAL.git
cd SK-GOLD-TERMINAL

# 2. Install dependencies (Optional / Minimal)
pip install -r requirements.txt

# 3. Start Terminal Server
python server.py
# Or double-click "run_online_worldwide.bat" on Windows
```

---

## 🌐 Online Access

* **Local PC:** `http://127.0.0.1:5000`
* **Local Wi-Fi:** `http://<your-local-ip>:5000`
* **Worldwide Online:** Works seamlessly with Ngrok, Localhost.run, or Docker cloud providers.

---

## 📜 License
Private & Proprietary © Saeed Kakar. All Rights Reserved.

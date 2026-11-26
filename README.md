# 👑 SK Institutional Gold Terminal (V2.3)
**17 SMC Strategies + Hunter AI · XAUUSD Exclusive · 7-AI Council**

---

## 🚀 Quick Start

```powershell
cd C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app
python app.py
```

Dashboard opens at: `http://localhost:5000`

---

## 🎯 Hunter AI Bias Bar (Main Feature)

The dashboard now shows **one clear bias** at the top — no confusion:

| Element | Description |
|---|---|
| 🟢 **BUY % bar** | Live probability of bullish move today |
| 🔴 **SELL %** | Live probability of bearish move |
| **Urdu Reason** | Plain-language explanation below the bar |
| **CRT Row** | Previous Day High/Low + Previous Week High/Low |

**Example output:**
> `🟢 AAJ BUY PREFER KAREIN (61% BUY / 39% SELL)`

The Hunter AI reads:
- **Daily CRT** (Prev Day High/Low breakout)
- **Weekly CRT** (Prev Week High/Low range)
- **Daily & Weekly HTF Bias**
- **All 17 Strategy votes** (Bull% vs Bear%)

---

## 📊 Show Detailed Analysis Toggle

Click **"📊 Show Detailed Analysis"** button to expand:
- 🏛️ CME COMEX Gold Open Interest card
- 4-Timeframe Bias grid (Monthly / Weekly / Daily / H4)
- All 17 strategy live votes breakdown

Click **"🔼 Hide Detailed Analysis"** to collapse and keep dashboard clean.

---

## 🤖 17 Institutional SMC Strategies

| # | Strategy | Type |
|---|---|---|
| 1 | CME Open Interest (400K Benchmark) | Market Structure |
| 2 | FVG (Fair Value Gap) | Price Action |
| 3 | Order Block (OB) | Smart Money |
| 4 | Unicorn Breaker | Advanced SMC |
| 5 | CRT (Candle Range Theory) | Range |
| 6 | Liquidity Sweep | Liquidity |
| 7 | SMT (Smart Money Tool) | Divergence |
| 8 | AOX | Momentum |
| 9 | BBMA (Bollinger Band Moving Avg) | Trend |
| 10 | DEMA (Double EMA) | Trend |
| 11 | MSNR | Session |
| 12 | IDM (Inducement) | Liquidity |
| 13 | EF (Equal Highs/Lows) | Liquidity |
| 14 | Vol Div (Volume Divergence) | Volume |
| 15 | HTF Liquidity | Multi-TF |
| 16 | SMC-IDM-EXT | Advanced SMC |
| 17 | **Quant Pilot 7-AI Liquidity Sweep & Displacement** | AI Composite |

---

## 🛡️ 7-AI Council

| Agent | Role |
|---|---|
| 📡 AI 1: Scout | Live market feed & spread inspector |
| 🗺️ AI 2: Cartographer | Liquidity pool & HTF range mapper |
| 🎯 AI 3: Hunter | 17-strategy A+ signal scanner |
| 🔬 AI 4: Analyst | CME 400K+ whale flow scorer |
| 🛡️ AI 5: Guardian | Capital & drawdown protector |
| ⚡ AI 6: Executioner | Direct MT5 order sniper |
| 📜 AI 7: Chronicler | Trade journal & auditor |

---

## ⚙️ Trading Modes

| Mode | Description |
|---|---|
| 🟡 Paper Simulation | No real orders — test only |
| 🔵 1-Click Approval | Manual confirm before MT5 execution |
| 🟢 Full Auto MT5 | Auto-fire on every A+ signal (requires Algo Trading ON in MT5) |

> ⚠️ **MT5 Algo Trading must be manually enabled in the terminal** — it is never auto-enabled by this app.

---

## 📡 Key API Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/council/status` | Full 7-AI council state + Hunter briefing (`buy_pct`, `sell_pct`) |
| `GET /api/bias` | 4-TF HTF bias + CME + 16-strategy compass |
| `GET /api/signals` | Active A+ signals + history |
| `GET /api/market` | Live XAUUSD price, spread, session |
| `GET /api/poll` | Unified lightweight fast-poll (every 2s) |
| `POST /api/mt5/execute` | Submit order to MT5 |
| `POST /api/cme/update` | Update CME OI data manually |

---

## 💾 D-Drive Backup

Backups are stored at: `D:\SK_Gold_Backups\`

Run backup manually:
```powershell
python backup_battle.py
```

---

## 🔀 Git History

```
2c65f8a feat: Add Hunter AI Daily/Weekly CRT & Bias BUY/SELL Briefing on Dashboard
df4c6ca feat: Add 17th strategy (Quant Pilot 7-AI Liquidity Sweep & Displacement)
a5eb54f feat: 7-AI council now reads live 16-SMC+CME rules
dc8d124 feat: Add dedicated MT5 Algo Accounts & %/$ Risk Settings page
7adba4a revert: Restore original SK Gold Terminal design
```

---

*Last updated: 2026-11-27 · V2.3 · 17 Strategies + Hunter AI Bias Bar*

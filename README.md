# SK Perfect Trading Signal Terminal (Gold & Forex)

Standalone Python trading signal application for Gold (XAUUSD) and Forex pairs based on ICT / Smart Money Concepts (SMC) and EMA Multi-Confluence.

## Folder Structure
```
trading_signal_app/
│
├── core/
│   ├── models.py             # Signal & Candle data structures
│   ├── data_feed.py          # MetaTrader 5 (MT5) connector + live market fallback
│   └── engine.py             # Background scanner & signal processor
│
├── strategies/               # All individual strategies
│   ├── base_strategy.py      # Base template for all strategies
│   ├── strategy_orderblock.py      # Strategy 1: True Order Block (OB) Retest
│   ├── strategy_fvg.py             # Strategy 2: Fair Value Gap (FVG) Retest
│   ├── strategy_smt.py             # Strategy 3: SMT Divergence (Gold vs Silver/DXY)
│   ├── strategy_liquidity_sweep.py # Strategy 4: Session Liquidity Sweep (Turtle Soup)
│   └── strategy_ema_ribbon.py      # Strategy 5: EMA 144 Retest + 5/8/13/21 EMA Cross
│
├── templates/
│   └── index.html            # Dark-theme Web Dashboard with Audio Alarms
│
├── server.py                 # Lightweight zero-dependency Python server
└── start_app.bat             # 1-Click launcher
```

## How to Run
1. Double-click **`start_app.bat`** (or open command prompt and run `python server.py`).
2. Browser automatically opens at: `http://127.0.0.1:5000`.
3. Click **"🔔 Test Sound & Alert"** to test loud audio chime and signal card display.

## How to add future strategies (One-by-One)
1. Add a new file inside `strategies/` (e.g. `strategy_macd.py`) inheriting from `BaseStrategy`.
2. Register it in `core/engine.py`.
3. It will automatically show up on the dashboard with its own toggle switch!

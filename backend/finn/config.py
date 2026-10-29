"""Static configuration: the mock portfolio, demo research set and default watch rules."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("FINN_DATA_DIR", ROOT / "data"))
SEED_DIR = Path(os.environ.get("FINN_SEED_DIR", ROOT / "seed"))
WEB_DIST = ROOT / "web" / "dist"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 18 names chosen for spread: mega-cap anchors, a lender, a PSU, mid-cap compounders
# and two volatile small/mid manufacturers that actually trip alerts.
PORTFOLIO = [
    {"symbol": "RELIANCE", "sector": "Energy & Telecom", "size": "Mega"},
    {"symbol": "HDFCBANK", "sector": "Private Bank", "size": "Mega", "lender": True},
    {"symbol": "BHARTIARTL", "sector": "Telecom", "size": "Mega"},
    {"symbol": "TCS", "sector": "IT Services", "size": "Mega"},
    {"symbol": "LT", "sector": "Engineering & Construction", "size": "Large"},
    {"symbol": "SUNPHARMA", "sector": "Pharma", "size": "Large"},
    {"symbol": "MARUTI", "sector": "Autos", "size": "Large"},
    {"symbol": "BAJFINANCE", "sector": "NBFC", "size": "Large", "lender": True},
    {"symbol": "TITAN", "sector": "Consumer", "size": "Large"},
    {"symbol": "DMART", "sector": "Retail", "size": "Large"},
    {"symbol": "ETERNAL", "sector": "Internet", "size": "Large"},
    {"symbol": "TRENT", "sector": "Retail", "size": "Large"},
    {"symbol": "HAL", "sector": "Defence PSU", "size": "Large"},
    {"symbol": "POLYCAB", "sector": "Cables & Wires", "size": "Mid"},
    {"symbol": "PERSISTENT", "sector": "IT Services", "size": "Mid"},
    {"symbol": "DIXON", "sector": "Electronics Mfg", "size": "Mid"},
    {"symbol": "DEEPAKNTR", "sector": "Chemicals", "size": "Mid"},
    {"symbol": "KAYNES", "sector": "Electronics Mfg", "size": "Small"},
]
PORTFOLIO_SYMBOLS = [p["symbol"] for p in PORTFOLIO]
LENDERS = {p["symbol"] for p in PORTFOLIO if p.get("lender")} | {
    "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB",
    "CHOLAFIN", "SHRIRAMFIN", "MUTHOOTFIN", "BAJAJFINSV", "LICHSGFIN", "PFC", "RECLTD",
}

# Outside the portfolio, picked to stress the pull side: two that give explicit
# numeric guidance (KPIT, IndiGo), two that mostly talk in direction (Pidilite, Astral).
RESEARCH_DEMO = ["KPITTECH", "INDIGO", "PIDILITIND", "ASTRAL"]

DEFAULT_RULES = {
    "price_pct": 4.0,        # |daily move| beyond this %
    "vol_mult": 2.0,         # volume vs 20-session average
    "sigma": 2.5,            # move vs the stock's own 60-day volatility
    "use_sigma": True,
    "categories": ["results", "M&A", "management_change", "fund_raise", "litigation",
                   "credit_rating", "pledging", "bonus_split", "capex"],
    "min_score": 65,
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

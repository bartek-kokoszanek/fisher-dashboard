"""Konfiguracja dashboardu Fishera: uniwersum spolek i wagi scoringu.

Tickery w formacie Yahoo Finance:
  - Nasdaq: zwykly symbol, np. "AAPL", "MSFT"
  - GPW:    symbol z sufiksem ".WA", np. "PKN.WA", "CDR.WA"

Mozesz swobodnie dopisywac/usuwac spolki ponizej.
"""

# --- Uniwersum Nasdaq (przyklad: duze spolki wzrostowe/technologiczne) ---
NASDAQ = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "ADBE",
    "AMD", "INTC", "QCOM", "TXN", "AMAT", "LRCX", "ASML", "COST",
    "PEP", "CSCO", "INTU", "NOW", "PANW", "SNPS", "CDNS", "REGN",
]

# --- Uniwersum GPW: wszystkie spolki z WIG20 + mWIG40 + sWIG80 (~140) ---
# Sklady indeksow w gpw_indices.py (generowane; aktualizacja: patrz README).
# Spolki spoza indeksow ("WIG-pozostale") dociagane sa leniwie w aplikacji.
import gpw_indices as _gi

GPW = sorted(_gi.WIG20 | _gi.MWIG40 | _gi.SWIG80)

# Mapowanie tickera -> czytelna nazwa: baza z katalogu GPW + ladniejsze nadpisania
from gpw_tickers import GPW_TICKERS as _GPW_NAMES

NAMES = {
    **_GPW_NAMES,
    "PKN.WA": "Orlen", "PKO.WA": "PKO BP", "PEO.WA": "Bank Pekao",
    "PZU.WA": "PZU", "KGH.WA": "KGHM", "CDR.WA": "CD Projekt",
    "DNP.WA": "Dino Polska", "ALE.WA": "Allegro", "LPP.WA": "LPP",
    "CPS.WA": "Cyfrowy Polsat", "MBK.WA": "mBank",
    "OPL.WA": "Orange Polska", "KTY.WA": "Grupa Kety",
    "BDX.WA": "Budimex", "ATT.WA": "Grupa Azoty", "TXT.WA": "Text SA",
}

# --- Wagi metryk ilosciowych (proxy dla 15 punktow Fishera) ---
# Suma wag = 100. Metryki opisane w fisher_score.py
WEIGHTS = {
    "revenue_cagr":       18,  # trwaly wzrost sprzedazy (pkt 1)
    "revenue_growth_yoy": 10,  # dynamika ostatniego roku
    "gross_margin":        8,  # jakosc produktu (pkt 5)
    "operating_margin":   12,  # rentownosc operacyjna (pkt 5)
    "margin_trend":       10,  # obrona/poprawa marz (pkt 6)
    "rnd_intensity":      12,  # nacisk na R&D (pkt 2, 3)
    "roe":                12,  # jakosc / przewaga (pkt 11)
    "fcf_margin":         10,  # konwersja gotowki
    "low_dilution":        4,  # brak rozwadniania (pkt 13)
    "low_leverage":        4,  # bezpieczny bilans (pkt 13)
}

# Banki/ubezpieczyciele maja inna strukture sprawozdan (brak "przychodow"
# w klasycznym sensie, brak R&D). Oznaczamy je, by nie karac ich sztucznie.
FINANCIALS = {"PKO.WA", "PEO.WA", "PZU.WA", "MBK.WA"}

# Katalog cache
CACHE_DIR = "data"


def all_tickers():
    return NASDAQ + GPW


def market_of(ticker: str) -> str:
    return "GPW" if ticker.endswith(".WA") else "Nasdaq"

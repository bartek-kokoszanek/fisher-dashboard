"""Pelna pula symboli Nasdaq + NYSE + GPW do wyszukiwarki.

- Nasdaq: oficjalny katalog nasdaqlisted.txt z nasdaqtrader.com,
  pobierany i cache'owany lokalnie na 7 dni (data/nasdaqlisted.txt).
- NYSE: statyczna lista w nyse_tickers.py (glowny parkiet, wygenerowana
  z otherlisted.txt; ~2800 spolek, bez warrantow/jednostek/praw).
- GPW: statyczna lista w gpw_tickers.py (generowana z katalogu spolek;
  ~370 spolek rynku glownego).

Wyszukiwanie zwraca dopasowania po tickerze lub fragmencie nazwy.
Spolki wybrane z puli sa pobierane i punktowane on-demand — nie skanujemy
hurtowo calych gield (limity Yahoo).
"""
from __future__ import annotations

import os
import time

import requests

import config
from gpw_tickers import GPW_TICKERS

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_CACHE = os.path.join(config.CACHE_DIR, "nasdaqlisted.txt")
NASDAQ_TTL = 7 * 24 * 3600  # 7 dni


def _download_nasdaq() -> str:
    r = requests.get(NASDAQ_URL, timeout=30)
    r.raise_for_status()
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(NASDAQ_CACHE, "w", encoding="utf-8") as f:
        f.write(r.text)
    return r.text


def nasdaq_symbols() -> dict[str, str]:
    """{ticker: nazwa} dla wszystkich spolek notowanych na Nasdaq."""
    text = None
    if os.path.exists(NASDAQ_CACHE):
        if time.time() - os.path.getmtime(NASDAQ_CACHE) < NASDAQ_TTL:
            with open(NASDAQ_CACHE, "r", encoding="utf-8") as f:
                text = f.read()
    if text is None:
        try:
            text = _download_nasdaq()
        except Exception:
            # offline / blad sieci: uzyj przeterminowanego cache, jesli jest
            if os.path.exists(NASDAQ_CACHE):
                with open(NASDAQ_CACHE, "r", encoding="utf-8") as f:
                    text = f.read()
            else:
                return {}

    out = {}
    for line in text.splitlines()[1:]:  # naglowek
        parts = line.split("|")
        if len(parts) < 4 or parts[0] == "" or line.startswith("File Creation"):
            continue
        symbol, name, _category, test_issue = parts[0], parts[1], parts[2], parts[3]
        if test_issue == "Y":  # instrumenty testowe
            continue
        out[symbol] = name
    return out


def nyse_symbols() -> dict[str, str]:
    from nyse_tickers import NYSE_TICKERS
    return dict(NYSE_TICKERS)


def gpw_symbols() -> dict[str, str]:
    return dict(GPW_TICKERS)


def all_symbols() -> dict[str, str]:
    """Pelna pula {ticker: nazwa}: Nasdaq + NYSE + GPW + reszta S&P500.

    Nasdaq i NYSE (glowny parkiet) pokrywaja niemal cale S&P500, ale
    pojedyncze spolki (np. CBOE — notowana poza obu katalogami) nie
    laduja sie w zadnym z nich — dogrywamy je z osobnej, statycznej
    listy S&P500, zeby nic nie znikalo z wyszukiwarki.
    """
    pool = nasdaq_symbols()
    pool.update(nyse_symbols())
    pool.update(gpw_symbols())
    from sp500_tickers import SP500
    for tk, name in SP500.items():
        pool.setdefault(tk, name)
    return pool


def search(query: str, pool: dict[str, str] | None = None, limit: int = 30):
    """Dopasowania po tickerze lub fragmencie nazwy. Zwraca [(ticker, nazwa)]."""
    if pool is None:
        pool = all_symbols()
    q = query.strip().upper()
    if not q:
        return []
    starts, contains = [], []
    for tk, name in pool.items():
        tk_base = tk.replace(".WA", "")
        if tk_base.startswith(q) or tk.startswith(q):
            starts.append((tk, name))
        elif q in name.upper():
            contains.append((tk, name))
    starts.sort(key=lambda x: len(x[0]))
    return (starts + sorted(contains))[:limit]


if __name__ == "__main__":
    pool = all_symbols()
    print(f"Nasdaq: {len(nasdaq_symbols())}, GPW: {len(gpw_symbols())}, razem: {len(pool)}")
    for q in ("MU", "MICRON", "DINO", "ORLEN"):
        print(f"\n'{q}':", search(q, pool, limit=5))

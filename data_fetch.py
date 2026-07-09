"""Pobieranie danych fundamentalnych i cenowych.

Zrodla (darmowe):
  - yfinance : fundamenty (rachunek wynikow, bilans, cash flow) dla Nasdaq i GPW
  - stooq     : ceny GPW jako fallback / weryfikacja (CSV, bez limitow API)

Wynik dla kazdej spolki to slownik surowych metryk, ktory potem trafia
do fisher_score.compute_score(). Dane sa cache'owane do data/raw_<ticker>.json,
zeby nie odpytywac API przy kazdym odswiezeniu dashboardu.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import config


def _cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    safe = ticker.replace(".", "_")
    return os.path.join(config.CACHE_DIR, f"raw_{safe}.json")


def _row(df: pd.DataFrame, *keywords: str):
    """Zwraca wiersz sprawozdania, ktorego etykieta zawiera podane slowa.

    yfinance bywa niespojny w nazwach wierszy miedzy spolkami, wiec
    szukamy po fragmencie (case-insensitive), a nie po dokladnej nazwie.
    Zwraca pandas.Series (kolumny = kolejne lata) albo None.
    """
    if df is None or df.empty:
        return None
    for label in df.index:
        low = str(label).lower()
        if all(k.lower() in low for k in keywords):
            return df.loc[label]
    return None


def _latest(series) -> float | None:
    if series is None:
        return None
    s = series.dropna()
    if s.empty:
        return None
    # kolumny yfinance sa posortowane malejaco po dacie -> pierwsza = najnowsza
    return float(s.iloc[0])


def _oldest(series) -> float | None:
    if series is None:
        return None
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _cagr(series) -> float | None:
    """Roczna stopa wzrostu (CAGR) miedzy najstarsza a najnowsza wartoscia."""
    if series is None:
        return None
    s = series.dropna()
    if len(s) < 2:
        return None
    newest = float(s.iloc[0])
    oldest = float(s.iloc[-1])
    years = len(s) - 1
    if oldest <= 0 or newest <= 0 or years <= 0:
        return None
    return (newest / oldest) ** (1 / years) - 1


def fetch_raw(ticker: str) -> dict:
    """Pobiera i ekstrahuje surowe metryki dla jednej spolki."""
    t = yf.Ticker(ticker)

    try:
        info = t.get_info()
    except Exception:
        info = {}

    inc = getattr(t, "income_stmt", None)
    bal = getattr(t, "balance_sheet", None)
    cf = getattr(t, "cashflow", None)

    revenue = _row(inc, "total", "revenue")
    if revenue is None:
        revenue = _row(inc, "revenue")
    gross = _row(inc, "gross", "profit")
    op_income = _row(inc, "operating", "income")
    net_income = _row(inc, "net", "income")
    rnd = _row(inc, "research", "development")

    equity = _row(bal, "stockholders", "equity")
    if equity is None:
        equity = _row(bal, "total", "equity")
    total_debt = _row(bal, "total", "debt")
    shares = _row(bal, "ordinary", "shares", "number")
    if shares is None:
        shares = _row(bal, "share", "issued")

    fcf = _row(cf, "free", "cash", "flow")

    rev_latest = _latest(revenue)
    rev_cagr = _cagr(revenue)

    # dynamika r/r z dwoch ostatnich lat
    rev_yoy = None
    if revenue is not None:
        s = revenue.dropna()
        if len(s) >= 2 and float(s.iloc[1]) > 0:
            rev_yoy = float(s.iloc[0]) / float(s.iloc[1]) - 1

    def margin(num_series):
        n, r = _latest(num_series), rev_latest
        if n is None or not r:
            return None
        return n / r

    # trend marzy operacyjnej: najnowsza minus najstarsza
    op_margin_trend = None
    if op_income is not None and revenue is not None:
        oi, rv = op_income.dropna(), revenue.dropna()
        if not oi.empty and not rv.empty and float(rv.iloc[0]) > 0 and float(rv.iloc[-1]) > 0:
            newest_m = float(oi.iloc[0]) / float(rv.iloc[0])
            oldest_m = float(oi.iloc[-1]) / float(rv.iloc[-1])
            op_margin_trend = newest_m - oldest_m

    # rozwodnienie: wzrost liczby akcji (dodatni = rozwadnia = zle)
    dilution = None
    if shares is not None:
        s = shares.dropna()
        if len(s) >= 2 and float(s.iloc[-1]) > 0:
            dilution = float(s.iloc[0]) / float(s.iloc[-1]) - 1

    roe = None
    ni, eq = _latest(net_income), _latest(equity)
    if ni is not None and eq and eq > 0:
        roe = ni / eq
    if roe is None and info.get("returnOnEquity") is not None:
        roe = info.get("returnOnEquity")

    debt_to_equity = None
    td = _latest(total_debt)
    if td is not None and eq and eq > 0:
        debt_to_equity = td / eq
    if debt_to_equity is None and info.get("debtToEquity") is not None:
        # yfinance podaje w procentach
        debt_to_equity = info.get("debtToEquity") / 100.0

    # zwrot ~6-miesieczny (momentum dla strategii typu Simons)
    return_6m = None
    try:
        hist = t.history(period="7mo")["Close"].dropna()
        if len(hist) >= 100:
            return_6m = float(hist.iloc[-1] / hist.iloc[0] - 1)
    except Exception:
        pass

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    target_mean = info.get("targetMeanPrice")
    target_upside = None
    if price and target_mean:
        target_upside = target_mean / price - 1

    raw = {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or config.NAMES.get(ticker, ticker),
        "market": config.market_of(ticker),
        "sector": info.get("sector"),
        "currency": info.get("currency"),
        "price": price,
        "market_cap": info.get("marketCap"),
        "website": info.get("website"),
        # --- konsensus analitykow (dla GPW czesto brak - zostaje None) ---
        "target_mean": target_mean,
        "target_upside": target_upside,
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "recommendation_mean": info.get("recommendationMean"),
        "recommendation_key": info.get("recommendationKey"),
        "trailing_pe": info.get("trailingPE"),
        "return_6m": return_6m,
        "is_financial": ticker in config.FINANCIALS or (info.get("sector") == "Financial Services"),
        # metryki wejsciowe do scoringu:
        "revenue_cagr": rev_cagr,
        "revenue_growth_yoy": rev_yoy,
        "gross_margin": margin(gross),
        "operating_margin": margin(op_income),
        "net_margin": margin(net_income),
        "margin_trend": op_margin_trend,
        "rnd_intensity": (margin(rnd) if rnd is not None else 0.0),
        "roe": roe,
        "fcf_margin": margin(fcf),
        "dilution": dilution,
        "debt_to_equity": debt_to_equity,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return raw


def get(ticker: str, max_age_hours: float = 24.0, force: bool = False) -> dict:
    """Zwraca dane spolki z cache lub swiezo z API."""
    path = _cache_path(ticker)
    if not force and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = datetime.fromisoformat(cached["fetched_at"])
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            # "return_6m" in cached = wersjonowanie schematu: starsze cache
            # (sprzed momentum/kolumn analitykow) sa odswiezane automatycznie
            if age <= max_age_hours and "return_6m" in cached:
                return cached
        except Exception:
            pass

    raw = fetch_raw(ticker)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    return raw


def get_many(tickers, force=False, sleep=0.4, progress=None):
    out = []
    for i, tk in enumerate(tickers):
        try:
            out.append(get(tk, force=force))
        except Exception as e:
            out.append({"ticker": tk, "name": config.NAMES.get(tk, tk),
                        "market": config.market_of(tk), "error": str(e)})
        if progress:
            progress(i + 1, len(tickers), tk)
        if force:
            time.sleep(sleep)  # nie DDoS-ujemy Yahoo
    return out


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(json.dumps(get(tk, force=True), ensure_ascii=False, indent=2))

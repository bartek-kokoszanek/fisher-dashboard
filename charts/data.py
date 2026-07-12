"""Historia finansowa spolki dla wykresow (z obecnego zrodla: yfinance).

Zwraca slownik serii {metryka: {rok: wartosc}} + dywidendy + roczne PE.
UWAGA: darmowy yfinance daje ~5 lat rocznych sprawozdan (nie 10) — bierzemy
ile jest. Dywidendy i ceny (PE) siegaja dalej. Wynik cache'owany 24h do
data/hist_<ticker>.json. Brakujace metryki po prostu nie wystepuja w slowniku.

Ceny: obok Yahoo dostepne jest alternatywne zrodlo Stooq (darmowe CSV, bez
klucza; GPW i USA) — get_prices(ticker, source). Fundamenty (sprawozdania,
prognozy analitykow) maja tylko zrodlo Yahoo — darmowej alternatywy brak.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import config

TTL_H = 24
SCHEMA = 2  # v2: ceny tygodniowe za caly dostepny okres (Max), nie tylko 6 lat


def _cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"hist_{ticker.replace('.', '_')}.json")


def _num(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _row(df, *keywords, exact=None):
    if df is None or getattr(df, "empty", True):
        return None
    for label in df.index:
        low = str(label).lower()
        if exact is not None:
            if str(label) == exact:
                return df.loc[label]
        elif all(k.lower() in low for k in keywords):
            return df.loc[label]
    return None


def _first(*rows):
    """Pierwszy nie-None wiersz (unika ambiwalencji bool(Series))."""
    for r in rows:
        if r is not None:
            return r
    return None


def _series_by_year(row) -> dict:
    """pandas.Series (kolumny = daty sprawozdan) -> {rok: wartosc}."""
    out = {}
    if row is None:
        return out
    for col, val in row.items():
        v = _num(val)
        if v is not None:
            try:
                out[int(col.year)] = v
            except AttributeError:
                pass
    return out


def _ratio(num_by_year: dict, den_by_year: dict) -> dict:
    out = {}
    for y, n in num_by_year.items():
        d = den_by_year.get(y)
        if _num(n) is not None and _num(d) not in (None, 0):
            out[y] = n / d
    return out


def _diff(a: dict, b: dict) -> dict:
    out = {}
    for y in set(a) | set(b):
        av, bv = a.get(y), b.get(y)
        if _num(av) is not None or _num(bv) is not None:
            out[y] = (av or 0) - (bv or 0)
    return out


def _fetch_forecast(t, revenue: dict, eps: dict) -> dict:
    """Prognozy analitykow z yfinance: przychody i EPS na 0y/+1y + cena docelowa.

    Darmowe dane siegaja zwykle 2 lat naprzod (biezacy rok obrachunkowy '0y'
    i nastepny '+1y'). Mapujemy je na lata kalendarzowe po ostatnim roku historii.
    """
    out = {"revenue": {}, "eps": {}, "price_target": {}}
    base = max(revenue) if revenue else (max(eps) if eps else None)
    if base is None:
        return out
    period_year = {"0y": base + 1, "+1y": base + 2}

    def _estim(df, target):
        if df is None or getattr(df, "empty", True):
            return
        for period, yr in period_year.items():
            if period in df.index:
                row = df.loc[period]
                avg = _num(row.get("avg"))
                if avg is None:
                    continue
                target[yr] = {"avg": avg, "low": _num(row.get("low")),
                              "high": _num(row.get("high")),
                              "n": _num(row.get("numberOfAnalysts"))}

    try:
        _estim(t.revenue_estimate, out["revenue"])
    except Exception:
        pass
    try:
        _estim(t.earnings_estimate, out["eps"])
    except Exception:
        pass
    try:
        pt = t.analyst_price_targets or {}
        out["price_target"] = {k: _num(v) for k, v in pt.items()
                               if _num(v) is not None}
    except Exception:
        pass
    return out


def fetch(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    try:
        inc = t.income_stmt
        bal = t.balance_sheet
        cf = t.cashflow
    except Exception:
        inc = bal = cf = None

    revenue = _series_by_year(_first(_row(inc, "total", "revenue"), _row(inc, "revenue")))
    net_income = _series_by_year(_first(_row(inc, exact="Net Income"),
                                        _row(inc, "net", "income")))
    gross = _series_by_year(_row(inc, "gross", "profit"))
    op_income = _series_by_year(_row(inc, "operating", "income"))
    ebitda = _series_by_year(_first(_row(inc, exact="EBITDA"), _row(inc, "ebitda")))
    eps = _series_by_year(_first(_row(inc, "diluted", "eps"), _row(inc, "basic", "eps")))

    equity = _series_by_year(_first(_row(bal, "stockholders", "equity"),
                                    _row(bal, "total", "equity")))
    total_debt = _series_by_year(_row(bal, "total", "debt"))
    cash = _series_by_year(_first(_row(bal, exact="Cash And Cash Equivalents"),
                                  _row(bal, "cash", "equivalents"),
                                  _row(bal, "cash")))
    invested = _series_by_year(_row(bal, "invested", "capital"))
    shares = _series_by_year(_first(_row(bal, "ordinary", "shares", "number"),
                                    _row(bal, "share", "issued")))

    fcf = _series_by_year(_row(cf, "free", "cash", "flow"))

    # pochodne
    net_margin = _ratio(net_income, revenue)
    op_margin = _ratio(op_income, revenue)
    gross_margin = _ratio(gross, revenue)
    fcf_margin = _ratio(fcf, revenue)
    roe = _ratio(net_income, equity)
    book_ps = _ratio(equity, shares)
    net_debt = _diff(total_debt, cash)
    # ROIC ~ NOPAT/invested capital (NOPAT ~ operating_income * (1-0.21))
    nopat = {y: v * 0.79 for y, v in op_income.items()}
    roic = _ratio(nopat, invested)

    # dywidendy na akcje: suma wyplat w danym roku kalendarzowym
    dps = {}
    try:
        divs = t.dividends
        if divs is not None and len(divs):
            g = divs.groupby(divs.index.year).sum()
            dps = {int(y): _num(v) for y, v in g.items() if _num(v) is not None}
    except Exception:
        pass

    # payout ratio na rok: dps/eps
    payout = {}
    for y, d in dps.items():
        e = eps.get(y)
        if _num(e) not in (None, 0):
            payout[y] = d / e

    # roczne PE = srednia cena w danym roku / EPS tego roku
    # + tygodniowe ceny za caly dostepny okres (do wykresu z zakresem Max)
    pe_annual = {}
    avg_price = {}
    prices = {}
    try:
        hist = t.history(period="max")["Close"].dropna()
        if len(hist):
            gp = hist.groupby(hist.index.year).mean()
            avg_price = {int(y): _num(v) for y, v in gp.items() if _num(v) is not None}
            for y, p in avg_price.items():
                e = eps.get(y)
                if _num(e) not in (None, 0) and e > 0:
                    pe_annual[y] = p / e
            # tygodniowe ceny do wykresu kursu (mniej punktow = lzejszy cache)
            wk = hist.resample("W").last().dropna()
            prices = {d.strftime("%Y-%m-%d"): _num(v) for d, v in wk.items()
                      if _num(v) is not None}
    except Exception:
        pass

    forecast = _fetch_forecast(t, revenue, eps)

    data = {
        "ticker": ticker,
        "schema": SCHEMA,
        "forecast": forecast,
        "prices": prices,
        "series": {
            "revenue": revenue, "net_income": net_income, "gross_profit": gross,
            "operating_income": op_income, "ebitda": ebitda, "eps": eps,
            "equity": equity, "total_debt": total_debt, "cash": cash,
            "invested_capital": invested, "shares": shares, "fcf": fcf,
            "net_margin": net_margin, "operating_margin": op_margin,
            "gross_margin": gross_margin, "fcf_margin": fcf_margin,
            "roe": roe, "roic": roic, "book_value_ps": book_ps,
            "net_debt": net_debt, "dividend_ps": dps, "payout": payout,
            "pe_annual": pe_annual, "avg_price": avg_price,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return data


def get_history(ticker: str, force: bool = False) -> dict:
    path = _cache_path(ticker)
    if not force and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = datetime.fromisoformat(cached["fetched_at"])
            if ((datetime.now(timezone.utc) - ts).total_seconds() / 3600 <= TTL_H
                    and cached.get("schema") == SCHEMA):
                # klucze lat z JSON sa stringami -> rzutujemy na int
                for k, s in cached["series"].items():
                    cached["series"][k] = {int(y): v for y, v in s.items()}
                fc = cached.get("forecast", {})
                for k in ("revenue", "eps"):
                    if isinstance(fc.get(k), dict):
                        fc[k] = {int(y): v for y, v in fc[k].items()}
                return cached
        except Exception:
            pass
    data = fetch(ticker)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return data


# ------------------------------------------------------------- Ceny: zrodla ---
# Ceny mozna pobrac z dwoch niezaleznych zrodel. Fundamenty — tylko Yahoo.
PRICE_SOURCES = {
    "yahoo": "Yahoo Finance",
    "stooq": "Stooq",
}


def _stooq_symbol(ticker: str) -> str:
    """Ticker Yahoo -> symbol Stooq: GPW bez sufiksu ('CDR.WA' -> 'cdr'),
    USA z '.us' ('AAPL' -> 'aapl.us')."""
    if ticker.endswith(".WA"):
        return ticker[:-3].lower()
    return ticker.lower() + ".us"


def _stooq_cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR,
                        f"px_stooq_{ticker.replace('.', '_')}.json")


def fetch_prices_stooq(ticker: str) -> dict:
    """Tygodniowe ceny zamkniecia ze Stooq (caly dostepny okres).

    Darmowy CSV bez klucza: https://stooq.com/q/d/l/?s=<symbol>&i=w
    """
    import io

    import requests

    sym = _stooq_symbol(ticker)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=w"
    r = requests.get(url, timeout=30,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    text = r.text.strip()
    if not text or text.lower().startswith(("brak danych", "no data", "<")):
        raise ValueError(f"Stooq nie ma danych dla symbolu '{sym}'.")
    df = pd.read_csv(io.StringIO(text))
    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError(f"Nieoczekiwany format CSV ze Stooq dla '{sym}'.")
    prices = {}
    for _, rrow in df.iterrows():
        v = _num(rrow["Close"])
        if v is not None:
            prices[str(rrow["Date"])] = v
    return {"prices": prices, "source": "stooq",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def get_prices(ticker: str, source: str = "yahoo", force: bool = False) -> dict:
    """Ceny tygodniowe z wybranego zrodla + metadane swiezosci.

    Zwraca {"prices": {YYYY-MM-DD: close}, "source": str, "source_label": str,
    "fetched_at": iso}. Yahoo -> z cache historii (get_history); Stooq ->
    osobny cache data/px_stooq_<t>.json (TTL 24h). Fail-soft: blad Stooq
    zglaszamy wyjatkiem — UI pokazuje komunikat i mozna wrocic na Yahoo.
    """
    if source == "stooq":
        path = _stooq_cache_path(ticker)
        if not force and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                ts = datetime.fromisoformat(cached["fetched_at"])
                if (datetime.now(timezone.utc) - ts).total_seconds() / 3600 <= TTL_H:
                    cached["source_label"] = PRICE_SOURCES["stooq"]
                    return cached
            except Exception:
                pass
        out = fetch_prices_stooq(ticker)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False)
        except Exception:
            pass
        out["source_label"] = PRICE_SOURCES["stooq"]
        return out

    hist = get_history(ticker, force=force)
    return {"prices": hist.get("prices", {}), "source": "yahoo",
            "source_label": PRICE_SOURCES["yahoo"],
            "fetched_at": hist.get("fetched_at")}


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    d = get_history(tk, force=True)
    for k, s in d["series"].items():
        yrs = sorted(s)
        print(f"{k:18} {len(yrs)} lat: {yrs}")
    px = get_prices(tk, "stooq", force=True)
    print(f"stooq: {len(px['prices'])} punktow, fetched {px['fetched_at']}")

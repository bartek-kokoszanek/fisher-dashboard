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

    # kalendarz Yahoo: najblizsze wyniki kwartalne + daty dywidendy
    next_earnings = cal_ex_div = cal_pay = None
    today = datetime.now(timezone.utc).date()
    try:
        cal = t.calendar or {}
        eds = cal.get("Earnings Date") or []
        # tylko PRZYSZLE publikacje — minione daty nie sa pokazywane
        future = sorted(d for d in eds if d >= today)
        if future:
            next_earnings = future[0].isoformat()
        if cal.get("Ex-Dividend Date"):
            cal_ex_div = cal["Ex-Dividend Date"].isoformat()
        if cal.get("Dividend Date"):
            cal_pay = cal["Dividend Date"].isoformat()
    except Exception:
        pass

    # dywidenda: dane z BIEZACEGO roku, a gdy ich brak — z ubieglego.
    # Kandydaci: zadeklarowana w kalendarzu (ex-div + kwota lastDividendValue
    # + ew. dzien wyplaty) oraz historia wyplat (t.dividends: ex-date, kwota).
    # Wygrywa najnowsza data ex-div. Dzien wyplaty zna tylko kalendarz Yahoo
    # (dla czesci GPW brak — pole puste).
    ex_div_date = div_pay_date = None
    dividend_amount = None
    candidates = []  # (ex_date_iso, kwota, pay_date_iso)
    if cal_ex_div:
        candidates.append((cal_ex_div, info.get("lastDividendValue"), cal_pay))
    try:
        divs = t.dividends
        if divs is not None and len(divs):
            for yr in (today.year, today.year - 1):
                sel = divs[divs.index.year == yr]
                if len(sel):
                    candidates.append((sel.index[-1].date().isoformat(),
                                       float(sel.iloc[-1]), None))
                    break
    except Exception:
        pass
    valid = [c for c in candidates
             if c[0] and int(c[0][:4]) >= today.year - 1]
    if valid:
        ex_div_date, dividend_amount, div_pay_date = max(valid, key=lambda c: c[0])

    # ostatnie OPUBLIKOWANE wyniki kwartalne + zaskoczenie vs konsensus EPS.
    # (Yahoo nie udostepnia wstecznego konsensusu przychodow — tylko EPS.)
    last_q_date = last_q_revenue = last_q_eps = eps_surprise = None
    try:
        qinc = t.quarterly_income_stmt
        rev_row = _row(qinc, "total", "revenue")
        if rev_row is None:
            rev_row = _row(qinc, "revenue")
        if rev_row is not None:
            s = rev_row.dropna()
            if len(s):
                last_q_revenue = float(s.iloc[0])
                last_q_date = s.index[0].date().isoformat()
    except Exception:
        pass
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty:
            ehs = eh.dropna(subset=["epsActual"])
            if len(ehs):
                last = ehs.iloc[-1]  # indeks rosnaco po kwartale -> ostatni
                last_q_eps = float(last["epsActual"])
                sp = last.get("surprisePercent")
                if sp is not None and not pd.isna(sp):
                    eps_surprise = float(sp)
                if last_q_date is None:
                    last_q_date = str(ehs.index[-1].date())
    except Exception:
        pass

    # konsensus analitykow: oczekiwany wzrost r/r przychodow i zysku (EPS)
    # na najblizszy raportowany kwartal ('0q'; fallback: biezacy rok '0y')
    def _est_growth(df):
        try:
            if df is None or getattr(df, "empty", True) or "growth" not in df.columns:
                return None
            for period in ("0q", "0y"):
                if period in df.index:
                    v = df.loc[period, "growth"]
                    if v is not None and not pd.isna(v):
                        return float(v)
        except Exception:
            pass
        return None

    try:
        rev_growth_est = _est_growth(t.revenue_estimate)
    except Exception:
        rev_growth_est = None
    try:
        eps_growth_est = _est_growth(t.earnings_estimate)
    except Exception:
        eps_growth_est = None

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
        "next_earnings_date": next_earnings,
        "rev_growth_est": rev_growth_est,
        "eps_growth_est": eps_growth_est,
        # --- dywidenda (biezacy rok, fallback ubiegly) ---
        "ex_dividend_date": ex_div_date,
        "dividend_pay_date": div_pay_date,
        "last_dividend_value": dividend_amount,
        # --- ostatnie opublikowane wyniki kwartalne ---
        "last_q_date": last_q_date,
        "last_q_revenue": last_q_revenue,
        "last_q_eps": last_q_eps,
        "eps_surprise": eps_surprise,
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
            # "eps_surprise" in cached = wersjonowanie schematu: starsze cache
            # (sprzed kolumn wynikow kwartalnych) odswiezaja sie same
            if age <= max_age_hours and "eps_surprise" in cached:
                return cached
        except Exception:
            pass

    raw = fetch_raw(ticker)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    return raw


# Rownolegle pobieranie: yfinance jest I/O-bound (~10 zapytan HTTP na spolke),
# wiec watki daja ~7x przyspieszenie (475 spolek: ~24 min -> ~3 min). Przy 8-16
# watkach Yahoo nie odrzuca zapytan (sprawdzone: te same braki co sekwencyjnie).
WORKERS = int(os.environ.get("FETCH_WORKERS", "8"))


def get_many(tickers, force=False, progress=None, workers=None):
    """Dane dla listy spolek — rownolegle, z zachowaniem kolejnosci wejsciowej.

    progress(i, n, ticker) wolane jest z watku glownego po kazdej gotowej
    spolce (Streamlit nie lubi update'ow UI z watkow roboczych).
    """
    from concurrent.futures import ThreadPoolExecutor

    tickers = list(tickers)
    n = len(tickers)
    if not n:
        return []

    def _one(tk):
        try:
            return get(tk, force=force)
        except Exception as e:
            return {"ticker": tk, "name": config.NAMES.get(tk, tk),
                    "market": config.market_of(tk), "error": str(e)}

    out = []
    with ThreadPoolExecutor(max_workers=workers or WORKERS) as ex:
        for i, res in enumerate(ex.map(_one, tickers)):
            out.append(res)
            if progress:
                progress(i + 1, n, res.get("ticker", ""))
    return out


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(json.dumps(get(tk, force=True), ensure_ascii=False, indent=2))

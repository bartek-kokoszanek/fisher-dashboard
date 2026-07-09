"""Scoring ilosciowy wg zasad Philipa Fishera.

Fisher ma 15 punktow, ale wiekszosc jest jakosciowa (zarzad, kultura, R&D).
Tutaj punktujemy tylko to, co da sie zmierzyc z danych finansowych.
Reszta (jakosc) idzie przez ai_research.py.

Kazda metryka jest przeksztalcana na 0-100 przez funkcje progowa,
a nastepnie wazona zgodnie z config.WEIGHTS. Wynik koncowy 0-100.
"""
from __future__ import annotations

import math

import config


def _isnum(x) -> bool:
    """True tylko dla skonczonych liczb (odrzuca None, NaN, str, pd.NA itp.)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) \
        and math.isfinite(x)


def _band(x, low, high):
    """Liniowe skalowanie x z przedzialu [low, high] do 0-100 (z obcieciem)."""
    if not _isnum(x):
        return None
    if high == low:
        return 50.0
    v = (x - low) / (high - low) * 100
    return max(0.0, min(100.0, v))


def _band_inv(x, low, high):
    """Jak _band, ale mniej = lepiej (np. zadluzenie, rozwodnienie)."""
    s = _band(x, low, high)
    return None if s is None else 100.0 - s


# Progi (dobrane pod spolki wzrostowe; edytowalne).
# (metryka) -> funkcja(raw_value) -> 0..100 lub None
SCORERS = {
    "revenue_cagr":       lambda x: _band(x, 0.00, 0.25),   # 0% -> 0, 25%+/rok -> 100
    "revenue_growth_yoy": lambda x: _band(x, -0.05, 0.30),
    "gross_margin":       lambda x: _band(x, 0.15, 0.65),
    "operating_margin":   lambda x: _band(x, 0.05, 0.35),
    "margin_trend":       lambda x: _band(x, -0.05, 0.10),   # spadek marzy karany
    "rnd_intensity":      lambda x: _band(x, 0.00, 0.15),    # 15%+ przychodow na R&D -> 100
    "roe":                lambda x: _band(x, 0.05, 0.30),
    "fcf_margin":         lambda x: _band(x, 0.00, 0.25),
    "low_dilution":       lambda x: _band_inv(x, -0.01, 0.05),  # rozwadnianie karane
    "low_leverage":       lambda x: _band_inv(x, 0.0, 2.0),     # D/E: 0 -> 100, 2+ -> 0
    # metryki dodatkowe dla strategii guru (gurus.py):
    "value_pe":           lambda x: _band_inv(x, 5, 40) if (_isnum(x) and x > 0) else None,
    "momentum":           lambda x: _band(x, -0.20, 0.50),      # zwrot 6-mies.
}

# Ktora surowa metryka zasila ktory scorer
RAW_KEY = {
    "revenue_cagr": "revenue_cagr",
    "revenue_growth_yoy": "revenue_growth_yoy",
    "gross_margin": "gross_margin",
    "operating_margin": "operating_margin",
    "margin_trend": "margin_trend",
    "rnd_intensity": "rnd_intensity",
    "roe": "roe",
    "fcf_margin": "fcf_margin",
    "low_dilution": "dilution",
    "low_leverage": "debt_to_equity",
    "value_pe": "trailing_pe",
    "momentum": "return_6m",
}

# metryki bez sensu dla bankow/ubezpieczycieli (inna struktura sprawozdan)
FIN_SKIP = {"rnd_intensity", "gross_margin", "revenue_cagr", "revenue_growth_yoy"}


def compute_score(raw: dict, weights: dict | None = None) -> dict:
    """Zwraca {'score': float, 'subscores': {...}, 'coverage': float}.

    weights: slownik metryka->waga; domyslnie config.WEIGHTS (strategia Fishera).
    Strategie innych inwestorow (gurus.py) podaja wlasne wagi na tym samym
    zestawie metryk (+ value_pe, momentum).
    coverage = jaki % wagi udalo sie faktycznie policzyc (brak danych ->
    metryka pomijana, a wagi renormalizowane). Nizsza coverage = mniej ufny wynik.
    """
    weights = weights or config.WEIGHTS
    subscores = {}
    weighted_sum = 0.0
    weight_used = 0.0
    is_fin = raw.get("is_financial", False)

    for metric, weight in weights.items():
        # Banki: R&D i marze brutto nie maja sensu -> pomijamy te metryki
        if is_fin and metric in FIN_SKIP:
            continue

        raw_val = raw.get(RAW_KEY[metric])
        score = SCORERS[metric](raw_val)
        if score is None:
            subscores[metric] = None
            continue
        subscores[metric] = round(score, 1)
        weighted_sum += score * weight
        weight_used += weight

    total_weight = sum(w for m, w in weights.items()
                       if not (is_fin and m in FIN_SKIP))

    final = round(weighted_sum / weight_used, 1) if weight_used else None
    coverage = round(100 * weight_used / total_weight, 0) if total_weight else 0

    return {"score": final, "subscores": subscores, "coverage": coverage}


def verdict(score) -> str:
    if score is None:
        return "brak danych"
    if score >= 75:
        return "Silny kandydat strategii"
    if score >= 60:
        return "Wart obserwacji"
    if score >= 45:
        return "Przecietny"
    return "Slaby wg kryteriow"

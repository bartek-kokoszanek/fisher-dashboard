"""Scoring ilosciowy wg zasad Philipa Fishera.

Fisher ma 15 punktow, ale wiekszosc jest jakosciowa (zarzad, kultura, R&D).
Tutaj punktujemy tylko to, co da sie zmierzyc z danych finansowych.
Reszta (jakosc) idzie przez ai_research.py.

Kazda metryka jest przeksztalcana na 0-100 przez funkcje progowa,
a nastepnie wazona zgodnie z config.WEIGHTS. Wynik koncowy 0-100.
"""
from __future__ import annotations

import config


def _band(x, low, high):
    """Liniowe skalowanie x z przedzialu [low, high] do 0-100 (z obcieciem)."""
    if x is None:
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
}


def compute_score(raw: dict) -> dict:
    """Zwraca {'score': float, 'subscores': {...}, 'coverage': float}.

    coverage = jaki % wagi udalo sie faktycznie policzyc (brak danych ->
    metryka pomijana, a wagi renormalizowane). Nizsza coverage = mniej ufny wynik.
    """
    subscores = {}
    weighted_sum = 0.0
    weight_used = 0.0
    is_fin = raw.get("is_financial", False)

    for metric, weight in config.WEIGHTS.items():
        # Banki: R&D i marze brutto nie maja sensu -> pomijamy te metryki
        if is_fin and metric in ("rnd_intensity", "gross_margin", "revenue_cagr", "revenue_growth_yoy"):
            continue

        raw_val = raw.get(RAW_KEY[metric])
        score = SCORERS[metric](raw_val)
        if score is None:
            subscores[metric] = None
            continue
        subscores[metric] = round(score, 1)
        weighted_sum += score * weight
        weight_used += weight

    total_weight = sum(
        w for m, w in config.WEIGHTS.items()
        if not (is_fin and m in ("rnd_intensity", "gross_margin", "revenue_cagr", "revenue_growth_yoy"))
    )

    final = round(weighted_sum / weight_used, 1) if weight_used else None
    coverage = round(100 * weight_used / total_weight, 0) if total_weight else 0

    return {"score": final, "subscores": subscores, "coverage": coverage}


def verdict(score) -> str:
    if score is None:
        return "brak danych"
    if score >= 75:
        return "Silny kandydat Fishera"
    if score >= 60:
        return "Wart obserwacji"
    if score >= 45:
        return "Przecietny"
    return "Slaby wg kryteriow"

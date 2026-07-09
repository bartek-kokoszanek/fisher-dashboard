"""Wykres 10: Dividend History (Bar, dywidenda na akcje, do 20 lat)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_dividends(hist: dict, max_years: int = 20):
    years, vals = h.sorted_items(hist["series"].get("dividend_ps"))
    if years:
        years, vals = years[-max_years:], vals[-max_years:]
    if len(years) < 2:
        return None
    fig = go.Figure()
    fig.add_bar(x=years, y=vals, marker_color=h.COLORS["dividend"],
                hovertemplate="%{x}: %{y:.2f}/akcję<extra></extra>")
    return h.base_layout(fig)


def dividend_stats(hist: dict) -> dict:
    years, vals = h.sorted_items(hist["series"].get("dividend_ps"))
    _, payout = h.sorted_items(hist["series"].get("payout"))
    return {
        "cagr": h.cagr(vals),
        "avg_payout": h.mean(payout),
        "years_paid": len([v for v in vals if h.is_num(v) and v > 0]),
    }

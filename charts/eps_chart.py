"""Wykresy: EPS (12), Book Value per Share (13), Shares Outstanding (11)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_eps(hist):
    years, vals = h.sorted_items(hist["series"].get("eps"))
    years, vals = years[-5:], vals[-5:]
    if len(years) < 2:
        return None
    xh = [str(y) for y in years]
    colors = [h.COLORS["eps"] if v >= 0 else h.COLORS["neg"] for v in vals]
    fig = go.Figure()
    fig.add_scatter(x=xh, y=vals, mode="lines+markers", name="Historia",
                    line=dict(color=h.COLORS["eps"], width=2.5),
                    marker=dict(size=7, color=colors),
                    hovertemplate="%{x}: EPS %{y:.2f}<extra></extra>")
    fc = (hist.get("forecast") or {}).get("eps") or {}
    fyears = sorted(fc)
    has_fc = bool(fyears)
    if has_fc:
        # laczymy ostatni punkt historii z prognoza (ciaglosc linii)
        xf = [xh[-1]] + [str(y) for y in fyears]
        yf = [vals[-1]] + [fc[y]["avg"] for y in fyears]
        err_plus = [None] + [(fc[y]["high"] - fc[y]["avg"]) if h.is_num(fc[y].get("high")) else None for y in fyears]
        err_minus = [None] + [(fc[y]["avg"] - fc[y]["low"]) if h.is_num(fc[y].get("low")) else None for y in fyears]
        fig.add_scatter(x=xf, y=yf, mode="lines+markers", name="Prognoza analityków",
                        line=dict(color=h.COLORS["eps"], width=2, dash="dot"),
                        marker=dict(size=8, symbol="diamond-open"),
                        error_y=dict(type="data", symmetric=False, array=err_plus,
                                     arrayminus=err_minus, color="rgba(128,128,128,0.5)"),
                        hovertemplate="%{x} (prognoza): EPS %{y:.2f}<extra></extra>")
    return h.base_layout(fig, legend=has_fc)


def fig_book_value(hist):
    years, vals = h.sorted_items(hist["series"].get("book_value_ps"))
    if len(years) < 2:
        return None
    fig = go.Figure()
    fig.add_scatter(x=years, y=vals, mode="lines+markers",
                    line=dict(color=h.COLORS["book"], width=2.5), marker=dict(size=7),
                    hovertemplate="%{x}: %{y:.2f}/akcję<extra></extra>")
    return h.base_layout(fig)


def fig_shares(hist):
    years, vals = h.sorted_items(hist["series"].get("shares"))
    if len(years) < 2:
        return None
    fig = go.Figure()
    fig.add_scatter(x=years, y=vals, mode="lines+markers",
                    line=dict(color=h.COLORS["shares"], width=2.5), marker=dict(size=7),
                    text=[h.human(v) for v in vals],
                    hovertemplate="%{x}: %{text} akcji<extra></extra>")
    return h.base_layout(fig)


def shares_trend(hist) -> str | None:
    """'buyback' (spadek liczby akcji), 'dilution' (wzrost) lub None."""
    years, vals = h.sorted_items(hist["series"].get("shares"))
    if len(vals) < 2 or vals[0] == 0:
        return None
    change = vals[-1] / vals[0] - 1
    if change < -0.01:
        return "buyback"
    if change > 0.01:
        return "dilution"
    return "flat"

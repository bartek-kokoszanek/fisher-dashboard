"""Wykresy: EPS (12), Book Value per Share (13), Shares Outstanding (11)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_eps(hist):
    years, vals = h.sorted_items(hist["series"].get("eps"))
    if len(years) < 2:
        return None
    colors = [h.COLORS["eps"] if v >= 0 else h.COLORS["neg"] for v in vals]
    fig = go.Figure()
    fig.add_scatter(x=years, y=vals, mode="lines+markers",
                    line=dict(color=h.COLORS["eps"], width=2.5),
                    marker=dict(size=7, color=colors),
                    hovertemplate="%{x}: EPS %{y:.2f}<extra></extra>")
    return h.base_layout(fig)


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

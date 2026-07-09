"""Wykresy: Revenue (bar+line), Revenue Growth, Net Income, Net Income Growth."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_revenue(hist: dict):
    years, vals = h.sorted_items(hist["series"].get("revenue"))
    if len(years) < 2:
        return None
    fig = go.Figure()
    fig.add_bar(x=years, y=vals, name="Przychody",
                marker_color=h.COLORS["revenue"],
                text=[h.human(v) for v in vals], textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>")
    fig.add_scatter(x=years, y=vals, mode="lines", line=dict(color=h.COLORS["revenue"], width=2),
                    hoverinfo="skip", showlegend=False)
    return h.base_layout(fig)


def _growth_fig(hist, key):
    years, vals = h.sorted_items(hist["series"].get(key))
    if len(years) < 2:
        return None
    g = h.yoy(vals)
    xs = [y for y, gv in zip(years, g) if gv is not None]
    ys = [gv * 100 for gv in g if gv is not None]
    if len(xs) < 1:
        return None
    colors = [h.COLORS["pos"] if v >= 0 else h.COLORS["neg"] for v in ys]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=ys, mode="lines+markers",
                    line=dict(color="rgba(128,128,128,0.5)", width=1.5),
                    marker=dict(color=colors, size=9),
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    fig.add_hline(y=0, line_color="rgba(128,128,128,0.4)")
    return h.base_layout(fig)


def fig_revenue_growth(hist):
    return _growth_fig(hist, "revenue")


def fig_net_income(hist):
    years, vals = h.sorted_items(hist["series"].get("net_income"))
    if len(years) < 2:
        return None
    colors = [h.COLORS["net_income"] if v >= 0 else h.COLORS["neg"] for v in vals]
    fig = go.Figure()
    fig.add_bar(x=years, y=vals, marker_color=colors,
                text=[h.human(v) for v in vals], textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>")
    return h.base_layout(fig)


def fig_net_income_growth(hist):
    return _growth_fig(hist, "net_income")

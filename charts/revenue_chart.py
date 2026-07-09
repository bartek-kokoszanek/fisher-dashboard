"""Wykresy: Revenue (bar+line), Revenue Growth, Net Income, Net Income Growth."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def _forecast_bars(fig, fc: dict, color: str):
    """Dokleja slupki prognozy analitykow (0y/+1y) z widelkami low/high."""
    fyears = sorted(fc)
    if not fyears:
        return False
    xf = [str(y) for y in fyears]
    avg = [fc[y]["avg"] for y in fyears]
    err_plus = [(fc[y]["high"] - fc[y]["avg"]) if h.is_num(fc[y].get("high")) else None
                for y in fyears]
    err_minus = [(fc[y]["avg"] - fc[y]["low"]) if h.is_num(fc[y].get("low")) else None
                 for y in fyears]
    fig.add_bar(x=xf, y=avg, name="Prognoza analityków",
                marker=dict(color=color, opacity=0.45, pattern_shape="/"),
                error_y=dict(type="data", symmetric=False, array=err_plus,
                             arrayminus=err_minus, color="rgba(128,128,128,0.6)"),
                text=[h.human(v) for v in avg], textposition="outside",
                hovertemplate="%{x} (prognoza): %{text}<extra></extra>")
    return True


def fig_revenue(hist: dict):
    years, vals = h.sorted_items(hist["series"].get("revenue"))
    years, vals = years[-5:], vals[-5:]
    if len(years) < 2:
        return None
    xh = [str(y) for y in years]
    fig = go.Figure()
    fig.add_bar(x=xh, y=vals, name="Historia", marker_color=h.COLORS["revenue"],
                text=[h.human(v) for v in vals], textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>")
    fig.add_scatter(x=xh, y=vals, mode="lines", line=dict(color=h.COLORS["revenue"], width=2),
                    hoverinfo="skip", showlegend=False)
    fc = (hist.get("forecast") or {}).get("revenue") or {}
    has_fc = _forecast_bars(fig, fc, h.COLORS["revenue"])
    return h.base_layout(fig, legend=has_fc)


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

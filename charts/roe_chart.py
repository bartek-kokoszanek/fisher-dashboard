"""Wykresy: ROE (ze srednia/max/min), ROIC (ze srednia). Line, % ."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_roe(hist):
    years, vals = h.sorted_items(hist["series"].get("roe"))
    if len(years) < 2:
        return None
    ys = [v * 100 for v in vals]
    fig = go.Figure()
    fig.add_scatter(x=years, y=ys, mode="lines+markers",
                    line=dict(color=h.COLORS["roe"], width=2.5), marker=dict(size=7),
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    avg = h.mean(vals)
    if avg is not None:
        fig.add_hline(y=avg * 100, line_dash="dash", line_color="rgba(128,128,128,0.6)",
                      annotation_text=f"śr. {avg * 100:.1f}%", annotation_position="top left")
    return h.base_layout(fig)


def fig_roic(hist):
    years, vals = h.sorted_items(hist["series"].get("roic"))
    if len(years) < 2:
        return None
    ys = [v * 100 for v in vals]
    fig = go.Figure()
    fig.add_scatter(x=years, y=ys, mode="lines+markers",
                    line=dict(color=h.COLORS["roic"], width=2.5), marker=dict(size=7),
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    avg = h.mean(vals)
    if avg is not None:
        fig.add_hline(y=avg * 100, line_dash="dash", line_color="rgba(128,128,128,0.6)",
                      annotation_text=f"śr. {avg * 100:.1f}%", annotation_position="top left")
    return h.base_layout(fig)

"""Wykresy marz: Net Margin, Operating Margin (Line, 10 lat / ile dostepne)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def _margin_fig(hist, key, color, avg_line=True):
    years, vals = h.sorted_items(hist["series"].get(key))
    if len(years) < 2:
        return None
    ys = [v * 100 for v in vals]
    fig = go.Figure()
    fig.add_scatter(x=years, y=ys, mode="lines+markers",
                    line=dict(color=color, width=2.5), marker=dict(size=7),
                    fill="tozeroy", fillcolor=color.replace(")", ",0.08)").replace("rgb", "rgba")
                    if color.startswith("rgb") else "rgba(124,58,237,0.08)",
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    avg = h.mean(vals)
    if avg_line and avg is not None:
        fig.add_hline(y=avg * 100, line_dash="dash",
                      line_color="rgba(128,128,128,0.6)",
                      annotation_text=f"śr. {avg * 100:.1f}%",
                      annotation_position="top left")
    return h.base_layout(fig)


def fig_net_margin(hist):
    return _margin_fig(hist, "net_margin", h.COLORS["margin"])


def fig_operating_margin(hist):
    return _margin_fig(hist, "operating_margin", h.COLORS["margin"])

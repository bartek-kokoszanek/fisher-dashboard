"""Wykres: Free Cash Flow (Bar, zielone dodatnie / czerwone ujemne)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_fcf(hist):
    years, vals = h.sorted_items(hist["series"].get("fcf"))
    if len(years) < 2:
        return None
    colors = [h.COLORS["pos"] if v >= 0 else h.COLORS["neg"] for v in vals]
    fig = go.Figure()
    fig.add_bar(x=years, y=vals, marker_color=colors,
                text=[h.human(v) for v in vals], textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>")
    fig.add_hline(y=0, line_color="rgba(128,128,128,0.4)")
    return h.base_layout(fig)

"""Wykres: Net Debt (Line). Ujemne = gotowka netto (pokazujemy pod zerem)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_net_debt(hist):
    years, vals = h.sorted_items(hist["series"].get("net_debt"))
    if len(years) < 2:
        return None
    fig = go.Figure()
    fig.add_scatter(x=years, y=vals, mode="lines+markers",
                    line=dict(color=h.COLORS["debt"], width=2.5), marker=dict(size=7),
                    text=[h.human(v) for v in vals],
                    hovertemplate="%{x}: %{text}<extra></extra>")
    fig.add_hline(y=0, line_color="rgba(128,128,128,0.5)",
                  annotation_text="0 = brak długu netto", annotation_position="bottom right")
    return h.base_layout(fig)

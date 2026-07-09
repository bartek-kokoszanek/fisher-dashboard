"""Wykres ceny/kursu akcji za wybrany okres (1R / 2L / 3L / 5L)."""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go

from . import helpers as h

PERIODS = {"1 rok": 1, "2 lata": 2, "3 lata": 3, "5 lat": 5}


def fig_price(prices: dict, years: int = 1):
    """prices: {YYYY-MM-DD: close}. Zwraca wykres ceny za ostatnie `years` lat."""
    if not prices:
        return None
    cutoff = datetime.now() - timedelta(days=365 * years + 7)
    items = []
    for d, v in prices.items():
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if dt >= cutoff and h.is_num(v):
            items.append((dt, v))
    items.sort()
    if len(items) < 2:
        return None
    xs = [dt for dt, _ in items]
    ys = [v for _, v in items]
    up = ys[-1] >= ys[0]
    color = h.COLORS["pos"] if up else h.COLORS["neg"]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=2),
                    hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>")
    # autoskala Y wokol realnego zakresu cen (nie od zera) + lekki margines
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.06 or hi * 0.02
    fig.update_yaxes(range=[lo - pad, hi + pad])
    return h.base_layout(fig, height=300, time_axis=True)

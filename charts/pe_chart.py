"""Wykres 9: PE History z pasmami (tanio/neutralnie/drogo) + auto-komentarz.

UWAGA: darmowy yfinance nie daje ciaglej historii PE. Budujemy roczne PE
(srednia cena roku / EPS roku) — zwykle ~5 punktow. Aktualne PE bierzemy
z danych spolki (trailing_pe), a srednia liczymy z dostepnych lat.
"""
from __future__ import annotations

import plotly.graph_objects as go

from . import helpers as h


def fig_pe_history(hist: dict, current_pe=None):
    years, vals = h.sorted_items(hist["series"].get("pe_annual"))
    vals = [v for v in vals if h.is_num(v) and v > 0]
    years = years[-len(vals):] if vals else []
    if len(years) < 2:
        return None, None

    avg = h.mean(vals)
    vmin, vmax = min(vals), max(vals)
    cur = current_pe if h.is_num(current_pe) else vals[-1]

    fig = go.Figure()
    # pasma wzgledem sredniej
    if avg:
        lo, hi = avg * 0.9, avg * 1.1
        top = max(vmax, cur, hi) * 1.1
        fig.add_hrect(y0=0, y1=lo, fillcolor=h.COLORS["band_ok"], line_width=0)
        fig.add_hrect(y0=lo, y1=hi, fillcolor=h.COLORS["band_mid"], line_width=0)
        fig.add_hrect(y0=hi, y1=top, fillcolor=h.COLORS["band_hi"], line_width=0)

    fig.add_scatter(x=years, y=vals, mode="lines+markers",
                    line=dict(color=h.COLORS["pe"], width=2.5), marker=dict(size=8),
                    hovertemplate="%{x}: P/E %{y:.1f}<extra></extra>")
    if avg:
        fig.add_hline(y=avg, line_dash="dash", line_color="rgba(128,128,128,0.7)",
                      annotation_text=f"śr. {avg:.1f}", annotation_position="top left")
    # aktualne PE jako punkt wyrozniony
    if h.is_num(cur):
        fig.add_scatter(x=[years[-1]], y=[cur], mode="markers",
                        marker=dict(color=h.COLORS["pe"], size=13, symbol="star"),
                        hovertemplate=f"Aktualne P/E {cur:.1f}<extra></extra>",
                        showlegend=False)

    comment = _comment(cur, avg, vmin, vmax)
    return h.base_layout(fig), comment


def _comment(cur, avg, vmin, vmax):
    if not (h.is_num(cur) and h.is_num(avg) and avg):
        return None
    diff = cur / avg - 1
    if diff <= -0.10:
        verdict = f"notowana ok. {abs(diff) * 100:.0f}% PONIŻEJ historycznej średniej — wycena relatywnie atrakcyjna."
    elif diff >= 0.10:
        verdict = f"notowana ok. {diff * 100:.0f}% POWYŻEJ historycznej średniej — wycena relatywnie wymagająca."
    else:
        verdict = "notowana w OKOLICACH historycznej średniej — wycena neutralna."
    return (f"Aktualne P/E wynosi {cur:.1f} przy średniej {avg:.1f} "
            f"(zakres {vmin:.1f}–{vmax:.1f}). Spółka jest {verdict}")

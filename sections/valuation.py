"""Zakladka Wycena: interpretacja AI, dywidenda, raporty PWPA.

Dywidenda mieszka tutaj, a nie w fundamentach, bo jest skladnikiem stopy
zwrotu, nie fundamentem operacyjnym (patrz spec).
"""
from __future__ import annotations

import streamlit as st

import financial_charts


def render(ticker: str, row: dict, hist: dict, notes: str | None,
           render_pwpa_fn, label: str) -> None:
    financial_charts.render_ai_interpretation(ticker, row, hist, notes)
    st.divider()
    financial_charts.render_dividend(ticker, row, hist)
    if ticker.endswith(".WA"):
        render_pwpa_fn(ticker, label)

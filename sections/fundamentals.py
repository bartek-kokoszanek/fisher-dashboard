"""Zakladka Fundamenty: kurs, rozbicie ilosciowe, KPI, 15 wykresow.

Kolejnosc od tego, co widac najszybciej (kurs), przez to, z czego
sklada sie Wynik (subscore), po pelna historie finansowa.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import financial_charts
import fisher_score


def render(ticker: str, row: dict, hist: dict, metric_labels: dict,
           fmt_pct) -> None:
    financial_charts.render_price_chart(ticker, row, hist)
    st.divider()

    st.markdown("**Rozbicie ilosciowe**")
    subs = row.get("subscores") or {}
    srows = [{"Metryka": label, "Pkt (0-100)": subs[m],
              "Wartosc surowa": fmt_pct(row.get(fisher_score.RAW_KEY[m]))}
             for m, label in metric_labels.items() if m in subs]
    st.dataframe(pd.DataFrame(srows), hide_index=True, width="stretch")
    st.caption(f"Sektor: {row.get('sector') or '—'} · "
               f"Kapitalizacja: {row.get('market_cap') or '—'} "
               f"{row.get('currency') or ''}")
    st.divider()

    financial_charts.render_kpis(hist, row)
    st.divider()
    financial_charts.render_charts(hist, row)

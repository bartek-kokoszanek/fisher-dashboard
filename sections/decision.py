"""Zakladka Decyzja: ocena jakosciowa AI, zalety/wady, panel decyzyjny.

Ocena jakosciowa stoi tutaj, a nie przy fundamentach, bo to ona karmi
jakosciowe warunki bramki decyzyjnej ('wariant', 'katalizator').
"""
from __future__ import annotations

import streamlit as st

import ai_research
import decision_panel
import gurus
from charts.helpers import fmt_dt


def render(ticker: str, row: dict, wl: dict, save_wl, guru_key: str,
           label: str) -> None:
    st.subheader(f"Ocena jakosciowa ({gurus.get(guru_key)['name']}) — {label}")
    ai = ai_research.load_cached(ticker, guru_key)
    if st.button("🤖 Uruchom research AI dla tej spolki",
                 disabled=not ai_research.available()):
        with st.spinner(f"Model ocenia przez pryzmat: {gurus.get(guru_key)['name']}..."):
            try:
                ai = ai_research.research(ticker, row.get("name", ticker),
                                          row.get("market", ""),
                                          guru=guru_key, force=True)
                st.rerun()
            except Exception as e:
                st.error(f"Blad research: {e}")
    if ai:
        for k, dim_label in ai_research.DIMENSIONS.items():
            sc = ai.get("scores", {}).get(k)
            note = ai.get("notes", {}).get(k, "")
            st.write(f"**{dim_label.split('(')[0].strip()}** — {sc}/100")
            if note:
                st.caption(note)
        st.info(ai.get("summary", ""))
        st.caption(f"Model: {ai.get('model')} · pewnosc: {ai.get('confidence')}% "
                   f"· wygenerowano {fmt_dt(ai.get('researched_at'))} "
                   "(wiedza modelu, bez wyszukiwarki)")
    else:
        st.caption("Brak researchu AI dla tej strategii. Uruchom przyciskiem powyzej.")

    if ai and (ai.get("strengths") or ai.get("weaknesses")):
        zc, wc = st.columns(2)
        with zc:
            st.subheader("✅ Najwieksze zalety")
            for s in ai.get("strengths", []):
                st.markdown(f"- {s}")
        with wc:
            st.subheader("⚠️ Najwieksze wady i ryzyka")
            for w in ai.get("weaknesses", []):
                st.markdown(f"- {w}")

    st.divider()
    decision_panel.render(ticker, row, wl, save_wl)

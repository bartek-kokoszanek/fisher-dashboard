"""Zakladka Notatki: prywatne wnioski uzytkownika (zapis w Giscie).

Notatki zasilaja interpretacje AI w zakladce Wycena - dlatego sekcja
mowi o tym wprost, zeby nie trzeba bylo tego zgadywac.
"""
from __future__ import annotations

import streamlit as st

import watchlists


def render(ticker: str, wl: dict, save_wl) -> None:
    notes = wl.setdefault("notes", {})
    _has_note = bool(notes.get(ticker, "").strip())
    with st.expander("📝 Moje notatki / wnioski z analiz" + (" ✓" if _has_note else ""),
                     expanded=_has_note):
        txt = st.text_area(
            "Notatki", value=notes.get(ticker, ""), height=160,
            key=f"note_{ticker}", label_visibility="collapsed",
            placeholder="Twoje wlasne wnioski, tezy, wyceny, cytaty z analiz, "
                        "ktore czytasz gdzie indziej. Uzytek osobisty.")
        nc1, nc2 = st.columns([1, 4])
        with nc1:
            if st.button("💾 Zapisz notatke", key=f"savenote_{ticker}"):
                if txt.strip():
                    notes[ticker] = txt.strip()
                else:
                    notes.pop(ticker, None)
                save_wl()
                st.success("Zapisano.")
                st.rerun()
        with nc2:
            if watchlists.backend() == "gist":
                st.caption("Zapis: GitHub Gist ✅ (trwaly, prywatny).")
            else:
                st.caption("Bez GITHUB_TOKEN+GIST_ID notatki sa lokalne i znikna "
                           "przy restarcie aplikacji.")
    st.caption("Te notatki trafiają do interpretacji AI w zakładce "
               "💰 Wycena — po ich zmianie przelicz podsumowanie tam.")

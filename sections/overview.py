"""Przypiety pasek przegladu — zawsze widoczny nad zakladkami.

Monitoring znanych spolek konczy sie na tym pasku (odpowiedz bez jednego
klikniecia), research ma te liczby na oczach podczas czytania kazdej
zakladki. Brak wartosci pokazuje '—' i kolumna NIE znika, zeby uklad nie
skakal przy przelaczaniu spolek.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import financial_charts
import fisher_score
import pwpa_targets
import research_deep
from charts import helpers as h
from charts.helpers import fmt_dt

DASH = "—"


def _dni_do(iso: str | None) -> str:
    """'2026-08-27' -> 'za 38 dni' / 'dzis' / '' gdy data minela lub brak."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso)).date()
    except (ValueError, TypeError):
        return ""
    delta = (d - date.today()).days
    if delta < 0:
        return ""
    return "dzis" if delta == 0 else f"za {delta} dni"


def render(ticker: str, row: dict, hist: dict) -> None:
    with st.container(border=True):
        c = st.columns(7)

        # 1. wynik + sygnal
        av = fisher_score.action_verdict(row.get("combined"))
        wynik = row.get("combined")
        c[0].metric("Wynik", DASH if wynik is None else f"{wynik:.0f}",
                    delta=f"{av['emoji']} {av['label']}", delta_color="off")

        # 2. wycena DCF na akcje
        dcf = financial_charts.dcf_per_share(hist) if hist else None
        cena = row.get("price")
        curr = row.get("currency") or ""
        if dcf and h.is_num(cena) and cena:
            c[1].metric("DCF / akcję", f"{dcf['value']:.2f} {curr}".strip(),
                        delta=f"{(dcf['value'] / cena - 1) * 100:+.0f}% vs cena")
        else:
            c[1].metric("DCF / akcję", DASH)

        # 3. cena docelowa z raportu PWPA
        c[2].metric("Cena docelowa PWPA", pwpa_targets.cell(ticker) or DASH)

        # 4. najblizsze wyniki kwartalne
        ned = row.get("next_earnings_date")
        c[3].metric("Najbliższe wyniki", str(ned) if ned else DASH,
                    delta=_dni_do(ned) or None, delta_color="off")

        # 5. dywidenda
        kwota, ex = row.get("last_dividend_value"), row.get("ex_dividend_date")
        c[4].metric("Dywidenda",
                    f"{kwota:.2f} {curr}".strip() if h.is_num(kwota) else DASH,
                    delta=f"ex {ex}" if ex else None, delta_color="off")

        # 6. sentyment rynku z deep researchu
        sent = (research_deep.load_cached(ticker) or {}).get("sentiment")
        c[5].metric("Sentyment", f"{sent:+d}" if isinstance(sent, int) else DASH)

        # 7. pokrycie danych
        c[6].metric("Pokrycie", f"{row.get('coverage', 0):.0f}%")

        st.caption(f"🗓 Yahoo Finance · zaktualizowano {fmt_dt(row.get('fetched_at'))}")
        st.markdown("Wynik · DCF · PWPA · Dywidenda · Pokrycie")

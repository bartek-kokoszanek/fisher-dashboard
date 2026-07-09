"""Sekcja 'Financial Charts' — KPI + 15 wykresow w kartach + podsumowanie AI.

Modularne: dane z charts.data, wykresy z pakietu charts.*, wspolne narzedzia
w charts.helpers. Wszystko Plotly, responsywne, z lagodna obsluga brakow danych.
Renderowane w app.py miedzy podsumowaniem spolki a deep research.
"""
from __future__ import annotations

import json
import os

import streamlit as st

import ai_research
import config
from charts import (cashflow_chart, data, debt_chart, dividend_chart, eps_chart,
                    helpers as h, margin_chart, pe_chart, price_chart,
                    revenue_chart, roe_chart)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def _hist(ticker: str) -> dict:
    return data.get_history(ticker)


def _last(series: dict):
    years, vals = h.sorted_items(series)
    return vals[-1] if vals else None


# ---------------- KPI ----------------

def _kpis(hist: dict, row: dict) -> list[tuple[str, str]]:
    s = hist["series"]
    price = row.get("price")
    dps_last = _last(s.get("dividend_ps"))
    div_yield = dps_last / price if h.is_num(dps_last) and h.is_num(price) and price else None
    net_debt, ebitda = _last(s.get("net_debt")), _last(s.get("ebitda"))
    debt_ebitda = net_debt / ebitda if h.is_num(net_debt) and h.is_num(ebitda) and ebitda else None
    _, rev = h.sorted_items(s.get("revenue"))
    _, eps = h.sorted_items(s.get("eps"))
    return [
        ("Revenue CAGR", h.pct(h.cagr(rev))),
        ("EPS CAGR", h.pct(h.cagr(eps))),
        ("Marża netto", h.pct(_last(s.get("net_margin")))),
        ("ROE", h.pct(_last(s.get("roe")))),
        ("P/E", h.num(row.get("trailing_pe"))),
        ("Stopa dywidendy", h.pct(div_yield)),
        ("Dywidenda CAGR", h.pct(dividend_chart.dividend_stats(hist)["cagr"])),
        ("FCF (ost.)", h.human(_last(s.get("fcf")))),
        ("Dług netto/EBITDA", h.num(debt_ebitda)),
    ]


# ---------------- Karty wykresow ----------------

def _card(col, title: str, desc: str, fig, footer: str = ""):
    with col.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(desc)
        if fig is None:
            st.info("Dane niedostępne dla tej spółki.")
        else:
            st.plotly_chart(fig, use_container_width=True, theme="streamlit",
                            config=h.PLOTLY_CONFIG)
            if footer:
                st.caption(footer)


def _specs(hist: dict, row: dict) -> list[tuple]:
    """Lista (tytul, opis, figura, stopka). Kazdy wykres = osobna karta."""
    s = hist["series"]
    out = []

    _, rev = h.sorted_items(s.get("revenue"))
    out.append(("Revenue", "Przychody: historia + prognoza analityków (słupki kreskowane).",
                revenue_chart.fig_revenue(hist),
                f"CAGR 5Y: {h.pct(h.cagr(rev[-5:]))} · CAGR 10Y: {h.pct(h.cagr(rev[-10:]))}"))

    out.append(("Revenue Growth", "Dynamika przychodów r/r (zielony >0, czerwony <0).",
                revenue_chart.fig_revenue_growth(hist), ""))

    _, ni = h.sorted_items(s.get("net_income"))
    out.append(("Net Income", "Zysk netto rok po roku.",
                revenue_chart.fig_net_income(hist), f"CAGR: {h.pct(h.cagr(ni))}"))

    out.append(("Net Income Growth", "Dynamika zysku netto r/r.",
                revenue_chart.fig_net_income_growth(hist), ""))

    _, nm = h.sorted_items(s.get("net_margin"))
    out.append(("Net Margin", "Marża netto (%) ze średnią.",
                margin_chart.fig_net_margin(hist),
                f"Średnia: {h.pct(h.mean(nm))} · Obecnie: {h.pct(_last(s.get('net_margin')))}"))

    _, roe = h.sorted_items(s.get("roe"))
    out.append(("ROE", "Zwrot z kapitału własnego (%).",
                roe_chart.fig_roe(hist),
                f"Śr: {h.pct(h.mean(roe))} · Max: {h.pct(max(roe) if roe else None)} · "
                f"Min: {h.pct(min(roe) if roe else None)}"))

    out.append(("Free Cash Flow", "Wolne przepływy pieniężne (zielone +, czerwone −).",
                cashflow_chart.fig_fcf(hist), ""))

    out.append(("Net Debt", "Dług netto; wartości ujemne = gotówka netto.",
                debt_chart.fig_net_debt(hist), ""))

    pe_fig, pe_comment = pe_chart.fig_pe_history(hist, row.get("trailing_pe"))
    out.append(("P/E History ★", "Roczne P/E z pasmami (tanio/neutralnie/drogo).",
                pe_fig, pe_comment or ""))

    ds = dividend_chart.dividend_stats(hist)
    out.append(("Dividend History", "Dywidenda na akcję (do 20 lat).",
                dividend_chart.fig_dividends(hist),
                f"Div CAGR: {h.pct(ds['cagr'])} · Śr. payout: {h.pct(ds['avg_payout'])} · "
                f"Lat wypłat: {ds['years_paid']}"))

    trend = eps_chart.shares_trend(hist)
    badge = {"buyback": "🔽 Buyback (skup akcji)", "dilution": "🔼 Equity dilution",
             "flat": "≈ Stała liczba akcji"}.get(trend, "")
    out.append(("Shares Outstanding", "Liczba akcji w obiegu.",
                eps_chart.fig_shares(hist), badge))

    _, eps = h.sorted_items(s.get("eps"))
    out.append(("EPS", "Zysk na akcję: historia + prognoza analityków (linia kropkowana).",
                eps_chart.fig_eps(hist), f"CAGR: {h.pct(h.cagr(eps))}"))

    out.append(("Book Value / Share", "Wartość księgowa na akcję.",
                eps_chart.fig_book_value(hist), ""))

    _, roic = h.sorted_items(s.get("roic"))
    out.append(("ROIC", "Zwrot z zainwestowanego kapitału (przybliżony).",
                roe_chart.fig_roic(hist), f"Średnia: {h.pct(h.mean(roic))}"))

    out.append(("Operating Margin", "Marża operacyjna (%) ze średnią.",
                margin_chart.fig_operating_margin(hist), ""))
    return out


# ---------------- AI: interpretacja + oceny ----------------

def _fin_ai_path(ticker: str) -> str:
    return os.path.join(config.CACHE_DIR, f"finai_{ticker.replace('.', '_')}.json")


def _metrics_text(hist, row) -> str:
    s = hist["series"]
    _, rev = h.sorted_items(s.get("revenue"))
    _, eps = h.sorted_items(s.get("eps"))
    _, nm = h.sorted_items(s.get("net_margin"))
    lines = [
        f"Revenue CAGR: {h.pct(h.cagr(rev))}, ostatni przychod: {h.human(_last(s.get('revenue')))}",
        f"EPS CAGR: {h.pct(h.cagr(eps))}",
        f"Marza netto ostatnia: {h.pct(_last(s.get('net_margin')))}, srednia: {h.pct(h.mean(nm))}",
        f"ROE ostatnie: {h.pct(_last(s.get('roe')))}, ROIC: {h.pct(_last(s.get('roic')))}",
        f"FCF ostatni: {h.human(_last(s.get('fcf')))}",
        f"Dlug netto: {h.human(_last(s.get('net_debt')))}, EBITDA: {h.human(_last(s.get('ebitda')))}",
        f"P/E: {h.num(row.get('trailing_pe'))}",
        f"Dywidenda/akcje ost.: {h.num(_last(s.get('dividend_ps')), 2)}",
    ]
    return "\n".join(lines)


SYSTEM_FIN = (
    "Jestes analitykiem finansowym. Na podstawie podanych metryk oceniasz kondycje "
    "finansowa i wycene spolki. Piszesz zwiezle, konkretnie, po polsku."
)


def interpret(ticker: str, hist: dict, row: dict, force: bool = False) -> dict:
    path = _fin_ai_path(ticker)
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    prompt = f"""Metryki spolki {row.get('name', ticker)} ({ticker}):
{_metrics_text(hist, row)}

Napisz podsumowanie (MAX 250 slow) odpowiadajace na pytania: czy przychody rosna,
czy zysk jest stabilny, czy marze rosna, czy FCF jest zdrowy, czy zadluzenie jest
pod kontrola, czy wycena jest atrakcyjna, czy dywidenda rosnie, czy biznes jest
przewidywalny. Zwroc WYLACZNIE JSON:
{{"summary": "<max 250 slow>", "financial_quality": <int 0-100>,
  "valuation": "<Cheap|Fair|Expensive>"}}"""

    data_ = ai_research.complete_json(SYSTEM_FIN, prompt, max_tokens=2048)
    data_["ticker"] = ticker
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    return data_


def load_interpret(ticker: str) -> dict | None:
    path = _fin_ai_path(ticker)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------- Render sekcji ----------------

def render(ticker: str, row: dict):
    st.subheader("📊 Financial Charts")
    st.caption("Wykresy finansowe z danych Yahoo Finance. ~5 lat historii + "
               "prognoza analityków na 2 kolejne lata dla przychodów i EPS "
               "(darmowe dane nie sięgają dalej). Dywidendy i P/E — dłużej. "
               "Brakujące dane pokazywane są jako komunikat, nie błąd.")

    with st.spinner("Ładuję historię finansową..."):
        hist = _hist(ticker)

    # Wykres ceny akcji (pierwszy) z przelacznikiem okresu
    st.markdown(f"**Kurs akcji — {row.get('name', ticker)}**")
    period = st.segmented_control("Okres", list(price_chart.PERIODS.keys()),
                                  default="1 rok", key=f"pxper_{ticker}",
                                  label_visibility="collapsed")
    pfig = price_chart.fig_price(hist.get("prices", {}),
                                 price_chart.PERIODS.get(period or "1 rok", 1))
    if pfig is None:
        st.info("Brak danych cenowych dla tej spółki.")
    else:
        st.plotly_chart(pfig, use_container_width=True, theme="streamlit",
                        config=h.PLOTLY_CONFIG)
    st.divider()

    # KPI kafelki
    kpis = _kpis(hist, row)
    cols = st.columns(3)
    for i, (label, val) in enumerate(kpis):
        cols[i % 3].metric(label, val)

    st.divider()

    # Karty wykresow w 2 kolumnach
    specs = _specs(hist, row)
    for i in range(0, len(specs), 2):
        c1, c2 = st.columns(2)
        _card(c1, *specs[i])
        if i + 1 < len(specs):
            _card(c2, *specs[i + 1])

    # AI interpretacja
    st.divider()
    st.markdown("**🤖 Automatyczna interpretacja AI**")
    fin = load_interpret(ticker)
    if st.button("Wygeneruj podsumowanie finansowe AI",
                 key=f"finai_{ticker}", disabled=not ai_research.available()):
        with st.spinner("Analizuję kondycję finansową..."):
            try:
                fin = interpret(ticker, hist, row, force=True)
            except Exception as e:
                st.error(f"Błąd interpretacji: {e}")
    if not ai_research.available():
        st.caption("Wymaga GEMINI_API_KEY.")
    if fin:
        q = fin.get("financial_quality")
        val = fin.get("valuation", "—")
        val_pl = {"Cheap": "🟢 Tania", "Fair": "🟡 Uczciwa",
                  "Expensive": "🔴 Droga"}.get(val, val)
        m1, m2 = st.columns(2)
        m1.metric("Financial Quality", f"{q}/100" if h.is_num(q) else "—")
        m2.metric("Wycena", val_pl)
        st.info(fin.get("summary", ""))

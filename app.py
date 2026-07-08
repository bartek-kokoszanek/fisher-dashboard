"""Dashboard Fishera — Streamlit.

Uruchom:  py -m streamlit run app.py
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

import ai_research
import config
import data_fetch
import fisher_score

# Na Streamlit Community Cloud klucz API wpisujesz w panelu Secrets. Przenosimy go
# do zmiennej srodowiskowej, bo ai_research.py i SDK Anthropic czytaja z os.environ.
try:
    if "ANTHROPIC_API_KEY" in st.secrets and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass  # brak pliku secrets lokalnie — to normalne

st.set_page_config(page_title="Fisher Dashboard", page_icon="📈", layout="wide")

# --- Metryki: ladne etykiety do tabeli subscore ---
METRIC_LABELS = {
    "revenue_cagr": "Wzrost sprzedazy (CAGR)",
    "revenue_growth_yoy": "Dynamika r/r",
    "gross_margin": "Marza brutto",
    "operating_margin": "Marza operacyjna",
    "margin_trend": "Trend marzy",
    "rnd_intensity": "Nacisk na R&D",
    "roe": "ROE",
    "fcf_margin": "Marza FCF",
    "low_dilution": "Brak rozwodnienia",
    "low_leverage": "Niskie zadluzenie",
}


@st.cache_data(show_spinner=False)
def load_universe(force: bool):
    rows = data_fetch.get_many(config.all_tickers(), force=force)
    out = []
    for raw in rows:
        if "error" in raw:
            out.append({**raw, "score": None, "coverage": 0})
            continue
        res = fisher_score.compute_score(raw)
        ai = ai_research.load_cached(raw["ticker"])
        quality = ai.get("quality_score") if ai else None
        # Wynik laczny: 70% ilosciowy + 30% jakosciowy (jesli jest research)
        if res["score"] is not None and quality is not None:
            combined = round(0.7 * res["score"] + 0.3 * quality, 1)
        else:
            combined = res["score"]
        out.append({
            **raw,
            "score": res["score"],
            "quality": quality,
            "combined": combined,
            "coverage": res["coverage"],
            "subscores": res["subscores"],
            "verdict": fisher_score.verdict(combined),
        })
    return out


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


# ---------------- Sidebar ----------------
st.sidebar.title("📈 Fisher Dashboard")
st.sidebar.caption("Typowanie spolek Nasdaq + GPW wg 15 zasad Philipa Fishera")

markets = st.sidebar.multiselect("Gielda", ["Nasdaq", "GPW"], default=["Nasdaq", "GPW"])
min_cov = st.sidebar.slider("Min. pokrycie danych (%)", 0, 100, 40, step=10)

if st.sidebar.button("🔄 Odswiez dane z Yahoo (wolne)"):
    load_universe.clear()
    with st.spinner("Pobieram fundamenty..."):
        load_universe(force=True)
    st.sidebar.success("Zaktualizowano.")

st.sidebar.divider()
st.sidebar.subheader("Research AI (jakosciowy)")
if ai_research.available():
    st.sidebar.success("ANTHROPIC_API_KEY wykryty")
else:
    st.sidebar.warning("Ustaw ANTHROPIC_API_KEY, aby wlaczyc oceny jakosciowe")
use_web = st.sidebar.checkbox("Uzyj wyszukiwania w sieci", value=False)

# ---------------- Dane ----------------
data = load_universe(force=False)
df = pd.DataFrame(data)
df = df[df["market"].isin(markets)]
df = df[df["coverage"].fillna(0) >= min_cov]

# ---------------- Ranking ----------------
st.title("Ranking Fishera")
st.caption("Wynik 0-100. Laczy proxy ilosciowe (fundamenty) z ocena jakosciowa AI, jesli dostepna.")

view = df.sort_values("combined", ascending=False, na_position="last").copy()
table = view[["ticker", "name", "market", "combined", "score", "quality",
              "coverage", "verdict"]].rename(columns={
    "ticker": "Ticker", "name": "Spolka", "market": "Gielda",
    "combined": "Wynik", "score": "Ilosciowy", "quality": "Jakosciowy (AI)",
    "coverage": "Pokrycie %", "verdict": "Werdykt"})

st.dataframe(
    table,
    width="stretch", hide_index=True,
    column_config={
        "Wynik": st.column_config.ProgressColumn("Wynik", min_value=0, max_value=100, format="%.1f"),
        "Pokrycie %": st.column_config.NumberColumn(format="%d%%"),
    },
)

st.download_button(
    "⬇ Eksport watchlisty do TradingView (CSV tickerow)",
    data="\n".join(view["ticker"].tolist()),
    file_name="fisher_watchlist.txt",
    help="Wklej do TradingView: Watchlist -> Import / paste list. GPW: dodaj prefiks gieldy jesli TV tego wymaga.",
)

# ---------------- Szczegoly spolki ----------------
st.divider()
st.header("Analiza spolki")
choices = view["ticker"].tolist()
if choices:
    pick = st.selectbox("Wybierz spolke", choices,
                        format_func=lambda t: f"{t} — {config.NAMES.get(t, view.set_index('ticker').loc[t, 'name'])}")
    row = df[df["ticker"] == pick].iloc[0].to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wynik laczny", row.get("combined") or "—")
    c2.metric("Ilosciowy", row.get("score") or "—")
    c3.metric("Jakosciowy (AI)", row.get("quality") or "—")
    c4.metric("Pokrycie danych", f"{row.get('coverage', 0):.0f}%")

    left, right = st.columns(2)

    with left:
        st.subheader("Rozbicie ilosciowe")
        subs = row.get("subscores") or {}
        srows = []
        for m, label in METRIC_LABELS.items():
            if m in subs:
                srows.append({"Metryka": label, "Pkt (0-100)": subs[m],
                              "Wartosc surowa": fmt_pct(row.get(fisher_score.RAW_KEY[m]))})
        st.dataframe(pd.DataFrame(srows), hide_index=True, width="stretch")
        st.caption(f"Sektor: {row.get('sector') or '—'} · "
                   f"Kapitalizacja: {row.get('market_cap') or '—'} {row.get('currency') or ''}")

    with right:
        st.subheader("Ocena jakosciowa (Fisher)")
        ai = ai_research.load_cached(pick)
        if st.button("🤖 Uruchom research AI dla tej spolki",
                     disabled=not ai_research.available()):
            with st.spinner("Claude analizuje jakosc..."):
                try:
                    ai = ai_research.research(pick, row.get("name", pick),
                                              row.get("market", ""),
                                              use_web=use_web, force=True)
                    load_universe.clear()
                    st.success("Gotowe. Odswiez ranking, by uwzglednic wynik.")
                except Exception as e:
                    st.error(f"Blad research: {e}")
        if ai:
            for k, label in ai_research.DIMENSIONS.items():
                sc = ai.get("scores", {}).get(k)
                note = ai.get("notes", {}).get(k, "")
                st.write(f"**{label.split('(')[0].strip()}** — {sc}/100")
                if note:
                    st.caption(note)
            st.info(ai.get("summary", ""))
            st.caption(f"Model: {ai.get('model')} · pewnosc: {ai.get('confidence')}% · "
                       f"{'z siecia' if ai.get('used_web') else 'bez sieci'}")
        else:
            st.caption("Brak researchu AI. Uruchom przyciskiem powyzej.")
else:
    st.info("Brak spolek spelniajacych filtry. Zluzuj min. pokrycie lub odswiez dane.")

st.divider()
st.caption("⚠️ Narzedzie edukacyjne — nie stanowi porady inwestycyjnej. "
           "Dane: Yahoo Finance (yfinance). Metoda: Philip Fisher, 'Common Stocks and Uncommon Profits'.")

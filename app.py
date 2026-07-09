"""Dashboard Fishera — Streamlit.

Uruchom:  py -m streamlit run app.py
"""
from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

import ai_research
import config
import data_fetch
import financial_charts
import fisher_score
import gpw_indices
import gurus
import pwpa
import research_deep
import universe
import watchlists
from gpw_tickers import GPW_TICKERS

# Na Streamlit Community Cloud klucz API wpisujesz w panelu Secrets. Przenosimy go
# do zmiennej srodowiskowej, bo ai_research.py czyta klucz z os.environ.
try:
    _bridge = ["GEMINI_API_KEY", "GEMINI_API_KEYS", "LLM_API_KEY", "LLM_BASE_URL",
               "LLM_MODEL", "DEEP_MODEL", "GITHUB_TOKEN", "GIST_ID"]
    _bridge += [f"GEMINI_API_KEY_{i}" for i in range(2, 6)]
    for _k in _bridge:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = st.secrets[_k]
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


def build_row(raw: dict, guru_key: str) -> dict:
    """Surowe dane -> wiersz rankingu wg wybranej strategii (+ ocena AI z cache)."""
    if "error" in raw:
        return {**raw, "score": None, "coverage": 0}
    weights = gurus.get(guru_key)["weights"]
    res = fisher_score.compute_score(raw, weights)
    ai = ai_research.load_cached(raw["ticker"], guru_key)
    quality = ai.get("quality_score") if ai else None
    # Wynik laczny: 70% ilosciowy + 30% jakosciowy (jesli jest research)
    if res["score"] is not None and quality is not None:
        combined = round(0.7 * res["score"] + 0.3 * quality, 1)
    else:
        combined = res["score"]
    return {
        **raw,
        "score": res["score"],
        "quality": quality,
        "combined": combined,
        "coverage": res["coverage"],
        "subscores": res["subscores"],
        "verdict": fisher_score.verdict(combined),
    }


@st.cache_data(show_spinner=False)
def load_raws(force: bool):
    """Surowe dane bazowego uniwersum (cache Streamlita + cache plikowy 24h)."""
    return data_fetch.get_many(config.all_tickers(), force=force)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_pool():
    """Pelna pula symboli Nasdaq+GPW do wyszukiwarki."""
    return universe.all_symbols()


@st.cache_data(show_spinner=False, ttl=12 * 3600)
def pwpa_reports(ticker: str):
    try:
        return pwpa.reports_for(ticker)
    except Exception:
        return []


def render_pwpa(pick: str):
    """Blok rekomendacji z raportow GPW PWPA (cena docelowa + powody + zrodlo)."""
    try:
        reps = pwpa_reports(pick)
    except Exception:
        return
    if not reps:
        st.caption("📄 Spółka nie jest objęta programem GPW PWPA "
                   "(brak raportów analitycznych w tym źródle).")
        return

    with st.expander(f"📄 Rekomendacje analityków — GPW PWPA ({len(reps)} raporty)",
                     expanded=True):
        for r in reps:
            st.markdown(f"**{r['date']}** · {r['type']} · {r['firm']} — "
                        f"[źródło (PDF)]({r['pdf_url']})")

        latest = reps[0]
        cached = pwpa.load_extract(latest["pdf_url"])
        if st.button("🎯 Wyciągnij cenę docelową i uzasadnienie (AI, najnowszy raport)",
                     key=f"pwpa_{pick}", disabled=not ai_research.available()):
            with st.spinner("Czytam raport i wyciągam wycenę..."):
                try:
                    cached = pwpa.extract(latest, force=True)
                except Exception as e:
                    st.error(f"Nie udało się przetworzyć raportu: {e}")
        if not ai_research.available():
            st.caption("Wyciąganie ceny docelowej wymaga GEMINI_API_KEY.")
        if cached:
            tp = cached.get("target_price")
            cur = cached.get("currency") or ""
            rec = cached.get("recommendation") or "—"
            pc1, pc2 = st.columns(2)
            pc1.metric("Cena docelowa", f"{tp} {cur}".strip() if tp else "brak w raporcie")
            pc2.metric("Rekomendacja", rec)
            if cached.get("summary"):
                st.info(cached["summary"])
            if cached.get("rationale"):
                st.markdown("**Uzasadnienie:**")
                for pt in cached["rationale"]:
                    st.markdown(f"- {pt}")
            st.caption(f"Źródło: {cached.get('firm')} ({cached.get('date')}) · "
                       f"[raport PDF]({cached.get('source_url')})")


def get_wl() -> dict:
    if "watchlists" not in st.session_state:
        st.session_state["watchlists"] = watchlists.load()
    return st.session_state["watchlists"]


def save_wl():
    err = watchlists.save(st.session_state["watchlists"])
    if err:
        st.sidebar.warning(err)


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


# ---------------- Sidebar ----------------
st.sidebar.title("📈 Dashboard inwestora")
st.sidebar.caption("Typowanie spolek Nasdaq + GPW wg strategii znanych inwestorow")

guru_key = st.sidebar.selectbox(
    "🧭 Strategia inwestora", gurus.options(),
    format_func=lambda k: gurus.get(k)["name"],
)
st.sidebar.caption(gurus.get(guru_key)["desc"])

segments = st.sidebar.multiselect(
    "Segment", list(gpw_indices.ALL_SEGMENTS),
    default=["Nasdaq", "WIG20", "mWIG40"],
    help="Nasdaq-AI = kuratorowany podzbior spolek AI. WIG-pozostale = spolki "
         "GPW spoza WIG20/mWIG40/sWIG80 (pierwsze zaladowanie potrwa).",
)
min_cov = st.sidebar.slider("Min. pokrycie danych (%)", 0, 100, 40, step=10)

if st.sidebar.button("🔄 Odswiez dane z Yahoo (wolne)"):
    load_raws.clear()
    prog = st.sidebar.progress(0.0, text="Pobieram fundamenty...")
    data_fetch.get_many(
        config.all_tickers(), force=True,
        progress=lambda i, n, tk: prog.progress(i / n, text=f"{tk} ({i}/{n})"),
    )
    prog.empty()
    st.sidebar.success("Zaktualizowano.")

st.sidebar.divider()
st.sidebar.subheader("📋 Listy obserwacyjne")
wl = get_wl()
wl_names = list(wl["lists"].keys())
wl_filter = st.sidebar.selectbox("Pokaz spolki", ["Wszystkie"] + wl_names)

new_list = st.sidebar.text_input("Nowa lista (nazwa)", placeholder="np. Moj portfel")
if st.sidebar.button("➕ Utworz liste", disabled=not new_list.strip()):
    name = new_list.strip()
    if name in wl["lists"]:
        st.sidebar.warning("Taka lista juz istnieje.")
    else:
        wl["lists"][name] = []
        save_wl()
        st.rerun()

if wl_names:
    with st.sidebar.expander("Zarzadzaj / backup"):
        to_del = st.selectbox("Usun liste", ["—"] + wl_names)
        if to_del != "—" and st.button(f"🗑 Usun '{to_del}'"):
            wl["lists"].pop(to_del, None)
            save_wl()
            st.rerun()
        st.download_button("⬇ Eksport list (JSON)",
                           data=json.dumps(wl, ensure_ascii=False, indent=2),
                           file_name="watchlists.json")
        up = st.file_uploader("Import list (JSON)", type="json")
        if up is not None and st.button("Wczytaj import"):
            try:
                imported = json.load(up)
                assert isinstance(imported.get("lists"), dict)
                st.session_state["watchlists"] = imported
                save_wl()
                st.rerun()
            except Exception as e:
                st.error(f"Nieprawidlowy plik: {e}")

if watchlists.backend() == "gist":
    st.sidebar.caption("Zapis: GitHub Gist ✅ (trwaly)")
else:
    st.sidebar.caption("Zapis: lokalny plik — na Streamlit Cloud listy znikna przy "
                       "restarcie. Dodaj GITHUB_TOKEN i GIST_ID w Secrets, by zapisywac do Gista.")

st.sidebar.divider()
st.sidebar.subheader("Research AI (jakosciowy)")
_nkeys = ai_research.key_count()
if _nkeys:
    st.sidebar.success(f"Klucze API Gemini: {_nkeys}"
                       + (" (rotacja przy limicie)" if _nkeys > 1 else ""))
else:
    st.sidebar.warning("Ustaw GEMINI_API_KEY (darmowy, Google AI Studio), aby wlaczyc oceny jakosciowe")
st.sidebar.caption(f"Model: {ai_research.MODEL}")

# ---------------- Dane ----------------
raws = load_raws(force=False)
# spolki spoza bazowego uniwersum (wyszukiwarka, listy, WIG-pozostale) — surowe
extra_raws = st.session_state.setdefault("extra_raws", {})
known = {r["ticker"] for r in raws}

# spolki zapisane na listach, ktorych nie ma w bazowym uniwersum — dociagnij
missing_listed = [t for t in watchlists.all_listed_tickers(wl)
                  if t not in known and t not in extra_raws]
if missing_listed:
    with st.spinner(f"Pobieram spolki z Twoich list ({len(missing_listed)})..."):
        for t in missing_listed:
            extra_raws[t] = data_fetch.get(t)

# segment WIG-pozostale: leniwe dociagniecie spolek spoza indeksow
if "WIG-pozostale" in segments:
    rest = [t for t in GPW_TICKERS
            if "WIG-pozostale" in gpw_indices.segments_of(t)
            and t not in known and t not in extra_raws]
    if rest:
        st.info(f"Segment WIG-pozostale: pobieram {len(rest)} spolek spoza "
                "indeksow — pierwszy raz moze potrwac kilka minut.")
        prog = st.progress(0.0)
        for i, t in enumerate(rest):
            extra_raws[t] = data_fetch.get(t)
            prog.progress((i + 1) / len(rest), text=f"{t} ({i + 1}/{len(rest)})")
        prog.empty()

all_raws = raws + [r for t, r in extra_raws.items() if t not in known]
data = [build_row(r, guru_key) for r in all_raws]
df = pd.DataFrame(data)
df["segments"] = df["ticker"].map(gpw_indices.segments_of)
df["segment"] = df["ticker"].map(gpw_indices.segment_label)
_sel = set(segments)
df = df[df["segments"].map(lambda s: bool(s & _sel))]
df = df[df["coverage"].fillna(0) >= min_cov]
if wl_filter != "Wszystkie":
    df = df[df["ticker"].isin(set(wl["lists"].get(wl_filter, [])))]

# ---------------- Ranking ----------------
_g = gurus.get(guru_key)
st.title(f"Ranking wg strategii: {_g['name']}")
st.caption(f"{_g['desc']} · Wynik 0-100 laczy proxy ilosciowe (fundamenty) "
           "z ocena jakosciowa AI, jesli dostepna. Strategie to edukacyjne "
           "przyblizenia filozofii inwestorow, nie ich prawdziwe algorytmy.")

view = df.sort_values("combined", ascending=False, na_position="last").copy()

# kolumny w stylu skanera TradingView
for col in ("price", "target_mean", "target_upside", "analyst_count",
            "recommendation_mean", "recommendation_key", "trailing_pe", "market_cap"):
    if col not in view.columns:
        view[col] = None
view["target_upside_pct"] = view["target_upside"].astype(float) * 100


def _rec_label(r):
    m = r.get("recommendation_mean")
    k = r.get("recommendation_key")
    if m is None or (isinstance(m, float) and pd.isna(m)):
        return None
    key = "" if (k is None or (isinstance(k, float) and pd.isna(k))) else str(k).replace("_", " ")
    return f"{float(m):.1f} · {key}".strip(" ·")


view["rec_label"] = view.apply(_rec_label, axis=1)

table = view[["ticker", "name", "segment", "price", "target_mean",
              "target_upside_pct", "analyst_count", "rec_label", "trailing_pe",
              "market_cap", "combined", "coverage", "verdict"]].rename(columns={
    "ticker": "Symbol", "name": "Spolka", "segment": "Segment", "price": "Cena",
    "target_mean": "Cena docelowa", "target_upside_pct": "Do celu %",
    "analyst_count": "Rekom.", "rec_label": "Ocena analitykow",
    "trailing_pe": "C/Z", "market_cap": "Kap. rynk.",
    "combined": "Wynik", "coverage": "Pokrycie %", "verdict": "Werdykt"})


def _upside_color(v):
    if pd.isna(v):
        return ""
    return "color: #16a34a; font-weight: 600" if v >= 0 else "color: #dc2626; font-weight: 600"


styled = table.style.map(_upside_color, subset=["Do celu %"])

st.dataframe(
    styled,
    width="stretch", hide_index=True,
    column_config={
        "Cena": st.column_config.NumberColumn(format="%.2f"),
        "Cena docelowa": st.column_config.NumberColumn(format="%.2f"),
        "Do celu %": st.column_config.NumberColumn(format="%+.1f%%"),
        "Rekom.": st.column_config.NumberColumn(format="%d"),
        "C/Z": st.column_config.NumberColumn(format="%.1f"),
        "Kap. rynk.": st.column_config.NumberColumn(format="compact"),
        "Wynik": st.column_config.ProgressColumn("Wynik", min_value=0, max_value=100, format="%.1f"),
        "Pokrycie %": st.column_config.NumberColumn(format="%d%%"),
    },
)
st.caption("Cena i cena docelowa w walucie notowan (Nasdaq: USD, GPW: PLN). "
           "Rekom. = liczba analitykow pokrywajacych spolke; ocena 1=Strong Buy ... 5=Sell. "
           "Dla czesci spolek GPW konsensus analitykow jest niedostepny.")

st.download_button(
    "⬇ Eksport watchlisty do TradingView (CSV tickerow)",
    data="\n".join(view["ticker"].tolist()),
    file_name="fisher_watchlist.txt",
    help="Wklej do TradingView: Watchlist -> Import / paste list. GPW: dodaj prefiks gieldy jesli TV tego wymaga.",
)

# ---------------- Szczegoly spolki ----------------
st.divider()
st.header("Analiza spolki")

# Wyszukiwarka dowolnej spolki z pelnej puli Nasdaq (~5500) + GPW (~370)
pool = load_pool()
searched = st.selectbox(
    "🔍 Wyszukaj dowolna spolke z Nasdaq/GPW (wpisz ticker lub fragment nazwy)",
    options=sorted(pool.keys()),
    index=None,
    format_func=lambda t: f"{t} — {pool.get(t, t)}",
    placeholder="np. MU, DINO, ORLEN, MICROSOFT...",
)
if searched and searched not in set(df["ticker"]):
    with st.spinner(f"Pobieram i punktuje {searched}..."):
        raw = data_fetch.get(searched)
        st.session_state["extra_raws"][searched] = raw
        new_row = build_row(raw, guru_key)
    if "error" in new_row:
        st.warning(f"Nie udalo sie pobrac danych dla {searched}: {new_row['error']}")
    elif (new_row.get("coverage") or 0) < min_cov:
        st.warning(f"{searched} ma pokrycie danych {new_row.get('coverage', 0):.0f}% — "
                   f"ponizej filtra ({min_cov}%). Obniz suwak, by zobaczyc spolke.")
    else:
        st.rerun()

choices = view["ticker"].tolist()
if choices:
    default_idx = choices.index(searched) if searched in choices else 0
    pick = st.selectbox("Wybierz spolke", choices, index=default_idx,
                        format_func=lambda t: f"{t} — {config.NAMES.get(t, view.set_index('ticker').loc[t, 'name'])}")
    row = df[df["ticker"] == pick].iloc[0].to_dict()

    # --- przypisanie spolki do list obserwacyjnych ---
    on_lists = [n for n, tks in wl["lists"].items() if pick in tks]
    lc1, lc2, lc3 = st.columns([2, 1, 2])
    addable = [n for n in wl_names if n not in on_lists]
    with lc1:
        target = st.selectbox("Dodaj do listy", addable if addable else ["—"],
                              disabled=not addable, label_visibility="collapsed")
    with lc2:
        if st.button("➕ Dodaj do listy", disabled=not addable):
            wl["lists"][target].append(pick)
            save_wl()
            st.rerun()
    with lc3:
        if on_lists:
            st.caption("Na listach: " + ", ".join(on_lists))
            rm = st.selectbox("Usun z listy", on_lists, label_visibility="collapsed")
            if st.button("➖ Usun z listy"):
                wl["lists"][rm].remove(pick)
                save_wl()
                st.rerun()
        elif not wl_names:
            st.caption("Utworz liste w panelu bocznym, by zapisywac spolki.")

    def _num(v):
        return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else v

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wynik laczny", _num(row.get("combined")))
    c2.metric("Ilosciowy", _num(row.get("score")))
    c3.metric("Jakosciowy (AI)", _num(row.get("quality")))
    c4.metric("Pokrycie danych", f"{row.get('coverage', 0):.0f}%")

    # --- Rekomendacje analitykow z raportow GPW PWPA (tylko GPW) ---
    if pick.endswith(".WA"):
        render_pwpa(pick)

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
        st.subheader(f"Ocena jakosciowa ({gurus.get(guru_key)['name']})")
        ai = ai_research.load_cached(pick, guru_key)
        if st.button("🤖 Uruchom research AI dla tej spolki",
                     disabled=not ai_research.available()):
            with st.spinner(f"Model ocenia przez pryzmat: {gurus.get(guru_key)['name']}..."):
                try:
                    ai = ai_research.research(pick, row.get("name", pick),
                                              row.get("market", ""),
                                              guru=guru_key, force=True)
                    st.rerun()
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
            st.caption(f"Model: {ai.get('model')} · pewnosc: {ai.get('confidence')}%")
        else:
            st.caption("Brak researchu AI dla tej strategii. Uruchom przyciskiem powyzej.")

    # --- Najwieksze zalety / wady (z researchu AI) ---
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

    # ---------------- Financial Charts ----------------
    st.divider()
    financial_charts.render(pick, row)

    # ---------------- Deep research ----------------
    st.divider()
    st.subheader("🔎 Deep research: sentyment rynku + YouTube + relacje inwestorskie")
    st.caption(f"Analiza ostatnich {research_deep.MONTHS_BACK} miesiecy: artykuly "
               "(Google Search), filmy z YouTube (tytuly + transkrypty, gdy dostepne) "
               "i raporty z dzialu IR spolki. Sentyment NIE wplywa na Wynik strategii. "
               "Trwa 1-3 min.")
    deep = research_deep.load_cached(pick)
    if st.button("🔎 Uruchom deep research dla tej spolki",
                 disabled=not research_deep.available()):
        with st.spinner("Szukam filmow, artykulow i raportow IR..."):
            try:
                deep = research_deep.research(pick, row.get("name", pick),
                                              row.get("market", ""),
                                              row.get("website"), force=True)
            except Exception as e:
                st.error(f"Blad deep research: {e}")
    if not research_deep.available():
        st.caption("Wymaga GEMINI_API_KEY (grounding dziala tylko z Gemini).")
    if deep:
        s = deep.get("sentiment")
        dm1, dm2 = st.columns([1, 3])
        with dm1:
            if s is not None:
                st.metric("Sentyment rynku", f"{s:+d}", delta=int(s),
                          help="-100 skrajnie negatywny ... +100 skrajnie pozytywny")
            st.caption(f"Pewnosc: {deep.get('confidence', '—')}%")
        with dm2:
            st.info(deep.get("sentiment_summary", ""))
        if deep.get("key_news"):
            with st.expander(f"📰 Najwazniejsze newsy ({len(deep['key_news'])})",
                             expanded=True):
                for n in deep["key_news"]:
                    st.write(f"**{n.get('title', '')}** _{n.get('date', '')}_")
                    st.caption(n.get("takeaway", ""))
        if deep.get("youtube_findings"):
            with st.expander(f"▶️ YouTube ({len(deep['youtube_findings'])})"):
                if deep.get("yt_note"):
                    st.caption(f"ℹ️ {deep['yt_note']}")
                for v in deep["youtube_findings"]:
                    st.write(f"**{v.get('title', '')}** — {v.get('channel', '')} "
                             f"_{v.get('date', '')}_")
                    st.caption(v.get("takeaway", ""))
        if deep.get("ir_findings"):
            with st.expander("🏢 Relacje inwestorskie / raporty"):
                st.write(deep["ir_findings"])
        if deep.get("sources"):
            with st.expander(f"🔗 Zrodla ({len(deep['sources'])})"):
                for src in deep["sources"]:
                    st.markdown(f"- [{src.get('title', src['url'])}]({src['url']})")
        st.caption(f"Model: {deep.get('model')} · {deep.get('researched_at', '')}")
    else:
        st.caption("Brak deep researchu dla tej spolki. Uruchom przyciskiem powyzej.")
else:
    st.info("Brak spolek spelniajacych filtry. Zluzuj min. pokrycie lub odswiez dane.")

st.divider()
st.caption("⚠️ Narzedzie edukacyjne — nie stanowi porady inwestycyjnej. "
           "Dane: Yahoo Finance (yfinance). Strategie inwestorow sa edukacyjnymi "
           "przyblizeniami ich filozofii, nie prawdziwymi algorytmami.")

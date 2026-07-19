"""Dashboard Fishera — Streamlit.

Uruchom:  py -m streamlit run app.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_sortables import sort_items

import ai_research
import config
import data_fetch
import decision_panel
import financial_charts
import fisher_score
import gpw_indices
import gurus
import pwpa
import research_deep
import universe
import watchlists
import yt_transcribe
from charts.helpers import fmt_dt
from gpw_tickers import GPW_TICKERS

# Na Streamlit Community Cloud klucz API wpisujesz w panelu Secrets. Przenosimy go
# do zmiennej srodowiskowej, bo ai_research.py czyta klucz z os.environ.
try:
    _bridge = ["GEMINI_API_KEY", "GEMINI_API_KEYS", "LLM_API_KEY", "LLM_BASE_URL",
               "LLM_MODEL", "LLM_MODELS", "DEEP_MODEL", "STT_MODEL",
               "GITHUB_TOKEN", "GIST_ID", "YT_PROXY", "ALPHAVANTAGE_API_KEY",
               "YOUTUBE_API_KEY"]
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


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_raws(force: bool, _v: int = 4):
    """Surowe dane bazowego uniwersum (cache Streamlita + cache plikowy 24h).

    ttl + _v: bez ttl wpisy w pamieci zyly wiecznie (deploy na Streamlit
    Cloud to hot-reload bez restartu procesu), wiec tabela serwowala stare
    dane mimo bumpu wersji cache plikowego. Podbij _v przy zmianie schematu
    danych raw_*."""
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


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def yt_videos(ticker: str, name: str, market: str):
    try:
        return yt_transcribe.find_videos(name, ticker, market)
    except Exception:
        return []


def render_pwpa(pick: str, label: str):
    """Blok rekomendacji z raportow GPW PWPA (cena docelowa + powody + zrodlo)."""
    try:
        reps = pwpa_reports(pick)
    except Exception:
        return
    if not reps:
        st.caption("📄 Spółka nie jest objęta programem GPW PWPA "
                   "(brak raportów analitycznych w tym źródle).")
        return

    with st.expander(f"📄 Rekomendacje analityków — GPW PWPA — {label} "
                     f"({len(reps)} raporty)", expanded=True):
        for r in reps:
            st.markdown(f"**{r['date']}** · {r['type']} · {r['firm']} — "
                        f"[źródło (PDF)]({r['pdf_url']})")
        try:
            _idx_ts = datetime.fromtimestamp(
                os.path.getmtime(pwpa.INDEX_CACHE), tz=timezone.utc).isoformat()
        except OSError:
            _idx_ts = None
        st.caption(f"🗓 Źródło: **gpw.pl/gpwpa** (program PWPA) · lista raportów "
                   f"zaktualizowana {fmt_dt(_idx_ts)} (cache 12h)")

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
    st.session_state["watchlists"].setdefault("notes", {})  # notatki per spolka
    return st.session_state["watchlists"]


def save_wl():
    err = watchlists.save(st.session_state["watchlists"])
    if err:
        st.sidebar.warning(err)


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


def co_label(ticker: str, row: dict) -> str:
    """'TICKER — Nazwa spolki', do wyswietlenia przy kazdym module analizy."""
    name = row.get("name") or config.NAMES.get(ticker, ticker)
    return f"{ticker} — {name}"


def sortable_style() -> str:
    """Styl kafelkow kolumn dla motywu aplikacji (domyslnie tylko-ciemny).

    Komponent renderuje sie w iframie i nie dziedziczy motywu Streamlita, wiec
    kolory podajemy wprost — ale przez WLASNE API komponentu (custom_style),
    nie przez selektory DOM Streamlita, wiec aktualizacja frameworka tego nie
    zepsuje. Kafelki celowo sa neutralne (szarosc + blekitny akcent): czerwien
    i zielen nalezą w tej aplikacji do znaczenia (spadek / wzrost).

    Aplikacja definiuje tylko motyw ciemny (.streamlit/config.toml) — jasnej
    galezi ponizej uzyje tylko ktos, kto recznie przelaczy sie na WBUDOWANY
    jasny motyw Streamlita z menu ☰ -> Settings (wtedy dostaje domyslna,
    nie nasza, jasna palete Streamlita — kafelki dostosowuja sie do niej
    neutralnymi kolorami zamiast razic ciemnym tlem na jasnym tle).
    """
    try:
        dark = st.context.theme.type == "dark"
    except Exception:
        dark = True
    if dark:
        bg, border, chip, chip_fg = "#0f1218", "#272d3a", "#1c2230", "#e5e9f0"
        head, accent = "#8b94a7", "#5b8def"
    else:
        bg, border, chip, chip_fg = "#ffffff", "#d3d8de", "#f0f2f5", "#31333f"
        head, accent = "#6b7280", "#5b8def"
    return f"""
.sortable-component {{
    background: {bg};
    gap: 0.5rem;
}}
.sortable-container {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 0.5rem 0.6rem;
}}
.sortable-container-header {{
    color: {head};
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding-bottom: 0.4rem;
}}
.sortable-item {{
    background: {chip};
    color: {chip_fg};
    border: 1px solid {border};
    border-radius: 6px;
    font-size: 0.82rem;
    padding: 0.22rem 0.6rem;
    cursor: grab;
}}
.sortable-item:hover {{
    border-color: {accent};
    color: {accent};
}}
"""


# ---------------- Sidebar ----------------
st.sidebar.title("📈 Dashboard inwestora")
st.sidebar.caption("Typowanie spolek Nasdaq + GPW wg strategii znanych inwestorow")

guru_key = st.sidebar.selectbox(
    "🧭 Strategia inwestora", gurus.options(),
    format_func=lambda k: gurus.get(k)["name"],
)
st.sidebar.caption(gurus.get(guru_key)["desc"])

# ustawienia UI (segmenty, kolumny tabeli) trwale w tym samym zapisie co listy
wl = get_wl()
settings = wl.setdefault("settings", {})

# Nowe kolumny dopisujemy do ZAPISANEGO ukladu, zamiast chowac je w "Ukryte"
# (zapisana lista ich nie zna, wiec bez tego nikt by ich nie zobaczyl).
# Kolejnosc uzytkownika zostaje nietknieta — nowe ladują na koncu.
_COLS_VERSION = 1
if settings.get("ranking_columns") and settings.get("cols_version", 0) < _COLS_VERSION:
    for _c in ("GPW PWPA", "Wycena (AI)", "WERDYKT BRAMKI", "Sentyment rynku"):
        if _c not in settings["ranking_columns"]:
            settings["ranking_columns"].append(_c)
    settings["cols_version"] = _COLS_VERSION
    save_wl()

_saved_seg = settings.get("segments")
_seg_default = [s for s in (_saved_seg or ["WIG20", "mWIG40", "sWIG80"])
                if s in gpw_indices.ALL_SEGMENTS]
segments = st.sidebar.multiselect(
    "Segment", list(gpw_indices.ALL_SEGMENTS),
    default=_seg_default,
    help="Nasdaq-AI = kuratorowany podzbior spolek AI. S&P500 i WIG-pozostale "
         "dociagane sa leniwie (pierwsze zaladowanie potrwa kilka minut). "
         "Wybor jest zapamietywany.",
)
if segments != _saved_seg:
    settings["segments"] = segments
    save_wl()
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
_ms = ai_research.models_active()
st.sidebar.caption(f"Modele (rotacja): {', '.join(m.replace('gemini-', '') for m in _ms)}")

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
        for r in data_fetch.get_many(missing_listed):
            extra_raws[r["ticker"]] = r

# leniwe dociaganie duzych segmentow (spolki spoza bazowego uniwersum)
def _lazy_fetch(tickers, label):
    todo = [t for t in tickers if t not in known and t not in extra_raws]
    if not todo:
        return
    st.info(f"Segment {label}: pobieram {len(todo)} spolek "
            f"({data_fetch.WORKERS} rownolegle) — pierwszy raz potrwa "
            "~1-3 min, potem dane sa w cache.")
    prog = st.progress(0.0)
    for r in data_fetch.get_many(
            todo, progress=lambda i, n, tk: prog.progress(
                i / n, text=f"{tk} ({i}/{n})")):
        extra_raws[r["ticker"]] = r
    prog.empty()


if "WIG-pozostale" in segments:
    _lazy_fetch([t for t in GPW_TICKERS
                 if "WIG-pozostale" in gpw_indices.segments_of(t)], "WIG-pozostale")
if "S&P500" in segments:
    _lazy_fetch(sorted(gpw_indices.SP500), "S&P500")

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
            "recommendation_mean", "recommendation_key", "trailing_pe", "market_cap",
            "next_earnings_date", "rev_growth_est", "eps_growth_est",
            "ex_dividend_date", "dividend_pay_date", "last_dividend_value",
            "last_q_date", "last_q_revenue", "last_q_eps", "eps_surprise"):
    if col not in view.columns:
        view[col] = None
view["target_upside_pct"] = view["target_upside"].astype(float) * 100
view["rev_growth_pct"] = view["rev_growth_est"].astype(float) * 100
view["eps_growth_pct"] = view["eps_growth_est"].astype(float) * 100
view["eps_surprise_pct"] = view["eps_surprise"].astype(float) * 100


def _rec_label(r):
    m = r.get("recommendation_mean")
    k = r.get("recommendation_key")
    if m is None or (isinstance(m, float) and pd.isna(m)):
        return None
    key = "" if (k is None or (isinstance(k, float) and pd.isna(k))) else str(k).replace("_", " ")
    return f"{float(m):.1f} · {key}".strip(" ·")


view["rec_label"] = view.apply(_rec_label, axis=1)

# --- kolumny z modulow analizy (PWPA / wycena AI / bramka / sentyment) ---
# Wszystkie czytaja WYLACZNIE z cache — zero zapytan do API na wiersz.
# Indeks PWPA pobieramy RAZ dla calej tabeli (nie per spolka).
_pwpa_by_ticker: dict[str, list] = {}
try:
    for _r in pwpa.list_reports():
        _pwpa_by_ticker.setdefault(_r["ticker"], []).append(_r)
except Exception:
    pass  # brak sieci / zrodlo niedostepne -> kolumna zostaje pusta

_VALUATION_PL = {"Cheap": "🟢 Tania", "Fair": "🟡 Uczciwa", "Expensive": "🔴 Droga"}
_GATE_EMOJI = {"green": "🟢", "amber": "🟡", "red": "🔴"}


def _cell_pwpa(t: str):
    if not t.endswith(".WA"):
        return None
    reps = _pwpa_by_ticker.get(t[:-3].upper().strip())
    if not reps:
        return None
    return f"{len(reps)} · {max(r['date'] for r in reps)}"


def _cell_valuation(t: str):
    fin = financial_charts.load_interpret(t) or {}
    v = fin.get("valuation")
    return _VALUATION_PL.get(v, v) if v else None


def _cell_gate(t: str, r: dict):
    # Pokazujemy werdykt TYLKO gdy stoi za nim realna baza: scenariusze z AI
    # albo Twoje wlasne wpisy w panelu. Baza czysto mechaniczna wyprowadza
    # scenariusz 3-letni z 12-miesiecznej ceny docelowej, wiec CAGR wypada
    # ponizej progu praktycznie zawsze — kolumna pokazywalaby "NIE KUPUJ"
    # w kazdym wierszu i udawala werdykt, ktorym nie jest.
    if decision_panel.load_cached(t) is None and \
            not (wl.get("decision") or {}).get(t):
        return None
    try:
        v = decision_panel.verdict_for(t, r, wl)
    except Exception:
        return None
    if not v:
        return None
    # etykiety panelu bywaja dlugie ("... — pol pozycji") — w tabeli tniemy
    # do czesci glownej, ale bierzemy ja z panelu, wiec nie moze sie rozjechac
    return f"{_GATE_EMOJI.get(v['level'], '')} {v['label'].split('—')[0].strip()}"


def _cell_sentiment(t: str):
    d = research_deep.load_cached(t) or {}
    s = d.get("sentiment")
    return float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None


view["pwpa_cell"] = view["ticker"].map(_cell_pwpa)
view["ai_valuation"] = view["ticker"].map(_cell_valuation)
view["gate_verdict"] = [_cell_gate(t, r) for t, r
                        in zip(view["ticker"], view.to_dict("records"))]
view["market_sentiment"] = view["ticker"].map(_cell_sentiment)
view["signal"] = view["combined"].map(
    lambda s: f"{fisher_score.action_verdict(s)['emoji']} "
              f"{fisher_score.action_verdict(s)['label']}")
view["signal_level"] = view["combined"].map(
    lambda s: fisher_score.action_verdict(s)["level"])

# etykiety filtra sygnalu — wziete z action_verdict (reprezentatywny wynik na
# poziom), zeby nie duplikowac tresci etykiet/emoji na dwa sposoby w kodzie
_SIGNAL_SAMPLE = {"buy": 85, "accumulate": 64, "hold": 50, "sell": 20, "none": None}
SIGNAL_OPTIONS = {lvl: (lambda v: f"{v['emoji']} {v['label']}")(fisher_score.action_verdict(sc))
                  for lvl, sc in _SIGNAL_SAMPLE.items()}

# etykieta kolumny -> kolumna zrodlowa (kanoniczna kolejnosc)
COLS = {
    "Symbol": "ticker", "Spolka": "name", "Segment": "segment", "Cena": "price",
    "Cena docelowa": "target_mean", "Do celu %": "target_upside_pct",
    "Rekom.": "analyst_count", "Ocena analitykow": "rec_label",
    "Wyniki (data)": "next_earnings_date",
    "Przych. r/r (est.)": "rev_growth_pct", "Zysk r/r (est.)": "eps_growth_pct",
    "Ost. kwartal": "last_q_date", "Ost. przychody": "last_q_revenue",
    "Ost. EPS": "last_q_eps", "EPS vs konsensus": "eps_surprise_pct",
    "Dyw. ex-date": "ex_dividend_date", "Dyw. wyplata": "dividend_pay_date",
    "Dyw./akcje": "last_dividend_value",
    "C/Z": "trailing_pe", "Kap. rynk.": "market_cap",
    "Wynik": "combined", "Sygnal": "signal", "Pokrycie %": "coverage",
    "GPW PWPA": "pwpa_cell", "Wycena (AI)": "ai_valuation",
    "WERDYKT BRAMKI": "gate_verdict", "Sentyment rynku": "market_sentiment",
}

# --- ustawienia tabeli: wybor/kolejnosc kolumn (trwale) + grupa dla +/- ---
with st.expander("⚙️ Ustawienia tabeli (kolumny · grupa dla ±)"):
    st.caption("🖱️ **Przeciągaj kafelki myszką**: kolejność w „Widoczne” = "
               "kolejność kolumn w tabeli. Przeciągnij do „Ukryte”, by usunąć "
               "kolumnę z tabeli. Układ jest zapamiętywany.")
    _saved_cols = settings.get("ranking_columns") or list(COLS)
    _visible = [c for c in _saved_cols if c in COLS] or list(COLS)
    _hidden = [c for c in COLS if c not in _visible]
    _arranged = sort_items(
        [{"header": "Widoczne (kolejność = jak w tabeli)", "items": _visible},
         {"header": "Ukryte", "items": _hidden}],
        multi_containers=True, direction="horizontal",
        custom_style=sortable_style(), key="rank_cols_sort")
    sel_cols = list(_arranged[0]["items"])
    if not sel_cols:
        sel_cols = ["Symbol"]
    if "Symbol" not in sel_cols:
        sel_cols = ["Symbol"] + sel_cols
    if sel_cols != settings.get("ranking_columns"):
        settings["ranking_columns"] = sel_cols
        save_wl()
    group = None
    if wl_names:
        group = st.selectbox(
            "Grupa dla kolumny ± (zaznacz pole w tabeli, by dodać/usunąć spółkę)",
            wl_names, key="rank_group")
    else:
        st.caption("Utwórz listę w panelu bocznym, by włączyć kolumnę ± "
                   "(dodawanie/usuwanie spółek z grupy).")

    st.divider()
    _saved_sig = settings.get("signal_filter") or list(SIGNAL_OPTIONS)
    sig_sel = st.multiselect(
        "Sygnał — pokaż tylko", list(SIGNAL_OPTIONS),
        default=[lv for lv in _saved_sig if lv in SIGNAL_OPTIONS],
        format_func=lambda lv: SIGNAL_OPTIONS[lv], key="rank_signal_filter",
        help="Filtruje wiersze po kolumnie Sygnał (decyzja wg wybranej "
             "strategii). Filtr obejmuje też eksport CSV i listę do wyboru "
             "w sekcji Analiza spółki. Pusty wybór = pokaż wszystko. "
             "Wybór jest zapamiętywany.")
    if not sig_sel:
        sig_sel = list(SIGNAL_OPTIONS)
    if sig_sel != settings.get("signal_filter"):
        settings["signal_filter"] = sig_sel
        save_wl()

    st.divider()
    with st.expander("📏 Szerokość kolumn (px; puste = automatycznie)"):
        st.caption("Streamlit nie zgłasza do aplikacji szerokości ustawionej "
                   "przeciąganiem krawędzi nagłówka w samej tabeli (to czysto "
                   "wizualna zmiana we frontendzie) — dlatego szerokość "
                   "ustawiasz tu, liczbowo. W przeciwieństwie do przeciągania "
                   "w tabeli, to się zapamiętuje.")
        _saved_w = settings.get("column_widths") or {}
        new_w = dict(_saved_w)
        _wcols = st.columns(4)
        for _i, _c in enumerate(sel_cols):
            with _wcols[_i % 4]:
                _px = st.number_input(
                    _c, min_value=0, max_value=800,
                    value=int(_saved_w.get(_c, 0)), step=10,
                    key=f"colw_{_c}", help="0 = szerokość automatyczna")
                if _px:
                    new_w[_c] = _px
                else:
                    new_w.pop(_c, None)
        if new_w != _saved_w:
            settings["column_widths"] = new_w
            save_wl()

view = view[view["signal_level"].isin(sig_sel)]

table = view[[COLS[c] for c in sel_cols]].rename(
    columns={src: lbl for lbl, src in COLS.items()})

# kolumna ±: przynaleznosc do wybranej grupy (obok Spolki)
if group is not None:
    _pos = table.columns.get_loc("Spolka") + 1 if "Spolka" in table.columns else 1
    _members = set(wl["lists"].get(group, []))
    table.insert(_pos, "± Grupa", [t in _members for t in view["ticker"]])


def _upside_color(v):
    if pd.isna(v):
        return ""
    return "color: #16a34a; font-weight: 600" if v >= 0 else "color: #dc2626; font-weight: 600"


styled = table.style.map(
    _upside_color, subset=[c for c in ("Do celu %", "Przych. r/r (est.)",
                                       "Zysk r/r (est.)", "EPS vs konsensus",
                                       "Sentyment rynku")
                           if c in table.columns])

# wysokosc = wszystkie wiersze bez wewnetrznego przewijania
_tbl_height = 38 + 35 * len(table)

col_cfg = {
    "± Grupa": st.column_config.CheckboxColumn(
        "± Grupa", help="Zaznacz, by dodać spółkę do wybranej grupy; "
                        "odznacz, by ją usunąć."),
    "Cena": st.column_config.NumberColumn(format="%.2f"),
    "Cena docelowa": st.column_config.NumberColumn(format="%.2f"),
    "Do celu %": st.column_config.NumberColumn(format="%+.1f%%"),
    "Rekom.": st.column_config.NumberColumn(format="%d"),
    "Wyniki (data)": st.column_config.TextColumn(
        help="Data najblizszego sprawozdania kwartalnego (kalendarz Yahoo)"),
    "Przych. r/r (est.)": st.column_config.NumberColumn(
        format="%+.1f%%",
        help="Konsensus analitykow: oczekiwany wzrost przychodow r/r "
             "na najblizszy raportowany kwartal"),
    "Zysk r/r (est.)": st.column_config.NumberColumn(
        format="%+.1f%%",
        help="Konsensus analitykow: oczekiwany wzrost zysku (EPS) r/r "
             "na najblizszy raportowany kwartal"),
    "Ost. kwartal": st.column_config.TextColumn(
        help="Koniec ostatniego OPUBLIKOWANEGO kwartalu"),
    "Ost. przychody": st.column_config.NumberColumn(
        format="compact",
        help="Przychody z ostatnio opublikowanych wynikow kwartalnych"),
    "Ost. EPS": st.column_config.NumberColumn(
        format="%.2f",
        help="Zysk na akcje (EPS) z ostatnio opublikowanych wynikow "
             "kwartalnych"),
    "EPS vs konsensus": st.column_config.NumberColumn(
        format="%+.1f%%",
        help="O ile opublikowany EPS pobil (+) lub zawiodl (-) konsensus "
             "analitykow. Wstecznego konsensusu PRZYCHODOW Yahoo nie "
             "udostepnia, wiec pokazujemy tylko EPS."),
    "Dyw. ex-date": st.column_config.TextColumn(
        help="Dzien odciecia prawa do dywidendy (ex-dividend) z biezacego "
             "roku - najblizszy zadeklarowany albo juz miniony; gdy w tym "
             "roku brak, ostatni z ubieglego roku"),
    "Dyw. wyplata": st.column_config.TextColumn(
        help="Dzien wyplaty dywidendy. Zna go tylko kalendarz Yahoo - "
             "dla wiekszosci spolek GPW nie jest publikowany (puste pole)"),
    "Dyw./akcje": st.column_config.NumberColumn(
        format="%.2f",
        help="Kwota dywidendy na akcje (w walucie notowan) - z biezacego "
             "roku, a gdy brak, z ubieglego"),
    "GPW PWPA": st.column_config.TextColumn(
        help="Raporty analityczne z programu GPW PWPA: liczba raportow "
             "i data najnowszego. Pelna lista z linkami do PDF oraz "
             "wyciaganie ceny docelowej — w analizie spolki. "
             "Puste = spolka spoza programu (m.in. cala Nasdaq)."),
    "Wycena (AI)": st.column_config.TextColumn(
        help="Ocena wyceny z sekcji Financial Charts. Puste = nie "
             "wygenerowano jeszcze podsumowania AI dla tej spolki."),
    "WERDYKT BRAMKI": st.column_config.TextColumn(
        help="Werdykt bramki z Panelu decyzyjnego (ta sama logika, wiec "
             "kolumna i panel nie moga sie rozjechac). Puste = brak bazy "
             "scenariuszy: wygeneruj ja AI albo wpisz recznie w panelu. "
             "Sama baza mechaniczna nie jest pokazywana, bo wyprowadza "
             "3-letni scenariusz z 12-miesiecznej ceny docelowej i dawalaby "
             "'NIE KUPUJ' w kazdym wierszu."),
    "Sentyment rynku": st.column_config.NumberColumn(
        format="%+d",
        help="Sentyment z Deep research (-100 skrajnie negatywny ... "
             "+100 skrajnie pozytywny). NIE wplywa na Wynik strategii. "
             "Puste = nie uruchomiono deep researchu dla tej spolki."),
    "C/Z": st.column_config.NumberColumn(format="%.1f"),
    "Kap. rynk.": st.column_config.NumberColumn(format="compact"),
    "Wynik": st.column_config.ProgressColumn("Wynik", min_value=0, max_value=100, format="%.1f"),
    "Pokrycie %": st.column_config.NumberColumn(format="%d%%"),
}

# szerokosci ustawione recznie (patrz "📏 Szerokosc kolumn") — obiekty
# column_config.* sa zwyklymi dict-ami, wiec mozna dopisac "width" po fakcie
for _c, _px in (settings.get("column_widths") or {}).items():
    col_cfg.setdefault(_c, {})["width"] = _px

edited = st.data_editor(
    styled,
    width="stretch", hide_index=True, height=_tbl_height,
    disabled=[c for c in table.columns if c != "± Grupa"],
    key=f"rankedit_{group}_{len(wl['lists'].get(group, [])) if group else 0}",
    column_config=col_cfg,
)

# zastosuj zmiany z kolumny ±: roznica zaznaczen -> dodaj/usun w grupie
if group is not None and edited is not None and "± Grupa" in edited.columns:
    _new = set(edited.loc[edited["± Grupa"] == True, "Symbol"])  # noqa: E712
    _old = {t for t in table["Symbol"] if t in _members}
    if _new != _old:
        lst = wl["lists"].setdefault(group, [])
        for t in table["Symbol"]:
            if t in _new and t not in lst:
                lst.append(t)
            elif t not in _new and t in lst:
                lst.remove(t)
        save_wl()
        st.rerun()

st.caption("Cena, cena docelowa, przychody i dywidenda w walucie notowan "
           "(Nasdaq: USD, GPW: PLN). "
           "Rekom. = liczba analitykow; ocena 1=Strong Buy ... 5=Sell. "
           "Wyniki (data) = najblizsza PRZYSZLA planowana publikacja wynikow "
           "kwartalnych (puste = spolka nie ogosila terminu). "
           "Przych./Zysk r/r (est.) = konsensus analitykow na najblizszy kwartal "
           "wzgledem tego samego kwartalu rok wczesniej (zielone = wzrost, "
           "czerwone = spadek). "
           "Ost. kwartal/przychody/EPS = ostatnio OPUBLIKOWANE wyniki; "
           "EPS vs konsensus = o ile pobito oczekiwania analitykow. "
           "Dywidenda: dane z biezacego roku, a gdy brak - z ubieglego; "
           "dnia wyplaty dla wiekszosci spolek GPW Yahoo nie publikuje. "
           "Sygnal = decyzja wg wybranej strategii (Kupuj/Akumuluj/Trzymaj/Sprzedaj) "
           "na podstawie Wyniku. Dla czesci spolek GPW konsensus analitykow niedostepny. "
           "GPW PWPA = liczba raportow maklerskich i data najnowszego (tylko spolki "
           "objete programem). Wycena (AI), WERDYKT BRAMKI i Sentyment rynku "
           "pokazuja wyniki analiz uruchamianych per spolka (Financial Charts, "
           "Panel decyzyjny, Deep research) — puste pole znaczy, ze dla tej spolki "
           "jeszcze ich nie uruchomiles.")

# swiezosc danych rankingu: zakres czasow pobrania widocznych spolek
if "fetched_at" in view.columns:
    _fts = sorted(t for t in view["fetched_at"].dropna().tolist() if t)
    if _fts:
        _fresh = (f"zaktualizowano {fmt_dt(_fts[0])}" if _fts[0] == _fts[-1] else
                  f"zaktualizowano między {fmt_dt(_fts[0])} a {fmt_dt(_fts[-1])}")
        st.caption(f"🗓 Źródło danych: **Yahoo Finance** · {_fresh} "
                   f"(cache 24h — wymuś pobranie przyciskiem 🔄 w panelu bocznym).")

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
    st.info(f"📌 Analizowana spółka: **{co_label(pick, row)}**")

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
    st.caption(f"🗓 Dane fundamentalne: **Yahoo Finance** · zaktualizowano "
               f"{fmt_dt(row.get('fetched_at'))}")

    # Sygnal inwestycyjny wg wybranej strategii (czy by kupil / sprzedal)
    av = fisher_score.action_verdict(row.get("combined"))
    guru_name = gurus.get(guru_key)["name"]
    _msg = f"{av['emoji']} Wg strategii **{guru_name}**: **{av['label']}** — {av['desc']}."
    if av["level"] in ("buy", "accumulate"):
        st.success(_msg)
    elif av["level"] == "hold":
        st.warning(_msg)
    elif av["level"] == "sell":
        st.error(_msg)
    else:
        st.caption(_msg)

    # --- Moje notatki per spolka (prywatne, zapis w Gist) ---
    notes = wl.setdefault("notes", {})
    _has_note = bool(notes.get(pick, "").strip())
    with st.expander("📝 Moje notatki / wnioski z analiz" + (" ✓" if _has_note else ""),
                     expanded=_has_note):
        txt = st.text_area(
            "Notatki", value=notes.get(pick, ""), height=160,
            key=f"note_{pick}", label_visibility="collapsed",
            placeholder="Twoje wlasne wnioski, tezy, wyceny, cytaty z analiz, "
                        "ktore czytasz gdzie indziej. Uzytek osobisty.")
        nc1, nc2 = st.columns([1, 4])
        with nc1:
            if st.button("💾 Zapisz notatke", key=f"savenote_{pick}"):
                if txt.strip():
                    notes[pick] = txt.strip()
                else:
                    notes.pop(pick, None)
                save_wl()
                st.success("Zapisano.")
                st.rerun()
        with nc2:
            if watchlists.backend() == "gist":
                st.caption("Zapis: GitHub Gist ✅ (trwaly, prywatny).")
            else:
                st.caption("Bez GITHUB_TOKEN+GIST_ID notatki sa lokalne i znikna "
                           "przy restarcie aplikacji.")

    # --- Rekomendacje analitykow z raportow GPW PWPA (tylko GPW) ---
    if pick.endswith(".WA"):
        render_pwpa(pick, co_label(pick, row))

    left, right = st.columns(2)

    with left:
        st.subheader(f"Rozbicie ilosciowe — {co_label(pick, row)}")
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
        st.subheader(f"Ocena jakosciowa ({gurus.get(guru_key)['name']}) — {co_label(pick, row)}")
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
            st.caption(f"Model: {ai.get('model')} · pewnosc: {ai.get('confidence')}% "
                       f"· wygenerowano {fmt_dt(ai.get('researched_at'))} "
                       "(wiedza modelu, bez wyszukiwarki)")
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
    financial_charts.render(pick, row, notes=wl.get("notes", {}).get(pick))

    # ---------------- Panel decyzyjny ----------------
    st.divider()
    decision_panel.render(pick, row, wl, save_wl)

    # ---------------- Deep research ----------------
    st.divider()
    st.subheader(f"🔎 Deep research: sentyment rynku + YouTube + relacje inwestorskie — {co_label(pick, row)}")
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
        st.caption(f"🗓 Źródła: Google Search (grounding) + YouTube + strona IR · "
                   f"model: {deep.get('model')} · wygenerowano "
                   f"{fmt_dt(deep.get('researched_at'))}")
    else:
        st.caption("Brak deep researchu dla tej spolki. Uruchom przyciskiem powyzej.")

    # ---------------- Analiza wideo (AI agent oglada film) ----------------
    st.divider()
    st.subheader(f"🎧 Analiza wideo (AI) — {co_label(pick, row)}")
    st.caption("Agent najpierw próbuje napisów; gdy ich brak, wysyła film do "
               "Gemini, który **ogląda/odsłuchuje go po stronie Google** "
               "(działa też z chmury — nasz serwer nie pobiera nic z YouTube).")
    _vn = yt_transcribe.videos_note()
    if _vn:
        st.caption(f"ℹ️ {_vn}")
    if not yt_transcribe.available():
        st.caption("Wymaga GEMINI_API_KEY.")
    else:
        vids = yt_videos(pick, row.get("name", pick), row.get("market", ""))
        if not vids:
            st.caption("Nie znaleziono filmów o spółce z ostatnich 12 miesięcy"
                       + ("" if not _vn else
                          " — bez YOUTUBE_API_KEY wyszukiwanie z serwera "
                          "zwykle nie działa."))
        else:
            def _vid_label(v):
                mins = f" · {v['minutes']:.0f} min" if v.get("minutes") else ""
                views = (f" · {v['views']:,} wyśw.".replace(",", " ")
                         if v.get("views") else "")
                return (f"{v.get('date', '')} · {str(v.get('title', ''))[:60]} "
                        f"— {v.get('channel', '')}{mins}{views}")
            labels = {v["id"]: _vid_label(v) for v in vids}
            vid = st.selectbox(f"Film ({len(vids)} znalezionych, 12 mies.)",
                               [v["id"] for v in vids],
                               format_func=lambda i: labels.get(i, i),
                               key=f"ytt_sel_{pick}")
            video = next(v for v in vids if v["id"] == vid)
            res = yt_transcribe.load_cached(vid)
            if st.button("🎧 Przeanalizuj film", key=f"ytt_btn_{pick}"):
                with st.spinner("Analizuję film (napisy albo odsłuch przez "
                                "Gemini — do ~2 min)..."):
                    try:
                        res = yt_transcribe.run(video, row.get("name", pick),
                                                pick, force=True)
                    except Exception as e:
                        st.error(f"Nie udalo sie: {e}")
            if res:
                st.markdown(f"**[{res.get('title', 'film')}]({res.get('url')})** — "
                            f"źródło transkryptu: *{res.get('transcript_source')}*")
                sc = res.get("sentiment")
                if sc is not None:
                    st.metric("Sentyment autora wobec spółki", f"{sc:+d}")
                if res.get("thesis") and res["thesis"].lower() != "brak":
                    st.info(res["thesis"])
                if res.get("key_points"):
                    st.markdown("**Kluczowe tezy:**")
                    for p in res["key_points"]:
                        st.markdown(f"- {p}")
                if res.get("risks"):
                    st.markdown("**Ryzyka wg autora:**")
                    for p in res["risks"]:
                        st.markdown(f"- {p}")
                with st.expander("Fragment transkryptu"):
                    st.write(res.get("transcript_excerpt", ""))
                st.caption(f"🗓 Źródło: YouTube (transkrypt: "
                           f"{res.get('transcript_source', '—')}) · "
                           f"postawa: {res.get('speaker_stance', '—')} · "
                           f"przeanalizowano {fmt_dt(res.get('analyzed_at'))}")
else:
    st.info("Brak spolek spelniajacych filtry. Zluzuj min. pokrycie lub odswiez dane.")

st.divider()
st.caption("⚠️ Narzedzie edukacyjne — nie stanowi porady inwestycyjnej. "
           "Dane: Yahoo Finance (yfinance). Strategie inwestorow sa edukacyjnymi "
           "przyblizeniami ich filozofii, nie prawdziwymi algorytmami.")

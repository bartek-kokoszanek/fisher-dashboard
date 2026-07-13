"""ALPHA ENGINE — AKTYWNA INTELIGENCJA (ciemny terminal, 3 kolumny).

Nowy frontend do analizy spolek: watchlist -> cyfrowy blizniak spolki ->
wywiad strategiczny. Dziala na tych samych danych co glowny dashboard
(cache data/raw_* i data/hist_*; scoring fisher_score + gurus; research AI
z cache), a elementy bez backendu (DCF, obietnice zarzadu, dziennik) maja
CZYTELNIE OZNACZONE dane przykladowe — do walidacji UI.

Mobile (<768 px): kolumny skladaja sie w pionie w kolejnosci
hero -> watchlist (zwijana) -> panel prawy, wykresy jeden pod drugim.
"""
from __future__ import annotations

import json
import os

import plotly.graph_objects as go
import streamlit as st

import ai_research
import config
import data_fetch
import fisher_score
import gpw_indices
import gurus
import watchlists
from charts import data as chdata
from charts import helpers as chh

st.set_page_config(page_title="ALPHA ENGINE", page_icon="🔺", layout="wide")

# ---------------------------------------------------------------- style ---
GREEN, RED, CYAN = "#10b981", "#ef4444", "#0ea5e9"
BG, CARD, BORDER, TXT, MUT = "#0f172a", "#16223b", "#2c3e5d", "#e2e8f0", "#94a3b8"

st.markdown(f"""<style>
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background: {BG}; color: {TXT};
    font-family: Inter, Roboto, system-ui, -apple-system, sans-serif;
}}
[data-testid="stSidebar"] {{ background: #0b1222; }}
h1,h2,h3,h4,h5, p, li, label, span, div {{ color: {TXT}; }}
small, .stCaption, [data-testid="stCaptionContainer"] {{ color: {MUT} !important; }}
.ae-card {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 0.9rem 1rem; margin-bottom: 0.8rem;
}}
.ae-title {{ font-size: 0.8rem; letter-spacing: .08em; color: {MUT};
             text-transform: uppercase; margin-bottom: .45rem; }}
.ae-hero-score {{ font-size: 2.1rem; font-weight: 800; line-height: 1.1; }}
.ae-pill {{ display:inline-block; padding: .12rem .55rem; border-radius: 999px;
            border:1px solid {BORDER}; font-size:.78rem; margin: 0 .25rem .25rem 0; }}
.ae-green {{ color: {GREEN}; }} .ae-red {{ color: {RED}; }} .ae-cyan {{ color: {CYAN}; }}
.ae-b-green {{ border-color:{GREEN}; }} .ae-b-red {{ border-color:{RED}; }}
div[data-testid="stButton"] > button {{
    background: {CARD}; color: {TXT}; border: 1px solid {BORDER};
    border-radius: 8px; width: 100%; text-align: left; padding: .3rem .6rem;
}}
div[data-testid="stButton"] > button:hover {{ border-color: {CYAN}; color: {CYAN}; }}
/* --- mobile: kolumny w pion; w bloku glownym hero przed watchlista
       (blok glowny rozpoznajemy po expanderze watchlisty w 1. kolumnie) --- */
@media (max-width: 768px) {{
    div[data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important;
    }}
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stExpander"])
        > div[data-testid="stColumn"]:nth-child(1) {{ order: 2; }}
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stExpander"])
        > div[data-testid="stColumn"]:nth-child(2) {{ order: 1; }}
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stExpander"])
        > div[data-testid="stColumn"]:nth-child(3) {{ order: 3; }}
    .ae-hero-score {{ font-size: 1.6rem; }}
}}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- dane ---

def _cached_raw(ticker: str) -> dict | None:
    """Surowe dane WYLACZNIE z cache plikowego (bez pobierania — szybki start)."""
    path = os.path.join(config.CACHE_DIR, f"raw_{ticker.replace('.', '_')}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False, ttl=3600)
def load_universe() -> list[dict]:
    """Spolki z cache (WIG20/mWIG40/sWIG80 + Nasdaq) — bez odpytywania API."""
    out = []
    for t in config.all_tickers() + sorted(gpw_indices.NASDAQ_AI):
        raw = _cached_raw(t)
        if raw and "error" not in raw:
            out.append(raw)
    # deduplikacja po tickerze
    seen, uniq = set(), []
    for r in out:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            uniq.append(r)
    return uniq


def score_of(raw: dict, guru_key: str) -> tuple[float | None, dict]:
    res = fisher_score.compute_score(raw, gurus.get(guru_key)["weights"])
    ai = ai_research.load_cached(raw["ticker"], guru_key)
    q = ai.get("quality_score") if ai else None
    s = res["score"]
    combined = round(0.7 * s + 0.3 * q, 1) if (s is not None and q is not None) else s
    return combined, res["subscores"]


def _score_color(s) -> str:
    if s is None:
        return MUT
    return GREEN if s >= 70 else (CYAN if s >= 55 else RED)


def _fair_value(price, score):
    """Placeholder wyceny DCF (do czasu prawdziwego modelu): cena godziwa
    zalezna od wyniku strategii. Deterministyczny, oznaczony w UI."""
    if not price or score is None:
        return None, None
    fair = round(price * (0.82 + score / 100 * 0.42), 2)
    disc = round((fair / price - 1) * 100, 0)
    return fair, disc


# etykiety kryteriow guru (metryka -> nazwa PL)
CRIT_PL = {
    "revenue_cagr": "Trwaly wzrost sprzedazy", "revenue_growth_yoy": "Dynamika r/r",
    "gross_margin": "Wysoka marza brutto", "operating_margin": "Wysokie marze operacyjne",
    "margin_trend": "Poprawa marz", "rnd_intensity": "Silne R&D",
    "roe": "Wysokie ROE", "fcf_margin": "Silny FCF",
    "low_dilution": "Brak rozwadniania", "low_leverage": "Niski dlug",
    "value_pe": "Atrakcyjna wycena (C/Z)", "momentum": "Momentum 6M",
}

# przykladowe obietnice zarzadu (placeholder do czasu backendu ESPI/IR)
_PROMISES = [
    ("2025-03", "Podwojenie przychodow zagranicznych w 2 lata", True),
    ("2025-08", "Utrzymanie marzy operacyjnej powyzej 30%", True),
    ("2025-11", "Premiera nowego produktu w I polowie roku", False),
    ("2026-03", "Wyplata dywidendy min. 50% zysku", True),
]


# ---------------------------------------------------------------- header ---
hl, hm, hr = st.columns([3, 4, 2], vertical_alignment="center")
with hl:
    st.markdown(f"### 🔺 <span class='ae-cyan'>ALPHA ENGINE</span> — AKTYWNA "
                f"INTELIGENCJA", unsafe_allow_html=True)
with hm:
    seg = st.pills("Rynek", ["Wszystkie", "🇵🇱 GPW", "NASDAQ-AI", "WIG20"],
                   default="Wszystkie", label_visibility="collapsed")
with hr:
    guru_key = st.selectbox("Globalna Strategia:", gurus.options(),
                            format_func=lambda k: gurus.get(k)["name"])

universe = load_universe()
if not universe:
    st.info("Brak danych w cache — otwórz najpierw stronę główną (ranking), "
            "aby pobrać fundamenty spółek.")
    st.stop()

# filtr rynku
def _in_seg(r) -> bool:
    t = r["ticker"]
    if seg == "🇵🇱 GPW":
        return t.endswith(".WA")
    if seg == "NASDAQ-AI":
        return t in gpw_indices.NASDAQ_AI
    if seg == "WIG20":
        return t in gpw_indices.WIG20
    return True

rows = []
for r in universe:
    if not _in_seg(r):
        continue
    s, subs = score_of(r, guru_key)
    rows.append({**r, "score": s, "subscores": subs})
rows.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0)))

if "ae_pick" not in st.session_state or \
        st.session_state["ae_pick"] not in {r["ticker"] for r in rows}:
    st.session_state["ae_pick"] = rows[0]["ticker"] if rows else None

# ------------------------------------------------------------- 3 kolumny ---
c1, c2, c3 = st.columns([20, 55, 25], gap="medium")

# =========================== KOLUMNA 1: WATCHLIST ===========================
with c1:
    with st.expander("📋 Pokaż listę spółek (Watchlist)", expanded=True):
        wl_seg = st.segmented_control("Filtr", ["GPW", "NASDAQ-AI"],
                                      default="GPW", key="ae_wl_seg",
                                      label_visibility="collapsed")
        wl_rows = [r for r in rows
                   if (r["ticker"].endswith(".WA")) == (wl_seg == "GPW")]
        for r in wl_rows[:40]:
            s = r["score"]
            arrow = "▲" if (r.get("return_6m") or 0) >= 0 else "▼"
            acls = "ae-green" if (r.get("return_6m") or 0) >= 0 else "ae-red"
            bc, sc_ = st.columns([3, 2], vertical_alignment="center")
            with bc:
                if st.button(f"{r['ticker']}\n{str(r.get('name', ''))[:20]}",
                             key=f"ae_row_{r['ticker']}"):
                    st.session_state["ae_pick"] = r["ticker"]
                    st.rerun()
            with sc_:
                st.markdown(
                    f"<span style='color:{_score_color(s)};font-weight:700'>"
                    f"{'—' if s is None else f'{s:.0f}/100'}</span> "
                    f"<span class='{acls}'>{arrow}</span>",
                    unsafe_allow_html=True)

pick = st.session_state["ae_pick"]
cur = next((r for r in rows if r["ticker"] == pick), rows[0] if rows else None)

# ====================== KOLUMNA 2: CYFROWY BLIZNIAK ========================
with c2:
    if cur is None:
        st.info("Wybierz spółkę z watchlisty.")
        st.stop()
    s = cur["score"]
    av = fisher_score.action_verdict(s)
    fair, disc = _fair_value(cur.get("price"), s)
    curr = cur.get("currency") or ""
    sig_cls = {"buy": "ae-green", "accumulate": "ae-green",
               "hold": "ae-cyan", "sell": "ae-red"}.get(av["level"], "ae-cyan")

    st.markdown(f"""<div class="ae-card">
      <div class="ae-title">{cur.get('name', pick)} · CYFROWY BLIŹNIAK</div>
      <div class="ae-hero-score" style="color:{_score_color(s)}">
        OGÓLNY WYNIK ZAUFANIA: {'—' if s is None else f'{s:.0f}'}/100</div>
      <div style="margin-top:.4rem">
        Sygnał: <b class="{sig_cls}">{av['label']}</b>
        &nbsp;|&nbsp; Cena Godziwa (DCF*): <b>{fair if fair else '—'} {curr}</b>
        &nbsp;|&nbsp; {'Dyskonto' if (disc or 0) >= 0 else 'Premia'}:
        <b class="{'ae-green' if (disc or 0) >= 0 else 'ae-red'}">{'' if disc is None else f'{abs(disc):.0f}%'}</b>
      </div>
      <div style="color:{MUT};font-size:.75rem;margin-top:.3rem">
        * DCF: model uproszczony (placeholder) — pelna wycena w przygotowaniu.
      </div>
    </div>""", unsafe_allow_html=True)

    # Teza inwestycyjna (z researchu AI, gdy jest; inaczej z metryk)
    ai = ai_research.load_cached(pick, guru_key)
    theses = (ai.get("strengths") or [])[:3] if ai else []
    if not theses:
        subs = cur.get("subscores") or {}
        best = sorted(((v, k) for k, v in subs.items() if v is not None),
                      reverse=True)[:3]
        theses = [f"{CRIT_PL.get(k, k)}: {v:.0f}/100 pkt" for v, k in best] or \
                 ["Uruchom research AI na stronie głównej, by zobaczyć tezy."]
    st.markdown('<div class="ae-card"><div class="ae-title">Teza inwestycyjna'
                '</div>' + "".join(f"<li>{t}</li>" for t in theses)
                + "</div>", unsafe_allow_html=True)

    # Modul B: Wieloguru Ocena Jakosciowa
    g = gurus.get(guru_key)
    subs = cur.get("subscores") or {}
    crits = []
    for m, w in sorted(g["weights"].items(), key=lambda x: -x[1])[:6]:
        v = subs.get(m)
        ok = v is not None and v >= 60
        badge = ("<span class='ae-pill ae-b-green ae-green'>Spełnione</span>"
                 if ok else
                 "<span class='ae-pill ae-b-red ae-red'>Niespełnione</span>"
                 if v is not None else
                 f"<span class='ae-pill'>brak danych</span>")
        crits.append(f"<div style='display:flex;justify-content:space-between;"
                     f"margin:.2rem 0'><span>{CRIT_PL.get(m, m)} "
                     f"<span style='color:{MUT}'>(waga {w})</span></span>{badge}</div>")
    st.markdown(f'<div class="ae-card"><div class="ae-title">Wieloguru — ocena '
                f'jakościowa · <b class="ae-cyan">{g["name"]}</b></div>'
                + "".join(crits) + "</div>", unsafe_allow_html=True)

    # Modul C: wykresy (3 w rzedzie; na mobile jeden pod drugim)
    hist = None
    hpath = os.path.join(config.CACHE_DIR, f"hist_{pick.replace('.', '_')}.json")
    if os.path.exists(hpath):
        try:
            hist = chdata.get_history(pick)
        except Exception:
            hist = None

    def _dark(fig, title):
        fig.update_layout(
            title=dict(text=title, font=dict(size=13, color=TXT)),
            height=240, margin=dict(l=6, r=6, t=34, b=6),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUT, size=10), showlegend=True,
            legend=dict(orientation="h", y=-0.25, font=dict(size=9)),
            hovermode="x unified")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="rgba(148,163,184,.15)")
        return fig

    ch1, ch2, ch3 = st.columns(3)
    if hist:
        srs = hist.get("series", {})
        ry, rv = chh.sorted_items(srs.get("revenue"))
        ny, nv = chh.sorted_items(srs.get("net_income"))
        with ch1:
            f = go.Figure()
            f.add_bar(x=ry, y=rv, name="Przychody", marker_color=CYAN)
            f.add_bar(x=ny, y=nv, name="Zysk netto", marker_color=GREEN)
            st.plotly_chart(_dark(f, "Przychody i Zysk Netto R/R"),
                            width="stretch", config=chh.PLOTLY_CONFIG)
        fy, fv = chh.sorted_items(srs.get("fcf"))
        oy, ov = chh.sorted_items(srs.get("roe"))
        with ch2:
            f = go.Figure()
            f.add_bar(x=fy, y=fv, name="FCF", marker_color=GREEN)
            f.add_scatter(x=oy, y=[v * 100 for v in ov], name="ROE %",
                          mode="lines+markers", yaxis="y2",
                          line=dict(color=CYAN, width=2))
            f.update_layout(yaxis2=dict(overlaying="y", side="right",
                                        showgrid=False, ticksuffix="%"))
            st.plotly_chart(_dark(f, "FCF i ROE"),
                            width="stretch", config=chh.PLOTLY_CONFIG)
    else:
        with ch1:
            st.info("Historia finansowa niedostępna w cache — otwórz spółkę "
                    "na stronie głównej.")
    with ch3:
        price = cur.get("price")
        if price and fair:
            yrs = list(range(2024, 2030))
            path = [round(fair * (0.82 + 0.06 * i), 2) for i in range(len(yrs))]
            f = go.Figure()
            f.add_scatter(x=yrs, y=path, name="Cena godziwa (DCF*)",
                          line=dict(color=GREEN, width=2))
            f.add_scatter(x=yrs, y=[price] * len(yrs), name="Cena obecna",
                          line=dict(color=RED, dash="dash"))
            st.plotly_chart(_dark(f, "Wycena (DCF* i Mnożniki)"),
                            width="stretch", config=chh.PLOTLY_CONFIG)
        else:
            st.info("Brak ceny — wykres wyceny niedostępny.")

# ================= KOLUMNA 3: WYWIAD STRATEGICZNY / PORTFEL =================
with c3:
    risks = (ai.get("weaknesses") or [])[:3] if ai else []
    impact = ["Wysoki Wpływ, Średnie Prawdopodobieństwo",
              "Średni Wpływ, Wysokie Prawdopodobieństwo",
              "Średni Wpływ, Niskie Prawdopodobieństwo"]
    risk_html = "".join(
        f"<li>{r} <br><span style='color:{MUT};font-size:.75rem'>{impact[i % 3]}"
        f"</span></li>" for i, r in enumerate(risks)) or \
        f"<span style='color:{MUT}'>Uruchom research AI, by zobaczyć zagrożenia.</span>"
    sector = cur.get("sector") or "sektor"
    st.markdown(f"""<div class="ae-card">
      <div class="ae-title">Wywiad Strategiczny</div>
      <b class="ae-red">Zagrożenia</b><ul>{risk_html}</ul>
      <b class="ae-cyan">Gabinet Wojenny Konkurencji</b>
      <p style="font-size:.85rem">{cur.get('name', pick)} na tle konkurencji
      ({sector}): pozycja wg wyniku strategii
      {'' if s is None else f'{s:.0f}/100'} — porównanie szczegółowe
      w przygotowaniu (placeholder).</p>
    </div>""", unsafe_allow_html=True)

    prom_html = "".join(
        f"<div style='margin:.3rem 0;font-size:.85rem'>[{d}] {txt}<br>"
        f"<b class='{'ae-green' if ok else 'ae-red'}'>Status: "
        f"{'SPEŁNIONE' if ok else 'NIESPEŁNIONE'}</b></div>"
        for d, txt, ok in _PROMISES)
    st.markdown(f"""<div class="ae-card">
      <div class="ae-title">Obietnice Zarządu (przykładowe*)</div>{prom_html}
      <div style="color:{MUT};font-size:.72rem">* dane poglądowe — moduł
      śledzenia deklaracji (ESPI/IR) w przygotowaniu.</div>
    </div>""", unsafe_allow_html=True)

    wl = watchlists.load()
    positions = sorted(watchlists.all_listed_tickers(wl))[:8]
    pos_html = "".join(f"<span class='ae-pill'>{t}</span>" for t in positions) or \
               f"<span style='color:{MUT}'>Brak pozycji — dodaj spółki do list " \
               f"na stronie głównej.</span>"
    st.markdown(f"""<div class="ae-card">
      <div class="ae-title">Portfel</div>
      <b class="ae-cyan">Dziennik (przykładowy*)</b>
      <div style="font-size:.85rem;margin:.3rem 0">
        Kupiono XTB @ 84 PLN ze względu na wysokie FCF<br>
        Obserwacja: {pick} — sygnał {av['label']}</div>
      <b class="ae-cyan">Aktualne Pozycje</b><br>{pos_html}
      <div style="color:{MUT};font-size:.72rem;margin-top:.3rem">* dziennik
      transakcji w przygotowaniu; pozycje = Twoje listy obserwacyjne.</div>
    </div>""", unsafe_allow_html=True)

st.caption("⚠️ Narzędzie edukacyjne — nie stanowi porady inwestycyjnej. "
           "Elementy oznaczone * to dane przykładowe do walidacji interfejsu.")

"""Wspolne narzedzia wykresow: kolory, layout, formatowanie, CAGR, tooltipy.

Zasady (wg specyfikacji):
- Plotly, minimalistycznie, bez 3D.
- Os Y skaluje sie automatycznie (domyslne zachowanie Plotly).
- Wykresy responsywne (renderowane z use_container_width=True + responsive config).
- Brak danych => zwracamy None, a karta pokazuje komunikat zamiast bledu.
"""
from __future__ import annotations

import math

# --- Kolory (paleta ze specyfikacji) ---
COLORS = {
    "revenue": "#2563eb",     # niebieski
    "net_income": "#16a34a",  # zielony
    "margin": "#7c3aed",      # fioletowy
    "pe": "#ea580c",          # pomaranczowy
    "roe": "#dc2626",         # czerwony
    "fcf": "#0d9488",         # turkusowy
    "debt": "#6b7280",        # szary
    "eps": "#0891b2",
    "book": "#4f46e5",
    "dividend": "#0ea5e9",
    "shares": "#64748b",
    "roic": "#be123c",
    "pos": "#16a34a",         # dodatnie
    "neg": "#dc2626",         # ujemne
    "band_ok": "rgba(22,163,74,0.10)",
    "band_mid": "rgba(234,179,8,0.10)",
    "band_hi": "rgba(220,38,38,0.10)",
}

# Konfiguracja Plotly: responsywnosc + czyste UI + eksport PNG
PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def base_layout(fig, height: int = 260, legend: bool = False, time_axis: bool = False):
    """Minimalistyczny, responsywny layout. Kolory tekstu zostawiamy motywowi
    Streamlita (st.plotly_chart theme='streamlit'). time_axis=True -> os dat
    (dla wykresu ceny); domyslnie os X to kategorie lat (bez etykiet 2021.5)."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        bargap=0.25,
    )
    if time_axis:
        fig.update_xaxes(showgrid=False, zeroline=False)
    else:
        # lata jako kategorie: bez ulamkowych etykiet (2021.5) na osi X
        fig.update_xaxes(showgrid=False, zeroline=False, type="category")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)",
                     zeroline=True, zerolinecolor="rgba(128,128,128,0.35)")
    return fig


# --- Formatowanie ---

def fmt_dt(iso: str | None) -> str:
    """ISO-timestamp (UTC) -> 'YYYY-MM-DD HH:MM' czasu polskiego.

    Do podpisow 'zaktualizowano: ...' przy danych. Fallback: czas lokalny
    systemu, a przy nieparsowalnym wejsciu — surowy tekst.
    """
    if not iso:
        return "—"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(iso))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo("Europe/Warsaw"))
        except Exception:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso)


def human(x) -> str:
    """Duze liczby w skrocie: 4.5T / 23.2B / 512M / 8.1K."""
    if not is_num(x):
        return "—"
    a = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{x / div:.1f}{suf}"
    return f"{x:.0f}"


def pct(x, digits: int = 1) -> str:
    return "—" if not is_num(x) else f"{x * 100:.{digits}f}%"


def num(x, digits: int = 1) -> str:
    return "—" if not is_num(x) else f"{x:.{digits}f}"


# --- Statystyki ---

def cagr(values: list) -> float | None:
    """CAGR miedzy pierwsza a ostatnia dodatnia wartoscia serii (rosnaco po latach)."""
    vals = [v for v in values if is_num(v)]
    if len(vals) < 2:
        return None
    first, last = vals[0], vals[-1]
    years = len(vals) - 1
    if first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def mean(values: list) -> float | None:
    vals = [v for v in values if is_num(v)]
    return sum(vals) / len(vals) if vals else None


def yoy(values: list) -> list:
    """Dynamika rok do roku (lista o tej samej dlugosci; pierwszy = None)."""
    out = [None]
    for prev, cur in zip(values, values[1:]):
        if is_num(prev) and is_num(cur) and prev != 0:
            out.append(cur / abs(prev) - 1)
        else:
            out.append(None)
    return out


def has_data(series: dict | None) -> bool:
    """Czy seria {rok: wartosc} ma co najmniej 2 liczbowe punkty."""
    if not series:
        return False
    return sum(1 for v in series.values() if is_num(v)) >= 2


def sorted_items(series: dict):
    """(lata, wartosci) posortowane rosnaco po roku; tylko liczbowe wartosci."""
    if not series:
        return [], []
    items = sorted(((int(k), v) for k, v in series.items() if is_num(v)))
    years = [k for k, _ in items]
    vals = [v for _, v in items]
    return years, vals

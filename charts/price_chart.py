"""Wykres kursu akcji: okresy 1M...Max + nakladki metryk (styl Qualtrim).

fig_price()    — prosty wykres ceny (uzywany historycznie; zostawiony).
fig_advanced() — wykres wielopanelowy: cena + cena docelowa, wskazniki
                 (P/E, P/S, EV/EBITDA z medianami 3L), potencjal do celu %,
                 marza operacyjna, przychody/zysk/FCF i EPS z prognozami.
                 Panele grupuja serie o tej samej jednostce (PLN/USD, %, x).

Wskazniki tygodniowe licza sie z ceny tygodniowej i ROCZNYCH sprawozdan
(wartosc z ostatniego dostepnego roku <= dana data) — to przyblizenie,
zaznaczone w podpisie wykresu w UI.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import helpers as h

# Prosty wykres (kompatybilnosc wstecz)
PERIODS = {"1 rok": 1, "2 lata": 2, "3 lata": 3, "5 lat": 5}

# Zakresy czasu wykresu zaawansowanego (dni; None = specjalne)
RANGES = {
    "1M": 31, "3M": 92, "6M": 183, "YTD": None, "1R": 366,
    "3L": 3 * 366, "5L": 5 * 366, "10L": 10 * 366, "20L": 20 * 366,
    "Max": 10 ** 6,
}

# Nakladki: etykieta -> (panel, kolor). Kolejnosc = kolejnosc w multiselect.
METRICS = {
    "Cena": ("price", "#6366f1"),
    "Cena docelowa (konsensus)": ("price", "#ea580c"),
    "Potencjał do celu (%)": ("pct", "#8b5cf6"),
    "P/E": ("ratio", "#ea580c"),
    "P/S": ("ratio", "#7c3aed"),
    "EV/EBITDA": ("ratio", "#0d9488"),
    "Marża operacyjna (%)": ("pct", "#dc2626"),
    "Przychody (roczne + prognoza)": ("fin", "#2563eb"),
    "Zysk netto (roczny)": ("fin", "#16a34a"),
    "Free Cash Flow (roczny)": ("fin", "#0d9488"),
    "EPS (roczny + prognoza)": ("eps", "#0891b2"),
}
DEFAULT_METRICS = ["Cena", "Cena docelowa (konsensus)", "P/E"]

# Tytuly paneli (jednostki)
_PANEL_TITLE = {"price": "Cena", "ratio": "Wskaźniki (x)", "pct": "%",
                "fin": "Sprawozdania (waluta)", "eps": "EPS"}
_PANEL_ORDER = ["price", "ratio", "pct", "fin", "eps"]


def fig_price(prices: dict, years: int = 1):
    """prices: {YYYY-MM-DD: close}. Zwraca wykres ceny za ostatnie `years` lat."""
    if not prices:
        return None
    cutoff = datetime.now() - timedelta(days=365 * years + 7)
    items = []
    for d, v in prices.items():
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if dt >= cutoff and h.is_num(v):
            items.append((dt, v))
    items.sort()
    if len(items) < 2:
        return None
    xs = [dt for dt, _ in items]
    ys = [v for _, v in items]
    up = ys[-1] >= ys[0]
    color = h.COLORS["pos"] if up else h.COLORS["neg"]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=2),
                    hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>")
    # autoskala Y wokol realnego zakresu cen (nie od zera) + lekki margines
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.06 or hi * 0.02
    fig.update_yaxes(range=[lo - pad, hi + pad])
    return h.base_layout(fig, height=300, time_axis=True)


# ------------------------------------------------------ narzedzia wewnetrzne ---

def _parse_prices(prices: dict) -> list[tuple[datetime, float]]:
    items = []
    for d, v in (prices or {}).items():
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if h.is_num(v):
            items.append((dt, v))
    items.sort()
    return items


def _cut(items, period_key: str):
    if not items or period_key == "Max":
        return items
    last = items[-1][0]
    if period_key == "YTD":
        cutoff = datetime(last.year, 1, 1)
    else:
        days = RANGES.get(period_key) or 366
        cutoff = last - timedelta(days=days)
    return [(dt, v) for dt, v in items if dt >= cutoff]


def _annual_lookup(series: dict):
    """Zwraca funkcje rok->wartosc: ostatni dostepny rok <= zadany."""
    if not series:
        return lambda y: None
    years = sorted(int(y) for y, v in series.items() if h.is_num(v))
    vals = {int(y): v for y, v in series.items() if h.is_num(v)}

    def at(y: int):
        best = None
        for yr in years:
            if yr <= y:
                best = yr
            else:
                break
        return vals.get(best) if best is not None else None

    return at


def _weekly_ratio(px_items, num_fn):
    """[(dt, cena)] + funkcja(dt, cena)->wartosc -> serie tygodniowa."""
    xs, ys = [], []
    for dt, p in px_items:
        v = num_fn(dt, p)
        if h.is_num(v):
            xs.append(dt)
            ys.append(v)
    return xs, ys


def _median3y(xs, ys):
    """Mediana z ostatnich 3 lat serii (do linii przerywanej)."""
    if not xs:
        return None
    cutoff = xs[-1] - timedelta(days=3 * 366)
    vals = [v for x, v in zip(xs, ys) if x >= cutoff]
    return statistics.median(vals) if vals else None


def _annual_points(series: dict, first_dt: datetime):
    """Seria {rok: v} -> punkty (31.12 kazdego roku) w oknie od first_dt."""
    xs, ys = [], []
    for y, v in sorted((int(y), v) for y, v in (series or {}).items()
                       if h.is_num(v)):
        dt = datetime(y, 12, 31)
        if dt >= first_dt - timedelta(days=366):
            xs.append(dt)
            ys.append(v)
    return xs, ys


def _forecast_points(fc: dict):
    """Prognozy {rok: {avg,low,high}} -> (xs, avg, low, high)."""
    xs, avg, low, high = [], [], [], []
    for y, d in sorted((int(y), d) for y, d in (fc or {}).items()):
        if not isinstance(d, dict) or not h.is_num(d.get("avg")):
            continue
        xs.append(datetime(y, 6, 30))
        avg.append(d["avg"])
        low.append(d.get("low"))
        high.append(d.get("high"))
    return xs, avg, low, high


def _fmt_val(panel: str, v: float) -> str:
    if panel == "pct":
        return f"{v * 100:.1f}%"
    if panel == "fin":
        return h.human(v)
    return f"{v:.2f}"


def _end_label(fig, row, x, y, panel, color):
    """Etykieta ostatniej wartosci na prawej krawedzi (jak w Qualtrim)."""
    if not h.is_num(y):
        return
    fig.add_annotation(x=x, y=y, row=row, col=1, text=_fmt_val(panel, y),
                       showarrow=False, xanchor="left", xshift=4,
                       font=dict(color="#ffffff", size=11),
                       bgcolor=color, opacity=0.9, borderpad=2)


# ----------------------------------------------------------- wykres glowny ---

def fig_advanced(hist: dict, row: dict, prices: dict,
                 period_key: str = "1R", selected: list[str] | None = None):
    """Wielopanelowy wykres kursu + nakladek. Zwraca figure albo None."""
    selected = [m for m in (selected or DEFAULT_METRICS) if m in METRICS]
    if not selected:
        selected = ["Cena"]
    px_all = _parse_prices(prices)
    px = _cut(px_all, period_key)
    if len(px) < 2:
        return None
    first_dt = px[0][0]
    last_dt = px[-1][0]

    s = hist.get("series", {})
    fc = hist.get("forecast", {})
    shares_at = _annual_lookup(s.get("shares"))
    revenue_at = _annual_lookup(s.get("revenue"))
    eps_at = _annual_lookup(s.get("eps"))
    ebitda_at = _annual_lookup(s.get("ebitda"))
    net_debt_at = _annual_lookup(s.get("net_debt"))
    target_mean = (fc.get("price_target") or {}).get("mean")

    # ktore panele sa potrzebne (w stalej kolejnosci)
    panels = [p for p in _PANEL_ORDER
              if any(METRICS[m][0] == p for m in selected)]
    rowno = {p: i + 1 for i, p in enumerate(panels)}
    weights = {"price": 2.2, "ratio": 1.2, "pct": 1.0, "fin": 1.2, "eps": 1.0}
    total_w = sum(weights[p] for p in panels)
    fig = make_subplots(
        rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[weights[p] / total_w for p in panels])

    def add(panel, xs, ys, name, color, dash=None, mode="lines",
            label=True, hover=None):
        if not xs:
            return
        r = rowno[panel]
        fig.add_scatter(
            x=xs, y=ys, mode=mode, name=name, row=r, col=1,
            line=dict(color=color, width=2, dash=dash),
            marker=dict(size=6),
            hovertemplate=(hover or "%{x|%Y-%m-%d}: %{y:.2f}") + "<extra>"
                          + name + "</extra>")
        if label:
            _end_label(fig, r, xs[-1], ys[-1], panel, color)

    for m in selected:
        panel, color = METRICS[m]

        if m == "Cena":
            xs = [dt for dt, _ in px]
            ys = [v for _, v in px]
            add(panel, xs, ys, "Cena", color)

        elif m == "Cena docelowa (konsensus)":
            if h.is_num(target_mean):
                add(panel, [first_dt, last_dt], [target_mean, target_mean],
                    "Cena docelowa", color, dash="dash",
                    hover="cel: %{y:.2f}")

        elif m == "Potencjał do celu (%)":
            if h.is_num(target_mean):
                xs, ys = _weekly_ratio(
                    px, lambda dt, p: (target_mean / p - 1) if p else None)
                add(panel, xs, ys, "Potencjał do celu", color,
                    hover="%{x|%Y-%m-%d}: %{y:.1%}")

        elif m == "P/E":
            xs, ys = _weekly_ratio(
                px, lambda dt, p: (p / eps_at(dt.year))
                if h.is_num(eps_at(dt.year)) and eps_at(dt.year) > 0 else None)
            add(panel, xs, ys, "P/E", color)
            med = _median3y(xs, ys)
            if med is not None:
                add(panel, [first_dt, last_dt], [med, med],
                    "P/E mediana 3L", color, dash="dot", label=False,
                    hover="mediana 3L: %{y:.2f}")

        elif m == "P/S":
            def _ps(dt, p):
                sh, rv = shares_at(dt.year), revenue_at(dt.year)
                if h.is_num(sh) and h.is_num(rv) and rv > 0:
                    return p * sh / rv
                return None
            xs, ys = _weekly_ratio(px, _ps)
            add(panel, xs, ys, "P/S", color)
            med = _median3y(xs, ys)
            if med is not None:
                add(panel, [first_dt, last_dt], [med, med],
                    "P/S mediana 3L", color, dash="dot", label=False,
                    hover="mediana 3L: %{y:.2f}")

        elif m == "EV/EBITDA":
            def _ev(dt, p):
                sh, eb = shares_at(dt.year), ebitda_at(dt.year)
                nd = net_debt_at(dt.year)
                if h.is_num(sh) and h.is_num(eb) and eb > 0:
                    return (p * sh + (nd if h.is_num(nd) else 0)) / eb
                return None
            xs, ys = _weekly_ratio(px, _ev)
            add(panel, xs, ys, "EV/EBITDA", color)
            med = _median3y(xs, ys)
            if med is not None:
                add(panel, [first_dt, last_dt], [med, med],
                    "EV/EBITDA mediana 3L", color, dash="dot", label=False,
                    hover="mediana 3L: %{y:.2f}")

        elif m == "Marża operacyjna (%)":
            xs, ys = _annual_points(s.get("operating_margin"), first_dt)
            add(panel, xs, ys, "Marża operacyjna", color,
                mode="lines+markers", hover="%{x|%Y}: %{y:.1%}")

        elif m == "Przychody (roczne + prognoza)":
            xs, ys = _annual_points(s.get("revenue"), first_dt)
            add(panel, xs, ys, "Przychody", color, mode="lines+markers",
                hover="%{x|%Y}: %{y:.3s}")
            fxs, favg, _, _ = _forecast_points(fc.get("revenue"))
            if fxs and xs:
                add(panel, [xs[-1]] + fxs, [ys[-1]] + favg,
                    "Przychody (prognoza)", color, dash="dot",
                    mode="lines+markers", hover="%{x|%Y}: %{y:.3s}")

        elif m == "Zysk netto (roczny)":
            xs, ys = _annual_points(s.get("net_income"), first_dt)
            add(panel, xs, ys, "Zysk netto", color, mode="lines+markers",
                hover="%{x|%Y}: %{y:.3s}")

        elif m == "Free Cash Flow (roczny)":
            xs, ys = _annual_points(s.get("fcf"), first_dt)
            add(panel, xs, ys, "FCF", color, mode="lines+markers",
                hover="%{x|%Y}: %{y:.3s}")

        elif m == "EPS (roczny + prognoza)":
            xs, ys = _annual_points(s.get("eps"), first_dt)
            add(panel, xs, ys, "EPS", color, mode="lines+markers",
                hover="%{x|%Y}: %{y:.2f}")
            fxs, favg, _, _ = _forecast_points(fc.get("eps"))
            if fxs and xs:
                add(panel, [xs[-1]] + fxs, [ys[-1]] + favg,
                    "EPS (prognoza)", color, dash="dot",
                    mode="lines+markers", hover="%{x|%Y}: %{y:.2f}")

    if not fig.data:
        return None

    # autoskala panelu ceny wokol realnego zakresu (nie od zera)
    if "price" in rowno:
        ys = [v for _, v in px]
        cand = ys + ([target_mean] if (h.is_num(target_mean) and
                     "Cena docelowa (konsensus)" in selected) else [])
        lo, hi = min(cand), max(cand)
        pad = (hi - lo) * 0.06 or hi * 0.02
        fig.update_yaxes(range=[lo - pad, hi + pad], row=rowno["price"], col=1)
    if "pct" in rowno:
        fig.update_yaxes(tickformat=".0%", row=rowno["pct"], col=1)

    for p, r in rowno.items():
        fig.update_yaxes(title_text=_PANEL_TITLE[p], title_font=dict(size=11),
                         row=r, col=1)

    height = int(140 + 190 * weights["price" if "price" in rowno else panels[0]]
                 / weights["price"] + 130 * (len(panels) - 1))
    fig.update_layout(
        height=max(320, height),
        margin=dict(l=8, r=64, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)",
                     zeroline=False)
    return fig

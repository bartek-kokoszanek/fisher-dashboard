"""Panel decyzyjny per spolka: scenariusze 3Y, bramka decyzyjna, kill criteria, os czasu.

Natywna wersja dashboardu HTML uzytkownika (analiza CRWV) dzialajaca dla kazdego
tickera. Trzy warstwy danych:
  1. Ilosciowe (cena, kapitalizacja, data raportu...) — zawsze swieze z `row`.
  2. Baza jakosciowa z AI (Gemini przez ai_research.complete_json) — cache
     data/decision_<ticker>.json; bez klucza API fallback mechaniczny.
  3. Nadpisania uzytkownika — wl["decision"][ticker], trwale przez watchlists
     (Gist), lacznie ze stanem zlamanych kill criteria.

Funkcje obliczeniowe na gorze modulu sa czyste (testowalne bez Streamlita).
"""
from __future__ import annotations

import copy
import json
import math as _math
import os
from datetime import date, datetime, timezone

import config

# ---------------- Stale ----------------

GATE_LABELS = {
    "fisher":    "Fisher ≥ 10/15, brak twardych czerwonych flag",
    "variant":   "Variant perception po mojej stronie",
    "asym":      "Asymetria ≥ 2:1 i EV > kurs",
    "cagr":      "Base case ≥ hurdle rate 12–15%",
    "catalyst":  "Katalizator w 12–18M",
    "liquidity": "Plynnosc wystarczajaca",
}
GATE_ORDER = list(GATE_LABELS)
STATUSES = ("ok", "borderline", "fail")
_STATUS_ICON = {"ok": "✅", "borderline": "⚠️", "fail": "❌"}
_RANK = {"ok": 0, "borderline": 1, "fail": 2}

HURDLE_LOW, HURDLE_HIGH = 0.12, 0.15   # prog CAGR (dolna/pelna granica)
ASYM_MIN = 2.0                          # wymagana asymetria zysk:strata


def _f(v) -> float | None:
    """Bezpieczna konwersja na float (None/NaN/str -> None)."""
    try:
        x = float(v)
        return None if _math.isnan(x) or _math.isinf(x) else x
    except (TypeError, ValueError):
        return None


# ---------------- Obliczenia (czyste funkcje) ----------------

def compute_math(price, scen: dict) -> dict:
    """EV, CAGR i asymetria ze scenariuszy (wiernie do JS z dashboardu HTML).

    scen = {"low"/"base"/"high": {"price": .., "prob": ..}}; prob base
    dopelnia sume do 100. Zwraca None w polach nieobliczalnych.
    """
    price = _f(price)
    p_low = _f(scen.get("low", {}).get("price"))
    p_base = _f(scen.get("base", {}).get("price"))
    p_high = _f(scen.get("high", {}).get("price"))
    low_prob = max(0, min(100, int(_f(scen.get("low", {}).get("prob")) or 0)))
    high_prob = max(0, min(100, int(_f(scen.get("high", {}).get("prob")) or 0)))
    base_prob = max(0, 100 - low_prob - high_prob)

    out = {"low_prob": low_prob, "base_prob": base_prob, "high_prob": high_prob,
           "ev": None, "ev_pct": None, "cagr_ev": None, "cagr_base": None,
           "asym": None}
    if None in (p_low, p_base, p_high):
        return out
    ev = (p_low * low_prob + p_base * base_prob + p_high * high_prob) / 100
    out["ev"] = ev
    if price and price > 0:
        out["ev_pct"] = ev / price - 1
        if ev > 0:
            out["cagr_ev"] = (ev / price) ** (1 / 3) - 1
        if p_base > 0:
            out["cagr_base"] = (p_base / price) ** (1 / 3) - 1
        if price > p_low:
            out["asym"] = (p_high - price) / (price - p_low)
        # price <= p_low: strata do scenariusza low zerowa -> asym "n/d" (None)
    return out


def _worse(a: str | None, b: str | None) -> str:
    """Gorszy z dwoch statusow (None pomijany; oba None -> borderline)."""
    cand = [s for s in (a, b) if s in _RANK]
    if not cand:
        return "borderline"
    return max(cand, key=lambda s: _RANK[s])


def eval_gate(row: dict, mth: dict, gate_ai: dict, overrides: dict) -> list[dict]:
    """6 warunkow bramki: auto z danych/matematyki + ocena AI + reczne nadpisania.

    Dla warunkow policzalnych wygrywa GORSZY ze statusow (auto vs AI);
    nadpisanie uzytkownika (overrides[id]) zastepuje ocene AI.
    """
    price = _f(row.get("price"))
    combined = _f(row.get("combined"))
    mcap = _f(row.get("market_cap"))

    auto: dict[str, tuple[str | None, str]] = {}
    # fisher: wynik laczny 0-100 mapowany na skale 15 pkt (~10/15 = 67)
    if combined is None:
        auto["fisher"] = (None, "brak wyniku strategii")
    elif combined >= 67:
        auto["fisher"] = ("ok", f"wynik {combined:.0f}/100 (~{combined*15/100:.0f}/15)")
    elif combined >= 55:
        auto["fisher"] = ("borderline", f"wynik {combined:.0f}/100 — blisko progu 10/15")
    else:
        auto["fisher"] = ("fail", f"wynik {combined:.0f}/100 — ponizej progu 10/15")

    # asym: asymetria >=2 ORAZ EV > kurs (jedno z dwoch -> borderline)
    asym, ev = mth.get("asym"), mth.get("ev")
    if price is None or ev is None:
        auto["asym"] = (None, "brak danych do obliczen")
    else:
        a_ok = (asym is None and ev > price) or (asym is not None and asym >= ASYM_MIN)
        e_ok = ev > price
        info = ("kurs ponizej scenariusza low — strata ograniczona"
                if asym is None else f"asymetria {asym:.1f}:1, EV {ev:.0f} vs kurs {price:.0f}")
        auto["asym"] = ("ok" if a_ok and e_ok else "borderline" if a_ok or e_ok
                        else "fail", info)

    # cagr: base case vs hurdle 12/15%
    cb = mth.get("cagr_base")
    if cb is None:
        auto["cagr"] = (None, "brak danych do obliczen")
    elif cb >= HURDLE_HIGH:
        auto["cagr"] = ("ok", f"CAGR base {cb*100:.1f}% ≥ {HURDLE_HIGH*100:.0f}%")
    elif cb >= HURDLE_LOW:
        auto["cagr"] = ("borderline", f"CAGR base {cb*100:.1f}% — dolna granica progu")
    else:
        auto["cagr"] = ("fail", f"CAGR base {cb*100:.1f}% < {HURDLE_LOW*100:.0f}%")

    # liquidity: kapitalizacja jako proxy plynnosci
    if mcap is None:
        auto["liquidity"] = (None, "brak kapitalizacji")
    elif mcap > 500e6:
        auto["liquidity"] = ("ok", f"kapitalizacja {mcap/1e9:.1f} mld")
    elif mcap > 100e6:
        auto["liquidity"] = ("borderline", f"kapitalizacja {mcap/1e6:.0f} mln — srednia plynnosc")
    else:
        auto["liquidity"] = ("fail", f"kapitalizacja {mcap/1e6:.0f} mln — niska plynnosc")

    out = []
    for gid in GATE_ORDER:
        ai_item = gate_ai.get(gid) or {}
        ov = overrides.get(gid) or {}
        qual_status = ov.get("status") if ov.get("status") in STATUSES \
            else (ai_item.get("status") if ai_item.get("status") in STATUSES else None)
        qual_info = ov.get("info") or ai_item.get("info") or ""
        a_status, a_info = auto.get(gid, (None, ""))
        if gid in ("variant", "catalyst"):        # czysto jakosciowe
            status = qual_status or "borderline"
            info = qual_info or "ocena reczna / wymaga AI"
        else:
            status = _worse(a_status, qual_status)
            info = " · ".join(x for x in (a_info, qual_info) if x)
        out.append({"id": gid, "label": GATE_LABELS[gid], "status": status,
                    "info": info})
    return out


def final_verdict(gate: list[dict], kill_broken: int) -> dict:
    """Werdykt koncowy z bramki + kill criteria (regula jak w dashboardzie HTML)."""
    if kill_broken >= 1:
        return {"label": "WYJDZ / NIE KUPUJ", "level": "red",
                "desc": f"zlamane kill criteria: {kill_broken}"}
    st_by_id = {g["id"]: g["status"] for g in gate}
    math_ok = st_by_id.get("asym") == "ok" and st_by_id.get("cagr") in ("ok", "borderline")
    quality_ok = all(st_by_id.get(g) != "fail" for g in ("fisher", "variant", "catalyst"))
    if all(s == "ok" for s in st_by_id.values()):
        return {"label": "POZYCJA OK", "level": "green",
                "desc": "wszystkie warunki bramki spelnione"}
    if math_ok and quality_ok:
        return {"label": "OK Z ZASTRZEZENIAMI — pol pozycji", "level": "amber",
                "desc": "bramka przechodzi, ale z warunkami granicznymi"}
    if math_ok:
        return {"label": "SPEKULACJA ≤2% portfela", "level": "amber",
                "desc": "matematyka sie spina, jakosc nie — nie dla portfela emerytalnego"}
    return {"label": "NIE KUPUJ — matematyka sie nie spina", "level": "red",
            "desc": "asymetria lub CAGR ponizej wymagan"}


def verdict_for(ticker: str, row: dict, wl: dict | None = None) -> dict | None:
    """Werdykt bramki BEZ renderowania panelu — do kolumny w rankingu.

    Idzie dokladnie ta sama sciezka co render(), zeby kolumna i panel nigdy
    nie pokazaly dwoch roznych werdyktow: baza AI (gdy wygenerowana) albo
    mechaniczna, na to nadpisania uzytkownika z wl["decision"][ticker],
    ta sama bramka i ten sam licznik zlamanych kill criteria.
    Zwraca None, gdy nie da sie zbudowac scenariuszy (brak ceny i konsensusu).
    """
    user = ((wl or {}).get("decision") or {}).get(ticker) or {}
    baseline = load_cached(ticker) or mechanical_baseline(row)
    merged = _merge(baseline, user)
    scen = merged.get("scenarios") or {}
    if not scen:
        return None
    mth = compute_math(_f(row.get("price")), scen)
    gate = eval_gate(row, mth,
                     {g["id"]: g for g in merged.get("gate", [])
                      if isinstance(g, dict)},
                     user.get("gate_overrides", {}))
    kill = list(merged.get("kill") or [])
    n_broken = len([k for k in (user.get("kill_broken") or []) if k in kill])
    out = final_verdict(gate, n_broken)
    out["source"] = baseline.get("source", "mechanical")
    return out


def mechanical_baseline(row: dict) -> dict:
    """Baza scenariuszy bez AI: konsensus analitykow albo zalozony wzrost roczny.

    target_mean to 12-miesieczna cena docelowa (Yahoo targetMeanPrice), a
    panel liczy scenariusze 3-LETNIE (compute_math robi (base/price)**(1/3)
    dla CAGR) — bez przeliczenia 1-roczny konsensus wpadalby do wzoru na 3
    lata i systemowo zanizal CAGR (np. 20% konsensusu rocznego -> tylko 6.3%
    w cube-root na 3 lata, czyli ponizej progu bramki, mimo ze 20%/rok to
    dobry wynik). Zakladamy, ze roczne tempo z konsensusu (albo zalozone
    25%/rok, gdy brak konsensusu) utrzymuje sie 3 lata, i tak wyliczona cene
    bazowa dopiero podajemy do tej samej matematyki 3-letniej co scenariusze
    od AI/uzytkownika.
    """
    price = _f(row.get("price"))
    target = _f(row.get("target_mean"))
    r1 = (target / price - 1) if (target and price and target > 0 and price > 0) else 0.25
    r1 = max(-0.5, min(r1, 1.0))  # sanity clamp - odstajace dane Yahoo nie majq eksplodowac
    base = price * (1 + r1) ** 3 if price else None
    src = "konsensus analitykow (cena docelowa, rzutowana na 3 lata)" \
        if target else "zalozony wzrost 25%/rok (brak konsensusu), rzutowany na 3 lata"
    scen = {}
    if base:
        # min(..., price): scenariusz negatywny nie powinien wypadac powyzej
        # dzisiejszej ceny - przy duzym r1 samo 0.45*base moze to przekroczyc.
        low = min(max(0.3 * price, base * 0.45), price)
        scen = {
            "low":  {"price": round(low, 2), "prob": 25,
                     "desc": f"Scenariusz negatywny — uzupelnij recznie ({src})."},
            "base": {"price": round(base, 2), "prob": 50,
                     "desc": f"Scenariusz bazowy — {src}."},
            "high": {"price": round(base * 1.6, 2), "prob": 25,
                     "desc": f"Scenariusz pozytywny — uzupelnij recznie ({src})."},
        }
    timeline = []
    ned = row.get("next_earnings_date")
    if ned:
        timeline.append({"date": str(ned), "title": "Raport kwartalny",
                         "desc": "Najblizsza planowana publikacja wynikow.",
                         "type": "plus"})
    return {"scenarios": scen, "gate": [], "kill": [], "timeline": timeline,
            "verdict_hint": "", "source": "mechanical"}


def _validate(data: dict, row: dict) -> dict:
    """Sanityzacja JSON z modelu: koercja liczb, clamp prob, porzadek cen,
    statusy/typy spoza slownika, limity dlugosci; braki -> fallback mechaniczny."""
    fb = mechanical_baseline(row)
    out = {"source": "ai"}

    scen_in = data.get("scenarios") if isinstance(data.get("scenarios"), dict) else {}
    scen = {}
    for key in ("low", "base", "high"):
        s = scen_in.get(key) if isinstance(scen_in.get(key), dict) else {}
        p = _f(s.get("price"))
        pr = _f(s.get("prob"))
        scen[key] = {"price": p if p and p > 0 else None,
                     "prob": max(0, min(100, int(pr))) if pr is not None else None,
                     "desc": str(s.get("desc") or "")[:400]}
    prices = [scen[k]["price"] for k in ("low", "base", "high")]
    if all(p is not None for p in prices):
        lo, mid, hi = sorted(prices)
        scen["low"]["price"], scen["base"]["price"], scen["high"]["price"] = lo, mid, hi
    else:
        scen = fb["scenarios"]
    if scen:
        lp = scen["low"].get("prob")
        hp = scen["high"].get("prob")
        lp = lp if lp is not None else 25
        hp = hp if hp is not None else 25
        if lp + hp > 100:  # skalowanie, by base >= 0
            tot = lp + hp
            lp, hp = round(lp * 100 / tot), round(hp * 100 / tot)
        scen["low"]["prob"], scen["high"]["prob"] = lp, hp
        scen["base"]["prob"] = max(0, 100 - lp - hp)
    out["scenarios"] = scen

    gate = []
    seen = set()
    for g in (data.get("gate") or []):
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id") or "")
        if gid not in GATE_LABELS or gid in seen:
            continue
        seen.add(gid)
        gate.append({"id": gid,
                     "status": g.get("status") if g.get("status") in STATUSES
                     else "borderline",
                     "info": str(g.get("info") or "")[:300]})
    out["gate"] = gate

    out["kill"] = [str(k)[:200] for k in (data.get("kill") or [])
                   if str(k).strip()][:8] or fb["kill"]

    timeline = []
    for t in (data.get("timeline") or []):
        if not isinstance(t, dict) or not str(t.get("title") or "").strip():
            continue
        timeline.append({"date": str(t.get("date") or "b.d.")[:40],
                         "title": str(t.get("title"))[:120],
                         "desc": str(t.get("desc") or "")[:400],
                         "type": t.get("type") if t.get("type") in ("plus", "minus")
                         else "minus"})
    out["timeline"] = timeline[:8] or fb["timeline"]

    out["verdict_hint"] = str(data.get("verdict_hint") or "")[:300]
    return out


def _merge(baseline: dict, user: dict) -> dict:
    """Baza (AI/fallback) + nadpisania uzytkownika (klucze obecne w user wygrywaja)."""
    merged = copy.deepcopy(baseline)
    for key in ("scenarios", "kill", "timeline"):
        if user.get(key):
            merged[key] = copy.deepcopy(user[key])
    return merged


# ---------------- Cache AI ----------------

SYSTEM_DECISION = (
    "Jestes doswiadczonym analitykiem akcji laczacym frameworki Phila Fishera "
    "i Petera Lyncha. Budujesz panel decyzyjny dla jednej spolki: scenariusze "
    "3-letnie cen akcji, bramke decyzyjna, kill criteria (sygnaly wyjscia) "
    "i os czasu katalizatorow/ryzyk. Odpowiadasz WYLACZNIE poprawnym JSON "
    "zgodnym ze schematem uzytkownika, po polsku, bez markdown i komentarzy."
)

_SCHEMA_HINT = """{
  "scenarios": {
    "low":  {"price": 0.0, "prob": 30, "desc": "1-2 zdania: co musi pojsc zle"},
    "base": {"price": 0.0, "prob": 45, "desc": "1-2 zdania: scenariusz bazowy"},
    "high": {"price": 0.0, "prob": 25, "desc": "1-2 zdania: co musi pojsc dobrze"}
  },
  "gate": [
    {"id": "fisher",    "status": "ok|borderline|fail", "info": "krotko dlaczego"},
    {"id": "variant",   "status": "ok|borderline|fail", "info": "..."},
    {"id": "asym",      "status": "ok|borderline|fail", "info": "..."},
    {"id": "cagr",      "status": "ok|borderline|fail", "info": "..."},
    {"id": "catalyst",  "status": "ok|borderline|fail", "info": "..."},
    {"id": "liquidity", "status": "ok|borderline|fail", "info": "..."}
  ],
  "kill": ["4-6 konkretnych, mierzalnych sygnalow natychmiastowego wyjscia"],
  "timeline": [{"date": "Sie 2026", "title": "...", "desc": "...", "type": "plus|minus"}],
  "verdict_hint": "1 zdanie podsumowania"
}"""


def _cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR,
                        f"decision_{ticker.replace('.', '_')}.json")


def load_cached(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def generate_ai(ticker: str, row: dict) -> dict:
    """Generuje baze panelu przez LLM (kontekst z row + istniejacych cache'ow AI)."""
    import ai_research
    import research_deep

    ctx = {k: row.get(k) for k in (
        "name", "market", "sector", "currency", "price", "market_cap",
        "trailing_pe", "debt_to_equity", "target_mean", "target_upside",
        "analyst_count", "rev_growth_est", "eps_growth_est",
        "next_earnings_date", "combined", "score", "quality", "return_6m")}
    ctx = {k: v for k, v in ctx.items()
           if (isinstance(v, str) and v) or _f(v) is not None}
    deep = research_deep.load_cached(ticker) or {}
    ai = ai_research.load_cached(ticker) or {}
    extra = {
        "sentyment_rynku": deep.get("sentiment"),
        "sentyment_opis": deep.get("sentiment_summary"),
        "kluczowe_newsy": [
            {"data": n.get("date"), "tytul": n.get("title")}
            for n in (deep.get("key_news") or [])[:6] if isinstance(n, dict)],
        "zalety": (ai.get("strengths") or [])[:5],
        "wady": (ai.get("weaknesses") or [])[:5],
    }
    today = date.today().isoformat()
    prompt = (
        f"Spolka: {ticker} ({row.get('name', ticker)}). Dzis: {today}.\n"
        f"Dane ilosciowe (Yahoo):\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n"
        f"Kontekst jakosciowy (wczesniejszy research):\n"
        f"{json.dumps(extra, ensure_ascii=False, default=str)}\n\n"
        "Zadanie: wypelnij panel decyzyjny. Ceny scenariuszy w walucie notowan, "
        "horyzont 3 lata, prawdopodobienstwa low+base+high = 100. Kill criteria "
        "maja byc mierzalne (progi, wydarzenia), a timeline zawierac 4-6 wpisow "
        "z przyblizonymi datami (katalizatory 'plus', ryzyka 'minus').\n"
        f"Zwroc WYLACZNIE JSON wg schematu:\n{_SCHEMA_HINT}"
    )
    data = ai_research.complete_json(SYSTEM_DECISION, prompt)
    result = _validate(data, row)
    result.update({"ticker": ticker, "model": ai_research.MODEL,
                   "generated_at": datetime.now(timezone.utc)
                   .isoformat(timespec="seconds")})
    with open(_cache_path(ticker), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


# ---------------- UI ----------------

_PILL = {"green": ("#16a34a", "#f0fdf4"), "amber": ("#d97706", "#fffbeb"),
         "red": ("#dc2626", "#fef2f2")}


def _fmt_big(v) -> str:
    v = _f(v)
    if v is None:
        return "—"
    if abs(v) >= 1e12:
        return f"{v/1e12:.2f} bln"
    if abs(v) >= 1e9:
        return f"{v/1e9:.1f} mld"
    if abs(v) >= 1e6:
        return f"{v/1e6:.0f} mln"
    return f"{v:,.0f}"


def _days_to(iso: str | None) -> int | None:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return (d - date.today()).days
    except (TypeError, ValueError):
        return None


def _color_caption(txt: str, level: str) -> str:
    col = _PILL.get(level, _PILL["amber"])[0]
    return f"<span style='color:{col};font-weight:600'>{txt}</span>"


def render(ticker: str, row: dict, wl: dict, save_wl) -> None:
    """Caly panel decyzyjny dla wybranej spolki (wpiecie z app.py)."""
    import streamlit as st
    import ai_research
    import research_deep
    from charts.helpers import fmt_dt

    st.subheader(f"🎯 Panel decyzyjny — {ticker} — {row.get('name', ticker)}")
    st.caption("Scenariusze 3-letnie, bramka decyzyjna, kill criteria, "
               "oś czasu katalizatorów.")

    dec_store = wl.setdefault("decision", {})
    user = dec_store.get(ticker, {})
    rev_key = f"dp_rev_{ticker}"
    rev = st.session_state.setdefault(rev_key, 0)
    K = f"dp_{ticker}_{rev}"  # prefiks kluczy widgetow (anty-bleed miedzy tickerami)

    baseline = load_cached(ticker) or mechanical_baseline(row)
    merged = _merge(baseline, user)
    price = _f(row.get("price"))
    cur = row.get("currency") or ""

    # --- przyciski AI / reset ---
    bc1, bc2, bc3 = st.columns([2, 1, 3])
    with bc1:
        if st.button("🤖 Wygeneruj / odswiez baze (AI)", key=f"{K}_gen",
                     disabled=not ai_research.available()):
            with st.spinner("Model buduje scenariusze, kill criteria i os czasu..."):
                try:
                    generate_ai(ticker, row)
                    st.session_state[rev_key] = rev + 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Blad generowania: {e}")
    with bc2:
        if st.button("↺ Przywroc baze", key=f"{K}_reset",
                     disabled=ticker not in dec_store,
                     help="Usuwa Twoje nadpisania — wraca baza AI/mechaniczna."):
            dec_store.pop(ticker, None)
            save_wl()
            st.session_state[rev_key] = rev + 1
            st.rerun()
    with bc3:
        if not ai_research.available():
            st.caption("Brak klucza GEMINI_API_KEY — panel dziala na bazie "
                       "mechanicznej (konsensus analitykow), uzupelnij pola recznie.")
        elif baseline.get("source") == "ai":
            st.caption(f"Baza: AI ({baseline.get('model')}) · wygenerowano "
                       f"{fmt_dt(baseline.get('generated_at'))}")
        else:
            st.caption("Baza mechaniczna — kliknij przycisk AI, by wypelnic "
                       "scenariusze i kryteria analiza modelu.")

    if not merged.get("scenarios"):
        st.warning("Brak ceny i konsensusu — nie da sie zbudowac scenariuszy "
                   "dla tej spolki.")
        return

    # --- KPI ---
    deep = research_deep.load_cached(ticker) or {}
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Kapitalizacja", f"{_fmt_big(row.get('market_cap'))} {cur}".strip())
    pe = _f(row.get("trailing_pe"))
    k2.metric("C/Z", f"{pe:.1f}" if pe is not None else "—")
    dte = _f(row.get("debt_to_equity"))
    k3.metric("Dlug/kapital", f"{dte:.2f}" if dte is not None else "—")
    tm = _f(row.get("target_mean"))
    tu = _f(row.get("target_upside"))
    k4.metric("Cena docelowa", f"{tm:.2f} {cur}".strip() if tm else "—",
              delta=f"{tu*100:+.1f}%" if tu is not None else None)
    cb = _f(row.get("combined"))
    k5.metric("Wynik strategii", f"{cb:.1f}" if cb is not None else "—")
    snt = _f(deep.get("sentiment"))
    k6.metric("Sentyment", f"{snt:+.0f}" if snt is not None else "—",
              help="Z deep research (o ile wykonany); -100..+100")

    # --- scenariusze 3Y ---
    scen0 = merged["scenarios"]
    sc_cols = st.columns(3)
    scen = {}
    meta = {"low": ("🔻 LOW", "red"), "base": ("⚖️ BASE", "amber"),
            "high": ("🚀 HIGH", "green")}
    for col, key in zip(sc_cols, ("low", "base", "high")):
        with col:
            title, lvl = meta[key]
            st.markdown(f"**{title}**")
            p = st.number_input(
                f"Cena docelowa {cur}".strip(), min_value=0.0,
                value=float(scen0[key].get("price") or 0.0), step=0.1,
                format="%.2f", key=f"{K}_price_{key}")
            if price and p > 0:
                zw = (p / price - 1) * 100
                st.markdown(_color_caption(f"{zw:+.0f}% / 3 lata",
                                           "green" if zw >= 0 else "red"),
                            unsafe_allow_html=True)
            if key == "base":
                prob = None  # dopelnienie liczone nizej
            else:
                prob = st.slider("Prawdopodobienstwo %", 0, 60,
                                 value=min(60, int(scen0[key].get("prob") or 25)),
                                 key=f"{K}_prob_{key}")
            st.caption(scen0[key].get("desc") or "—")
            scen[key] = {"price": p, "prob": prob,
                         "desc": scen0[key].get("desc") or ""}
    scen["base"]["prob"] = max(0, 100 - scen["low"]["prob"] - scen["high"]["prob"])
    sc_cols[1].caption(f"🔒 dopelnia do 100% = {scen['base']['prob']}%")

    with st.expander("✏️ Edytuj opisy scenariuszy"):
        for key in ("low", "base", "high"):
            scen[key]["desc"] = st.text_area(
                meta[key][0], value=scen[key]["desc"], height=70,
                key=f"{K}_desc_{key}")

    mth = compute_math(price, scen)

    # --- wyniki na zywo ---
    r1, r2, r3 = st.columns(3)
    with r1:
        ev = mth["ev"]
        st.metric("Wartosc oczekiwana 3Y",
                  f"{ev:.0f} {cur}".strip() if ev is not None else "—",
                  delta=(f"{mth['ev_pct']*100:+.0f}% vs kurs"
                         if mth["ev_pct"] is not None else None))
    with r2:
        ce = mth["cagr_ev"]
        st.metric("CAGR (EV) vs hurdle 12–15%",
                  f"{ce*100:.1f}%" if ce is not None else "—")
        if ce is not None:
            lvl = "green" if ce >= HURDLE_HIGH else \
                  "amber" if ce >= HURDLE_LOW else "red"
            txt = ("powyzej progu ✓" if lvl == "green" else
                   "dolna granica progu ~" if lvl == "amber" else "ponizej progu ✗")
            st.markdown(_color_caption(txt, lvl), unsafe_allow_html=True)
    with r3:
        asym = mth["asym"]
        st.metric("Asymetria (wymagane ≥ 2:1)",
                  f"{asym:.1f} : 1" if asym is not None else "n/d")
        if asym is not None:
            lvl = "green" if asym >= ASYM_MIN else "red"
            st.markdown(_color_caption(
                "warunek spelniony ✓" if lvl == "green" else "warunek niespelniony ✗",
                lvl), unsafe_allow_html=True)
        elif price is not None:
            st.caption("kurs ponizej scenariusza low")

    # --- bramka + kill criteria ---
    gate_ai = {g["id"]: g for g in merged.get("gate", []) if isinstance(g, dict)}
    overrides = user.get("gate_overrides", {})

    kill = list(merged.get("kill") or [])
    broken_saved = set(user.get("kill_broken") or [])

    gcol, kcol = st.columns(2)
    with gcol:
        st.markdown("**🚪 Bramka decyzyjna**")
        # najpierw zbieramy reczne nadpisania, by wiersze liczyly sie na zywo
        with st.expander("✏️ Oceny reczne (nadpisz AI)"):
            new_ov = {}
            opts = ["auto/AI"] + list(STATUSES)
            for gid in GATE_ORDER:
                oc1, oc2 = st.columns([1, 2])
                cur_ov = overrides.get(gid, {})
                sel = oc1.selectbox(
                    gid, opts,
                    index=opts.index(cur_ov["status"])
                    if cur_ov.get("status") in STATUSES else 0,
                    key=f"{K}_ov_{gid}")
                info = oc2.text_input("komentarz", value=cur_ov.get("info", ""),
                                      key=f"{K}_ovinfo_{gid}",
                                      label_visibility="collapsed",
                                      placeholder="komentarz (opcjonalnie)")
                if sel != "auto/AI":
                    new_ov[gid] = {"status": sel, "info": info}
        gate = eval_gate(row, mth, gate_ai, new_ov)
        for g in gate:
            st.markdown(f"{_STATUS_ICON[g['status']]} **{g['label']}**")
            if g["info"]:
                st.caption(g["info"])
    with kcol:
        n_broken_now = 0
        checked = []
        head = st.empty()
        for i, kr in enumerate(kill):
            on = st.checkbox(kr, value=kr in broken_saved, key=f"{K}_kill_{i}")
            if on:
                checked.append(kr)
                n_broken_now += 1
        if kill:
            lvl = "red" if n_broken_now else "green"
            head.markdown(
                f"**💀 Kill criteria — monitoring** &nbsp; " +
                _color_caption(f"{n_broken_now} / {len(kill)} zlamanych", lvl),
                unsafe_allow_html=True)
        else:
            head.markdown("**💀 Kill criteria — monitoring**")
            st.caption("Brak kryteriow — wygeneruj przez AI albo dodaj recznie ponizej.")
        # stan zlamania zapisujemy od razu (to monitoring, nie moze zginac)
        if set(checked) != broken_saved:
            dec_store.setdefault(ticker, {})["kill_broken"] = checked
            dec_store[ticker]["updated_at"] = datetime.now(timezone.utc)\
                .isoformat(timespec="seconds")
            save_wl()
        with st.expander("✏️ Edytuj liste (1 kryterium = 1 linia)"):
            kill_txt = st.text_area("Kryteria", value="\n".join(kill), height=140,
                                    key=f"{K}_killtxt", label_visibility="collapsed")
            kill_new = [ln.strip() for ln in kill_txt.splitlines() if ln.strip()]

    verdict = final_verdict(gate, n_broken_now)

    # --- werdykt + licznik do raportu ---
    vc1, vc2 = st.columns([3, 1])
    with vc1:
        col, bg = _PILL[verdict["level"]]
        hint = merged.get("verdict_hint") or verdict["desc"]
        st.markdown(
            f"<div style='display:inline-block;padding:8px 18px;border-radius:9999px;"
            f"background:{bg};border:1px solid {col};color:{col};font-weight:700'>"
            f"WERDYKT BRAMKI: {verdict['label']}</div>"
            f"<div style='color:#64748b;font-size:0.85em;margin-top:4px'>{hint}</div>",
            unsafe_allow_html=True)
    with vc2:
        days = _days_to(row.get("next_earnings_date"))
        st.metric("Dni do raportu",
                  f"{days} dni" if days is not None and days >= 0 else "brak terminu",
                  help=f"Najblizsza publikacja: {row.get('next_earnings_date') or '—'}")

    # --- os czasu katalizatorow ---
    timeline = merged.get("timeline") or []
    timeline_new = list(timeline)  # bez edycji: bierz stan biezacy
    with st.expander("📅 Os czasu katalizatorow i ryzyk", expanded=bool(timeline)):
        for t in timeline:
            icon = "🟢" if t.get("type") == "plus" else "🔴"
            st.markdown(f"{icon} **{t.get('date', 'b.d.')}** — **{t.get('title', '')}**")
            if t.get("desc"):
                st.caption(t["desc"])
        # uwaga: expander nie moze byc zagniezdzony w expanderze -> toggle
        if st.toggle("✏️ Edytuj os czasu", key=f"{K}_tledit"):
            import pandas as pd
            tl_df = pd.DataFrame(timeline or [{"date": "", "title": "",
                                               "desc": "", "type": "plus"}])
            for c in ("date", "title", "desc", "type"):
                if c not in tl_df.columns:
                    tl_df[c] = ""
            edited_tl = st.data_editor(
                tl_df[["date", "title", "desc", "type"]],
                num_rows="dynamic", key=f"{K}_tl", hide_index=True,
                column_config={
                    "date": st.column_config.TextColumn("Data"),
                    "title": st.column_config.TextColumn("Tytul"),
                    "desc": st.column_config.TextColumn("Opis"),
                    "type": st.column_config.SelectboxColumn(
                        "Typ", options=["plus", "minus"], default="plus"),
                })
            timeline_new = [
                {"date": str(r["date"] or "b.d."), "title": str(r["title"]),
                 "desc": str(r["desc"] or ""), "type": r["type"] or "minus"}
                for _, r in edited_tl.iterrows() if str(r["title"] or "").strip()]

    # --- zapis nadpisan uzytkownika (1 przycisk = 1 PATCH do Gista) ---
    current = {"scenarios": scen, "gate_overrides": new_ov,
               "kill": kill_new, "timeline": timeline_new}
    saved_cmp = {"scenarios": user.get("scenarios") or scen0,
                 "gate_overrides": overrides,
                 "kill": user.get("kill") or list(merged.get("kill") or []),
                 "timeline": user.get("timeline") or timeline}
    dirty = json.dumps(current, sort_keys=True, default=str) != \
        json.dumps(saved_cmp, sort_keys=True, default=str)

    sv1, sv2 = st.columns([1, 4])
    with sv1:
        if st.button("💾 Zapisz panel", key=f"{K}_save"):
            entry = dec_store.setdefault(ticker, {})
            entry.update(current)
            entry["kill_broken"] = [k for k in checked if k in kill_new]
            entry["updated_at"] = datetime.now(timezone.utc)\
                .isoformat(timespec="seconds")
            save_wl()
            st.success("Zapisano.")
            st.rerun()
    with sv2:
        if dirty:
            st.caption("⚠️ Niezapisane zmiany — kliknij Zapisz, by przetrwaly restart.")
        elif user:
            st.caption(f"Twoje nadpisania zapisane {fmt_dt(user.get('updated_at'))}.")

    st.caption("Dane ilosciowe: Yahoo Finance · analiza jakosciowa: "
               + (f"AI {baseline.get('model')} · wygenerowano "
                  f"{fmt_dt(baseline.get('generated_at'))}"
                  if baseline.get("source") == "ai" else "baza mechaniczna (bez AI)")
               + " · edycje uzytkownika trwale w watchlists (Gist).")

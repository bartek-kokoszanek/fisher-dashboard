"""Testy panelu decyzyjnego: czyste funkcje + headless render (AppTest).

Uruchom:  python decision_test.py
Liczby referencyjne pochodza z dashboardu HTML uzytkownika (CRWV):
price=75, scenariusze 25/105/210 z prob 30/45/25 -> EV 107.25,
CAGR(EV) ~12.7%, asymetria 2.7:1.
"""
import decision_panel as dp

FAILS = []


def check(name, cond, detail=""):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(name)


# ---------------- compute_math: liczby referencyjne CRWV ----------------
scen = {"low": {"price": 25, "prob": 30},
        "base": {"price": 105, "prob": 45},
        "high": {"price": 210, "prob": 25}}
m = dp.compute_math(75, scen)
check("EV = 107.25", abs(m["ev"] - 107.25) < 1e-9, f"ev={m['ev']}")
check("EV% = +43%", abs(m["ev_pct"] - 0.43) < 0.001, f"ev_pct={m['ev_pct']:.4f}")
check("CAGR(EV) ~12.66%", abs(m["cagr_ev"] - 0.12662) < 0.0005,
      f"cagr_ev={m['cagr_ev']:.5f}")
check("asymetria 2.7:1", abs(m["asym"] - 2.7) < 1e-9, f"asym={m['asym']}")
check("base_prob dopelnia do 100", m["base_prob"] == 45)

# guardy
m2 = dp.compute_math(20, scen)  # kurs ponizej low -> asym n/d
check("kurs<=low -> asym None", m2["asym"] is None)
m3 = dp.compute_math(None, scen)
check("price None -> ev liczone, reszta None",
      m3["ev"] is not None and m3["cagr_ev"] is None and m3["asym"] is None)
m4 = dp.compute_math(75, {"low": {"price": 25, "prob": 80},
                          "base": {"price": 105, "prob": 0},
                          "high": {"price": 210, "prob": 60}})
check("prob>100 -> base_prob=0 (nie ujemne)", m4["base_prob"] == 0)
m5 = dp.compute_math(75, {"low": {"price": None, "prob": 30},
                          "base": {"price": 105, "prob": 45},
                          "high": {"price": 210, "prob": 25}})
check("brak ceny scenariusza -> ev None", m5["ev"] is None)

# ---------------- eval_gate ----------------
row = {"price": 75, "combined": 70, "market_cap": 40e9}
gate = dp.eval_gate(row, m, {}, {})
by_id = {g["id"]: g["status"] for g in gate}
check("fisher 70/100 -> ok", by_id["fisher"] == "ok")
check("asym 2.7 + EV>kurs -> ok", by_id["asym"] == "ok")
check("cagr_base ~11.9% -> fail (<12%)", by_id["cagr"] == "fail",
      f"cagr_base={m['cagr_base']:.4f}")
check("liquidity 40 mld -> ok", by_id["liquidity"] == "ok")
check("variant bez AI -> borderline", by_id["variant"] == "borderline")

# nadpisanie uzytkownika wygrywa nad AI dla variant
gate2 = dp.eval_gate(row, m, {"variant": {"status": "ok", "info": "ai"}},
                     {"variant": {"status": "fail", "info": "moje"}})
check("override zastepuje AI", {g["id"]: g for g in gate2}["variant"]["status"] == "fail")

# gorszy z auto vs AI dla policzalnych
gate3 = dp.eval_gate(row, m, {"fisher": {"status": "fail", "info": "pozew"}}, {})
check("fisher: gorszy z auto(ok) i AI(fail) = fail",
      {g["id"]: g for g in gate3}["fisher"]["status"] == "fail")

# ---------------- final_verdict ----------------
def mk(**st_by_id):
    base = {gid: "ok" for gid in dp.GATE_ORDER}
    base.update(st_by_id)
    return [{"id": gid, "status": s} for gid, s in base.items()]

check("kill zlamane -> WYJDZ",
      dp.final_verdict(mk(), 2)["level"] == "red")
check("6x ok -> POZYCJA OK (zielony)",
      dp.final_verdict(mk(), 0)["label"] == "POZYCJA OK")
check("borderline jakosc -> pol pozycji (bursztyn)",
      "pol pozycji" in dp.final_verdict(mk(variant="borderline"), 0)["label"])
check("math ok, jakosc fail -> SPEKULACJA",
      "SPEKULACJA" in dp.final_verdict(mk(fisher="fail"), 0)["label"])
check("math fail -> NIE KUPUJ",
      "NIE KUPUJ" in dp.final_verdict(mk(asym="fail"), 0)["label"])

# ---------------- mechanical_baseline ----------------
mb = dp.mechanical_baseline({"price": 100, "target_mean": 150,
                             "next_earnings_date": "2026-08-06"})
# target_mean to konsensus 12-miesieczny; baza scenariuszy jest 3-letnia, wiec
# 1-roczna stopa (150/100-1=50%) jest kapitalizowana na 3 lata: 100*1.5**3=337.5
check("base = konsensus skapitalizowany na 3 lata", mb["scenarios"]["base"]["price"] == 337.5)
check("high = base*1.6", mb["scenarios"]["high"]["price"] == 540.0)
check("low = max(0.3*price, base*0.45), capped na price",
      mb["scenarios"]["low"]["price"] == 100.0)  # 0.45*337.5=151.9 > price -> capped
check("timeline z data raportu", mb["timeline"][0]["date"] == "2026-08-06")
mb2 = dp.mechanical_baseline({"price": None, "target_mean": None})
check("brak danych -> puste scenariusze", mb2["scenarios"] == {})

# ---------------- _validate: zepsuty JSON z modelu ----------------
bad = {
    "scenarios": {"low": {"price": "210", "prob": "70"},       # str + odwrocone ceny
                  "base": {"price": 105, "prob": 45},
                  "high": {"price": 25, "prob": 60}},           # low+high>100
    "gate": [{"id": "fisher", "status": "great", "info": "x"},  # zly status
             {"id": "nieznany", "status": "ok"},                 # zly id
             {"id": "variant", "status": "fail", "info": "y"}],
    "kill": ["a", "", "b"] + [f"k{i}" for i in range(10)],       # pusty + za duzo
    "timeline": [{"date": "Sie 2026", "title": "Raport", "type": "hmm"},
                 {"title": ""}],                                  # zly typ, pusty tytul
    "verdict_hint": 123,
}
v = dp._validate(bad, {"price": 75, "target_mean": 100})
sc = v["scenarios"]
check("ceny posortowane low<base<high",
      sc["low"]["price"] < sc["base"]["price"] < sc["high"]["price"])
check("prob przeskalowane do sumy<=100",
      sc["low"]["prob"] + sc["high"]["prob"] <= 100 and sc["base"]["prob"] >= 0)
check("zly status -> borderline",
      [g for g in v["gate"] if g["id"] == "fisher"][0]["status"] == "borderline")
check("zly id odfiltrowany", all(g["id"] in dp.GATE_LABELS for g in v["gate"]))
check("kill: puste usuniete, max 8", len(v["kill"]) == 8 and "" not in v["kill"])
check("timeline: zly typ -> minus, pusty tytul odfiltrowany",
      len(v["timeline"]) == 1 and v["timeline"][0]["type"] == "minus")

# calkowicie zepsuty JSON -> fallback mechaniczny
v2 = dp._validate({}, {"price": 75, "target_mean": 100})
# konsensus 100/75-1=33.3%/rok skapitalizowany na 3 lata: 75*(100/75)**3=177.78
check("pusty JSON -> scenariusze z fallbacku", v2["scenarios"]["base"]["price"] == 177.78)

# ---------------- _merge ----------------
mrg = dp._merge({"scenarios": {"low": 1}, "kill": ["a"], "timeline": [1]},
                {"kill": ["b", "c"]})
check("merge: user nadpisuje kill, reszta z bazy",
      mrg["kill"] == ["b", "c"] and mrg["scenarios"] == {"low": 1})

print()
if FAILS:
    print(f"BLEDY: {len(FAILS)} -> {FAILS}")
    raise SystemExit(1)
print("Wszystkie testy czystych funkcji przeszly.")

# ---------------- headless render panelu w izolacji (bez sieci) ----------------
print("\n=== AppTest: panel decyzyjny w izolacji (syntetyczny wiersz) ===")
from streamlit.testing.v1 import AppTest


def _panel_app():
    """Mini-aplikacja: sam panel decyzyjny na sztucznych danych (bez Yahoo)."""
    import streamlit as st
    import decision_panel
    st.set_page_config(layout="wide")
    row = {"ticker": "TST", "name": "Test SA", "market": "GPW",
           "currency": "PLN", "price": 75.0, "market_cap": 40e9,
           "trailing_pe": 18.0, "debt_to_equity": 0.5, "sector": "Tech",
           "target_mean": 105.0, "target_upside": 0.4, "analyst_count": 5,
           "combined": 70.0, "score": 70.0, "quality": None,
           "next_earnings_date": "2099-08-06"}
    wl = st.session_state.setdefault("wl", {"lists": {}, "notes": {}})
    decision_panel.render("TST", row, wl, lambda: None)


at = AppTest.from_function(_panel_app, default_timeout=120)
at.run()
if at.exception:
    for e in at.exception:
        print("EXC:", e.value)
    raise SystemExit(1)
subheaders = [h.value for h in at.subheader]
check("sekcja 'Panel decyzyjny' obecna",
      any("Panel decyzyjny" in s for s in subheaders), str(subheaders))
sliders = {s.key: s for s in at.slider}
check("suwaki low/high obecne",
      "dp_TST_0_prob_low" in sliders and "dp_TST_0_prob_high" in sliders,
      f"slidery={list(sliders)}")
check("przyciski panelu obecne",
      any("dp_" in (b.key or "") for b in at.button),
      f"buttons={[b.key for b in at.button][:6]}")
check("metryki EV/CAGR/asymetria obecne",
      any("oczekiwana" in (m.label or "") for m in at.metric)
      and any("Asymetria" in (m.label or "") for m in at.metric),
      f"metryki={[m.label for m in at.metric]}")

# interakcja: ruch suwaka -> przeliczenie bez wyjatku
at.slider(key="dp_TST_0_prob_low").set_value(50)
at.run()
check("ruch suwaka nie wywala renderu", not at.exception)

# --- pelna aplikacja: regresja (pomijana, gdy brak dostepu do Yahoo) ---
print("\n=== AppTest: pelna aplikacja app.py (moze potrwac) ===")
at2 = AppTest.from_file("app.py", default_timeout=1200)
at2.run()
if at2.exception:
    for e in at2.exception:
        print("EXC:", e.value)
    raise SystemExit(1)
subs2 = [h.value for h in at2.subheader]
if any("Panel decyzyjny" in s for s in subs2):
    print("Pelna aplikacja: panel decyzyjny wyrenderowany.")
elif not at2.dataframe or getattr(at2.dataframe[0].value, "empty", True):
    print("POMINIETO asercje panelu: ranking pusty (brak dostepu do Yahoo "
          "w tym srodowisku) — sekcja analizy spolki sie nie renderuje.")
else:
    check("panel decyzyjny w pelnej aplikacji", False, str(subs2))

print()
if FAILS:
    print(f"BLEDY: {len(FAILS)} -> {FAILS}")
    raise SystemExit(1)
print("Render OK — panel decyzyjny dziala.")

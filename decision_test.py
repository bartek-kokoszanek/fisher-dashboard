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
# horyzont 12M: zwrot okresowy = zwrot roczny, wiec bez anualizacji pierwiastkiem
check("Zwrot 12M (EV) = +43%", abs(m["cagr_ev"] - 0.43) < 0.0005,
      f"cagr_ev={m['cagr_ev']:.5f}")
check("asymetria 2.7:1", abs(m["asym"] - 2.7) < 1e-9, f"asym={m['asym']}")
check("base_prob dopelnia do 100", m["base_prob"] == 45)
check("low_pct = -66.7% (25 vs kurs 75)", abs(m["low_pct"] + 2 / 3) < 1e-9,
      f"low_pct={m['low_pct']}")

# guardy
m2 = dp.compute_math(20, scen)  # kurs ponizej low -> asym n/d
check("kurs<=low -> asym None", m2["asym"] is None)
m3 = dp.compute_math(None, scen)
check("price None -> ev liczone, reszta None",
      m3["ev"] is not None and m3["cagr_ev"] is None and m3["asym"] is None
      and m3["low_pct"] is None)
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
check("cagr_base 40% -> ok (>=15%)", by_id["cagr"] == "ok",
      f"cagr_base={m['cagr_base']:.4f}")
check("liquidity 40 mld -> ok", by_id["liquidity"] == "ok")
check("variant bez AI -> borderline", by_id["variant"] == "borderline")

# zwrot 12M ponizej progu -> cagr fail (base 80 vs kurs 75 = +6.7%)
m_slaby = dp.compute_math(75, {"low": {"price": 60, "prob": 25},
                               "base": {"price": 80, "prob": 50},
                               "high": {"price": 95, "prob": 25}})
check("cagr_base 6.7% -> fail (<12%)",
      {g["id"]: g["status"] for g in dp.eval_gate(row, m_slaby, {}, {})}["cagr"]
      == "fail", f"cagr_base={m_slaby['cagr_base']:.4f}")

# variant: auto-porownanie z konsensusem jest INFO, nie zmienia statusu
row_kons = dict(row, target_upside=0.11)   # konsensus +11% vs base +40%
g_var = {g["id"]: g for g in dp.eval_gate(row_kons, m, {}, {})}["variant"]
check("variant: info porownuje teze z konsensusem",
      "konsensus" in g_var["info"] and "odmienna teza" in g_var["info"],
      g_var["info"])
check("variant: status nadal jakosciowy (borderline)",
      g_var["status"] == "borderline")
g_zbiezny = {g["id"]: g for g in
             dp.eval_gate(dict(row, target_upside=0.38), m, {}, {})}["variant"]
check("variant: teza zbiezna z rynkiem -> brak przewagi",
      "brak przewagi" in g_zbiezny["info"], g_zbiezny["info"])

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

# guard obsuniecia: czysta bramka + gleboki dolek -> max pol pozycji
check("LOW -40% -> guard scina do pol pozycji",
      dp.final_verdict(mk(), 0, low_pct=-0.40)["level"] == "amber")
check("LOW -20% -> guard nie odpala",
      dp.final_verdict(mk(), 0, low_pct=-0.20)["label"] == "POZYCJA OK")
check("low_pct None -> zachowanie jak dawniej (kompatybilnosc)",
      dp.final_verdict(mk(), 0)["label"] == "POZYCJA OK")
check("guard nie PODNOSI werdyktu (math fail zostaje NIE KUPUJ)",
      "NIE KUPUJ" in dp.final_verdict(mk(asym="fail"), 0, low_pct=-0.05)["label"])

# ---------------- mechanical_baseline ----------------
mb = dp.mechanical_baseline({"price": 100, "target_mean": 150,
                             "next_earnings_date": "2026-08-06"})
# horyzont 12M: target_mean (cel 12-miesieczny) idzie do base 1:1, bez rzutowania
check("base = konsensus 1:1", mb["scenarios"]["base"]["price"] == 150.0)
check("high = base*1.25", mb["scenarios"]["high"]["price"] == 187.5)
check("low = kurs*0.75", mb["scenarios"]["low"]["price"] == 75.0)
check("baza mechaniczna oznaczona horyzontem",
      mb["horizon_months"] == dp.HORIZON_MONTHS)
check("timeline z data raportu", mb["timeline"][0]["date"] == "2026-08-06")
mb2 = dp.mechanical_baseline({"price": None, "target_mean": None})
check("brak danych -> puste scenariusze", mb2["scenarios"] == {})
# cel analitykow ponizej kursu -> low musi zostac ponizej base
mb3 = dp.mechanical_baseline({"price": 333.74, "target_mean": 318.25})
check("cel < kursu -> low < base < high",
      mb3["scenarios"]["low"]["price"] < mb3["scenarios"]["base"]["price"]
      < mb3["scenarios"]["high"]["price"],
      str({k: v["price"] for k, v in mb3["scenarios"].items()}))
mb4 = dp.mechanical_baseline({"price": 100, "target_mean": None})
check("brak konsensusu -> base = kurs*1.10", mb4["scenarios"]["base"]["price"] == 110.0)

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
check("pusty JSON -> scenariusze z fallbacku", v2["scenarios"]["base"]["price"] == 100.0)
check("wynik _validate oznaczony horyzontem",
      v2["horizon_months"] == dp.HORIZON_MONTHS)

# ---------------- migrate_horizon: stare bazy 3-letnie ----------------
row_m = {"price": 100}
stara = {"source": "ai", "scenarios": {
    "low": {"price": 64.0, "prob": 25}, "base": {"price": 337.5, "prob": 50},
    "high": {"price": 1000.0, "prob": 25}}}
mig = dp.migrate_horizon(stara, row_m)
# p12 = kurs * (p3/kurs)**(1/3): 337.5 -> 150.0, 1000 -> 215.44, 64 -> 86.18
# (scenariusz ponizej kursu podnosi sie ku kursowi - w 12 mies. jest blizej
#  dzisiejszej ceny niz w 3 lata, tak samo jak scenariusz powyzej opada)
check("migracja: base 337.5 (3L) -> 150.0 (12M)",
      mig["scenarios"]["base"]["price"] == 150.0,
      str(mig["scenarios"]["base"]["price"]))
check("migracja: high 1000 -> 215.44", mig["scenarios"]["high"]["price"] == 215.44)
check("migracja: low 64 -> 86.18", mig["scenarios"]["low"]["price"] == 86.18)
check("migracja oznacza horyzont i flage", mig["horizon_months"] == dp.HORIZON_MONTHS
      and mig["horizon_migrated"] is True)
check("migracja nie mutuje wejscia", stara["scenarios"]["base"]["price"] == 337.5)
check("migracja idempotentna (drugi przebieg nic nie zmienia)",
      dp.migrate_horizon(mig, row_m)["scenarios"]["base"]["price"] == 150.0)
check("brak ceny -> dict bez zmian",
      dp.migrate_horizon(stara, {"price": None})["scenarios"]["base"]["price"] == 337.5)
check("None -> None", dp.migrate_horizon(None, row_m) is None)

# ---------------- staleness_note ----------------
from datetime import date as _date, timedelta as _td
_dzis = _date.today()
swieza = {"source": "ai", "generated_at": _dzis.isoformat()}
check("swieza baza AI -> brak ostrzezenia",
      dp.staleness_note(swieza, {}) is None)
check("baza mechaniczna -> brak ostrzezenia",
      dp.staleness_note({"source": "mechanical"}, {}) is None)
stara_baza = {"source": "ai",
              "generated_at": (_dzis - _td(days=dp.STALE_DAYS + 10)).isoformat()}
check("baza >90 dni -> ostrzezenie o wieku",
      "dni" in (dp.staleness_note(stara_baza, {}) or ""))
check("raport kwartalny po generacji -> ostrzezenie",
      "raport kwartalny" in (dp.staleness_note(
          swieza, {"last_q_date": (_dzis + _td(days=1)).isoformat()}) or ""))
check("raport sprzed generacji -> brak ostrzezenia",
      dp.staleness_note(swieza,
                        {"last_q_date": (_dzis - _td(days=30)).isoformat()}) is None)
check("zepsuta data generacji -> brak wyjatku",
      dp.staleness_note({"source": "ai", "generated_at": "kiedys"}, {}) is None)

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

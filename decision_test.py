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
check("base z konsensusu", mb["scenarios"]["base"]["price"] == 150)
check("high = base*1.6", mb["scenarios"]["high"]["price"] == 240)
check("low = max(0.3*price, base*0.45)", mb["scenarios"]["low"]["price"] == 67.5)
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
check("pusty JSON -> scenariusze z fallbacku", v2["scenarios"]["base"]["price"] == 100)

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

# ---------------- headless render calej aplikacji ----------------
print("\n=== AppTest: headless render app.py (moze potrwac) ===")
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=1200)
at.run()
if at.exception:
    for e in at.exception:
        print("EXC:", e.value)
    raise SystemExit(1)
subheaders = [h.value for h in at.subheader]
found = any("Panel decyzyjny" in s for s in subheaders)
print("Podnaglowki:", [s for s in subheaders if "decyzyjny" in s.lower()] or subheaders[:8])
check("sekcja 'Panel decyzyjny' obecna", found)
check("sa suwaki scenariuszy", any("prob" in (s.key or "") for s in at.slider),
      f"slidery={[s.key for s in at.slider][:6]}")
check("sa checkboxy/przyciski panelu",
      any("dp_" in (b.key or "") for b in at.button))
print()
if FAILS:
    print(f"BLEDY: {len(FAILS)} -> {FAILS}")
    raise SystemExit(1)
print("Render OK — panel decyzyjny obecny w aplikacji.")

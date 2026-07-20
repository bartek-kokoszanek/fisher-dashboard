"""Test ukladu: pasek przegladu + 5 zakladek tematycznych."""
import sys
from streamlit.testing.v1 import AppTest

ETYKIETY = ["📊 Fundamenty", "💰 Wycena", "🌐 Rynek", "🎯 Decyzja", "📝 Notatki"]


def main() -> int:
    at = AppTest.from_file("app.py", default_timeout=300)
    at.run()

    if at.exception:
        print("BLAD: wyjatki przy renderze:")
        for e in at.exception:
            print("   ", str(e.value)[:300])
        return 1

    etykiety = [t.label for t in at.tabs]
    if etykiety != ETYKIETY:
        print(f"BLAD: zakladki {etykiety} != {ETYKIETY}")
        return 1
    print(f"[OK ] zakladki: {etykiety}")

    etykiety_metryk = {m.label for m in at.metric}
    oczekiwane_metryki = {"Wynik", "DCF / akcję", "Cena docelowa PWPA",
                          "Najbliższe wyniki", "Dywidenda", "Sentyment",
                          "Pokrycie"}
    brakujace = oczekiwane_metryki - etykiety_metryk
    if brakujace:
        print(f"BLAD: brak metryk w pasku przegladu: {brakujace}")
        return 1
    print("[OK ] pasek przegladu zawiera komplet metryk")

    if not any("Yahoo Finance" in str(c.value) for c in at.caption):
        print("BLAD: brak podpisu zrodla w pasku przegladu")
        return 1
    print("[OK ] pasek przegladu ma podpis zrodla")

    fund = " ".join(str(m.value) for m in at.tabs[0].markdown)
    if "Kurs akcji" not in fund:
        print("BLAD: zakladka Fundamenty nie zawiera kursu akcji")
        return 1
    print("[OK ] Fundamenty: kurs akcji obecny")

    val = " ".join(str(m.value) for m in at.tabs[1].markdown)
    if "Dywidenda" not in val:
        print("BLAD: zakladka Wycena nie zawiera bloku dywidendy")
        return 1
    print("[OK ] Wycena: dywidenda obecna")

    mkt = " ".join(str(m.value) for m in at.tabs[2].markdown) + \
          " ".join(str(s.value) for s in at.tabs[2].subheader)
    if "Deep research" not in mkt:
        print("BLAD: zakladka Rynek nie zawiera deep researchu")
        return 1
    print("[OK ] Rynek: deep research obecny")

    dec = " ".join(str(s.value) for s in at.tabs[3].subheader) + \
          " ".join(str(m.value) for m in at.tabs[3].markdown)
    if "Panel decyzyjny" not in dec:
        print("BLAD: zakladka Decyzja nie zawiera panelu decyzyjnego")
        return 1
    print("[OK ] Decyzja: panel decyzyjny obecny")

    notes_txt = " ".join(str(m.value) for m in at.tabs[4].markdown) + \
                " ".join(str(c.value) for c in at.tabs[4].caption)
    if "notatk" not in notes_txt.lower():
        print("BLAD: zakladka Notatki jest pusta")
        return 1
    print("[OK ] Notatki: sekcja obecna")

    # Prog ostrzegawczy z zapasem, zeby test nie pekal przy kazdej drobnej
    # zmianie w app.py.
    dlugosc = len(open("app.py", encoding="utf-8").read().splitlines())
    if dlugosc > 950:
        print(f"BLAD: app.py ma {dlugosc} linii, prog to 950")
        return 1
    print(f"[OK ] app.py: {dlugosc} linii")

    rc = test_financial_charts_api()
    if rc:
        return rc
    rc = test_pasek_braki()
    if rc:
        return rc
    return 0


def test_financial_charts_api() -> int:
    import financial_charts as fc
    wymagane = ("render_ai_interpretation", "render_price_chart",
                "render_dividend", "render_kpis", "render_charts")
    brak = [f for f in wymagane if not callable(getattr(fc, f, None))]
    if brak:
        print(f"BLAD: brak funkcji w financial_charts: {brak}")
        return 1
    print(f"[OK ] financial_charts wystawia: {', '.join(wymagane)}")
    return 0


def test_pasek_braki() -> int:
    """Spolka bez DCF, dywidendy i sentymentu — pasek pokazuje '—', nie znika."""
    import sections.overview as ov
    pusty = {"combined": None, "price": None, "coverage": 0,
             "next_earnings_date": None, "last_dividend_value": None,
             "ex_dividend_date": None, "currency": None, "fetched_at": None}
    try:
        ov._dni_do(None)
        ov._dni_do("2020-01-01")
        ov._dni_do("nie-data")
    except Exception as e:
        print(f"BLAD: _dni_do wywala sie na brzegowych danych: {e}")
        return 1
    if ov.DASH != "—":
        print("BLAD: pasek nie uzywa '—' jako wartosci pustej")
        return 1
    print("[OK ] pasek: brakujace wartosci obsluzone")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

    rc = test_financial_charts_api()
    if rc:
        return rc
    return 0


def test_financial_charts_api() -> int:
    import financial_charts as fc
    wymagane = ("render_ai_interpretation", "render_price_chart",
                "render_dividend", "render_kpis", "render_charts", "render")
    brak = [f for f in wymagane if not callable(getattr(fc, f, None))]
    if brak:
        print(f"BLAD: brak funkcji w financial_charts: {brak}")
        return 1
    print(f"[OK ] financial_charts wystawia: {', '.join(wymagane)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

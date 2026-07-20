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

    teksty = " ".join(str(m.value) for m in at.markdown)
    for pole in ("Wynik", "DCF", "PWPA", "Dywidenda", "Pokrycie"):
        if pole not in teksty:
            print(f"BLAD: brak pola '{pole}' w pasku przegladu")
            return 1
    print("[OK ] pasek przegladu zawiera komplet pol")
    return 0


if __name__ == "__main__":
    sys.exit(main())

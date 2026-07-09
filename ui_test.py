"""Headless render test dashboardu przez Streamlit AppTest.

Wykonuje app.py w symulowanym runtime (bez przegladarki), sprawdza brak
wyjatkow i obecnosc kluczowych elementow UI (tytul, tabela rankingu, przyciski).
"""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=1200)
at.run()

print("=== Wyjatki ===")
if at.exception:
    for e in at.exception:
        print("EXC:", e.value)
else:
    print("brak — render OK")

titles = [t.value for t in at.title]
headers = [h.value for h in at.header]
print("\nTytuly:", titles)
print("Naglowki:", headers)
print("Liczba dataframe:", len(at.dataframe))
if at.dataframe:
    df = at.dataframe[0].value
    print("Wymiary tabeli rankingu:", df.shape)
    print("Kolumny:", list(df.columns))
    top = df.sort_values("Wynik", ascending=False).head(5)
    print("\nTop 5 rankingu:")
    for _, r in top.iterrows():
        print(f"  {r['Symbol']:8} {str(r['Spolka'])[:22]:22} {str(r['Segment']):9} "
              f"wynik={r['Wynik']}  cel%={r['Do celu %']}  rekom={r['Rekom.']}")
print("\nPrzyciski download:", len(at.button) + len([b for b in getattr(at, 'download_button', [])]))
print("Selectboxy:", len(at.selectbox))
print("Multiselecty:", len(at.multiselect))

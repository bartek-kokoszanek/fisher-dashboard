# Układ modułów: przypięty pasek przeglądu + zakładki tematyczne

Data: 2026-07-20
Status: zaakceptowany, do wdrożenia

## Problem

Analiza spółki to dziś jedna strona z 20 sekcjami renderowanymi po kolei
w `app.py` (1084 linie). Aplikacja obsługuje dwa tryby pracy o sprzecznych
potrzebach:

- **research nowej spółki** — czytanie wszystkiego po kolei, od ogółu do
  szczegółu, płynna narracja;
- **monitoring znanych spółek** — szybka odpowiedź na pytanie „co się
  zmieniło", bez przewijania całości.

Jedna długa strona obsługuje oba średnio: monitoring musi scrollować przez
15 wykresów, a research traci kluczowe liczby z oczu, gdy tylko zjedzie
niżej (żeby porównać wykres z wynikiem, trzeba wracać na górę).

## Rozwiązanie

**Przypięty pasek przeglądu nad zakładkami tematycznymi.**

Pasek jest zawsze widoczny — monitoring dostaje odpowiedź bez jednego
kliknięcia, a research ma kluczowe liczby stale na oczach podczas czytania
każdej zakładki. To jedyny rozważany wariant, w którym oba tryby nie walczą
o to samo miejsce na ekranie.

Odrzucone warianty:
- *zakładki wg pytania inwestora, z „Przeglądem" jako pierwszą zakładką* —
  monitoring i tak musi kliknąć, a Przegląd konkuruje o uwagę z resztą;
- *zakładki wg źródła danych (liczby / AI / rynek)* — sztucznie rozdziela
  rzeczy czytane razem, np. marże i interpretację marż.

## Układ

Bez zmian zostaje wszystko nad analizą spółki: panel boczny, tabela rankingu
z ustawieniami i przyciskiem PWPA, eksport CSV, wyszukiwarka i przypisanie
spółki do list.

### Pasek przeglądu (przypięty)

Jeden rząd zwartych metryk:

| Pole | Źródło |
|---|---|
| Wynik łączny + sygnał | `fisher_score` + `action_verdict` |
| Wycena DCF na akcję + delta vs cena | `financial_charts.dcf_per_share` |
| Cena docelowa PWPA + data | `pwpa_targets` |
| Najbliższe wyniki (data + ile dni) | `row["next_earnings_date"]` |
| Dywidenda: ex-date + kwota | `row["ex_dividend_date"]`, `last_dividend_value` |
| Sentyment rynku | `research_deep.load_cached` |
| Pokrycie danych | `row["coverage"]` |

Pod paskiem jedna linia: źródło i data aktualizacji.

**Puste wartości pokazują `—`, kolumna nigdy nie znika** — inaczej układ
skakałby przy przełączaniu spółek.

### Zakładki

| Zakładka | Zawartość |
|---|---|
| `📊 Fundamenty` | kurs akcji z nakładkami · rozbicie ilościowe (subscore) · KPI · 15 wykresów |
| `💰 Wycena` | interpretacja AI (Financial Quality + DCF + wycena) · dywidenda ze szczegółami i historią · raporty PWPA z linkami do PDF |
| `🌐 Rynek` | deep research (sentyment, newsy, IR) · analiza wideo |
| `🎯 Decyzja` | ocena jakościowa AI (5 wymiarów) · zalety i wady · panel decyzyjny (scenariusze, bramka, kill criteria, oś czasu) |
| `📝 Notatki` | notatki użytkownika, z adnotacją, że zasilają interpretację AI w zakładce Wycena |

Dwie przeprowadzki względem stanu obecnego:

1. **Dywidenda** wychodzi z Financial Charts do `Wycena` — jest składnikiem
   stopy zwrotu, nie fundamentem operacyjnym. Skrót zostaje w pasku.
2. **Ocena jakościowa AI i zalety/wady** trafiają do `Decyzja`, nie do
   fundamentów — to one karmią jakościowe warunki bramki („wariant",
   „katalizator"), więc stoją najbliżej werdyktu.

## Architektura

`app.py` schodzi z 1084 do ~350 linii: panel boczny, wczytanie danych,
ranking, wybór spółki, złożenie zakładek. Reszta trafia do nowego pakietu:

```
sections/overview.py      # pasek przeglądu
sections/fundamentals.py  # kurs, subscore, KPI, 15 wykresów
sections/valuation.py     # interpretacja AI, dywidenda, PWPA
sections/market.py        # deep research, wideo
sections/decision.py      # ocena jakościowa, zalety/wady, panel decyzyjny
sections/notes.py         # notatki
```

Moduły domenowe (`financial_charts`, `decision_panel`, `research_deep`,
`pwpa`, `pwpa_targets`, `charts/`) zostają bez zmian w odpowiedzialności —
`sections/*` tylko je układa na ekranie.

Każda sekcja ma jedno wejście: `render(ticker, row, wl, save_wl)`, i sama
dociąga to, czego potrzebuje. Dzięki temu da się ją zrozumieć i przetestować
bez czytania pozostałych.

### Wymuszona zmiana w `financial_charts.py`

Dziś `render()` robi w jednym ciągu: interpretację AI → kurs → dywidendę →
KPI → 15 wykresów. Te części trafiają do **dwóch różnych zakładek**, więc
monolit trzeba rozbić na osobne funkcje:

- `render_ai_interpretation(ticker, row, hist, notes)` → Wycena
- `render_price_chart(ticker, row, hist)` → Fundamenty
- `render_dividend(ticker, row, hist)` → Wycena (dziś prywatne `_render_dividend`)
- `render_kpis(hist, row)` → Fundamenty
- `render_charts(hist, row)` → Fundamenty

Ciała funkcji przenoszone bez przepisywania logiki.

## Przepływ danych

Historia finansowa idzie przez istniejący `_hist()` z `st.cache_data`, więc
pięć zakładek nie oznacza pięciu pobrań — pierwsza zakładka liczy, reszta
trafia w cache.

Ceny docelowe PWPA czytane są z gotowych wyników (`pwpa_targets.load()`);
ekstrakcja PDF przez AI pozostaje wyłącznie pod przyciskiem nad tabelą.

## Wydajność — świadome ograniczenie

`st.tabs` renderuje **wszystkie** zakładki przy każdym przeładowaniu, nie
tylko aktywną. To nie jest regres (dziś jedna długa strona też liczy
wszystko), ale zakładki tego problemu **nie rozwiązują**. Jeśli render
zacznie zamulać, trzeba będzie osobno opakować ciężkie sekcje w
`st.fragment` — świadomie poza zakresem tej zmiany.

## Obsługa błędów i braków danych

Zachowanie, które już działa, zostaje bez zmian: brak danych to komunikat,
nie wyjątek; brak klucza AI to podpowiedź zamiast pustego miejsca; PWPA,
deep research i analiza wideo są fail-soft.

Nowość dotyczy wyłącznie paska przeglądu: brak wartości pokazuje `—`,
a kolumna nigdy nie znika.

## Testy

- `ui_test.py` — rozszerzyć o sprawdzenie, że renderuje się każda z pięciu
  zakładek;
- pasek przeglądu — sprawdzić komplet metryk dla spółki z pełnymi danymi
  (np. AAPL) i `—` dla spółki ubogiej w dane;
- `decision_test.py` — panel decyzyjny nadal działa po przeniesieniu do
  `sections/decision.py`;
- refaktor idzie etapami: po każdym przeniesieniu sekcji uruchamiany jest
  render, żeby nie zgubić czegoś po drodze.

## Ryzyko

To największa zmiana strukturalna w tej aplikacji. Ograniczenie ryzyka:
przenosiny kodu bez przepisywania logiki i weryfikacja po każdym kroku.
Gdyby coś się urwało, prostszym wyjściem jest rewert całego PR-a niż
punktowe łatanie.

# Fisher Dashboard — typowanie spółek Nasdaq + GPW

Dashboard do rankingowania spółek według 15 zasad **Philipa Fishera**
(*Common Stocks and Uncommon Profits*). Łączy mierzalne proxy fundamentalne
z jakościową oceną AI (Claude).

> ⚠️ Narzędzie edukacyjne — **nie stanowi porady inwestycyjnej**.

---

## Dlaczego nie TradingView?

TradingView **nie udostępnia oficjalnego API** dla kont osobistych — nie da się
„podłączyć" do niego skryptu, żeby pobierał dane czy typował spółki. Dlatego dane
fundamentalne pochodzą z **Yahoo Finance** (biblioteka `yfinance`), darmowo, dla obu
giełd. TradingView używasz na końcu: eksportujesz ranking jako listę tickerów i
importujesz do watchlisty, żeby oglądać wykresy (patrz niżej).

---

## Jak metoda Fishera trafia do liczb

~70% zasad Fishera jest **jakościowych** (jakość zarządu, kultura R&D, uczciwość).
Tego nie ma w danych finansowych, więc dzielimy ocenę na dwie warstwy:

**Warstwa ilościowa** (`fisher_score.py`) — 10 mierzalnych proxy, każde skalowane 0–100
i ważone (suma wag = 100):

| Metryka | Punkt Fishera | Waga |
|---|---|---|
| Wzrost sprzedaży (CAGR) | 1 | 18 |
| Dynamika r/r | 1 | 10 |
| Marża brutto | 5 | 8 |
| Marża operacyjna | 5 | 12 |
| Trend marży | 6 | 10 |
| Nacisk na R&D (R&D/przychody) | 2, 3 | 12 |
| ROE | 11 | 12 |
| Marża FCF | — | 10 |
| Brak rozwodnienia akcji | 13 | 4 |
| Niskie zadłużenie (D/E) | 13 | 4 |

**Warstwa jakościowa** (`ai_research.py`) — Claude ocenia 5 wymiarów, których nie widać
w liczbach: jakość zarządu, uczciwość/szczerość, fosa konkurencyjna, kultura innowacji,
horyzont długoterminowy.

**Wynik łączny** = 70% ilościowy + 30% jakościowy (jeśli zrobiłeś research AI dla spółki).
Pole **Pokrycie %** mówi, jaki procent wag udało się policzyć — niższe = mniej pewny wynik
(typowe dla mniejszych spółek GPW i banków).

---

## Uruchomienie

Wymaga Pythona 3.11+. W tym repo jest już gotowe wirtualne środowisko `.venv`.

```powershell
cd C:\Users\Bartek\Desktop\Claude\fisher-dashboard
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Otwórz http://localhost:8501. Pierwsze załadowanie pobiera fundamenty z Yahoo
(kilkadziesiąt spółek — potrwa ~1–2 min); potem dane są cache'owane w `data/` na 24h.
Przycisk **🔄 Odśwież dane** wymusza ponowne pobranie.

Gdyby `.venv` nie działało, odtwórz je:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Research AI (opcjonalny, warstwa jakościowa)

Ustaw klucz API Anthropic **przed** uruchomieniem:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
.\.venv\Scripts\python.exe -m streamlit run app.py
```

W panelu **Analiza spółki** kliknij *🤖 Uruchom research AI* — Claude oceni wymiary
jakościowe i podbije/obniży wynik łączny. Wyniki cache'owane w `data/ai_<ticker>.json`.
Domyślny model to `claude-haiku-4-5` (tani); zmienisz przez `FISHER_AI_MODEL`.
Checkbox *Użyj wyszukiwania w sieci* włącza świeższe dane (droższe).

---

## Dostosowanie

- **Dodać/usunąć spółki** → edytuj listy `NASDAQ` i `GPW` w [config.py](config.py).
  Nasdaq: sam symbol (`AAPL`). GPW: symbol + `.WA` (`PKN.WA`). Banki/ubezpieczycieli
  dopisz do zbioru `FINANCIALS`, żeby nie karać ich za brak R&D i marży brutto.
- **Zmienić wagi metryk** → `WEIGHTS` w [config.py](config.py) (suma powinna dać 100).
- **Dostroić progi punktacji** → `SCORERS` w [fisher_score.py](fisher_score.py).
  Domyślnie nastawione pod spółki wzrostowe.

---

## Eksport do TradingView

Pod tabelą rankingu jest **⬇ Eksport watchlisty**. Pobierze plik `.txt` z tickerami.
W TradingView: *Watchlist → menu (…) → Import list* i wklej zawartość.

Uwaga: GPW w TradingView bywa pod prefiksem giełdy, np. `GPW:PKN` zamiast `PKN.WA`.
Jeśli import nie rozpozna symboli, dodaj prefiks `GPW:` (dla warszawskich) ręcznie.

---

## Struktura

```
fisher-dashboard/
├── app.py            # dashboard Streamlit (UI)
├── config.py         # uniwersum spółek + wagi
├── data_fetch.py     # pobieranie fundamentów (yfinance) + cache
├── fisher_score.py   # scoring ilościowy 0–100
├── ai_research.py    # jakościowa ocena AI (Anthropic API)
├── smoke_test.py     # szybki test warstwy danych/scoringu
├── ui_test.py        # headless render-test (Streamlit AppTest)
├── requirements.txt
└── data/             # cache (tworzony automatycznie)
```

---

## Znane ograniczenia

- yfinance bywa niestabilny (rate-limit, puste sprawozdania małych spółek GPW).
  Kod pomija błędne tickery i pokazuje `Pokrycie %` — niskie pokrycie to nie błąd.
- Dane fundamentalne mają opóźnienie (raportowanie kwartalne/roczne).
- Progi scoringu są subiektywne — dostrój je do swojej strategii.

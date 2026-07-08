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

Domyślnie używa **darmowego Google Gemini**. Wygeneruj darmowy klucz (bez karty)
na [aistudio.google.com/apikey](https://aistudio.google.com/apikey) i ustaw go **przed**
uruchomieniem:

```powershell
$env:GEMINI_API_KEY = "..."
.\.venv\Scripts\python.exe -m streamlit run app.py
```

W panelu **Analiza spółki** kliknij *🤖 Uruchom research AI* — model oceni wymiary
jakościowe (zarząd, fosa, R&D, uczciwość) i podbije/obniży wynik łączny. Wyniki
cache'owane w `data/ai_<ticker>.json`.

**Inny provider.** Kod używa klienta OpenAI, więc zadziała z dowolnym API zgodnym z
OpenAI. Przekieruj go zmiennymi środowiskowymi:
- `LLM_BASE_URL` — endpoint (domyślnie Gemini)
- `LLM_MODEL` — id modelu (domyślnie `gemini-flash-latest`)
- `GEMINI_API_KEY` lub `LLM_API_KEY` — klucz

Np. dla darmowego Groq: `LLM_BASE_URL="https://api.groq.com/openai/v1"`,
`LLM_MODEL="llama-3.3-70b-versatile"`, `LLM_API_KEY="gsk_..."`.

---

## Deep research (sentyment + YouTube + relacje inwestorskie)

Przycisk **🔎 Deep research** w panelu analizy bada ostatnie ~6 miesięcy:

- **Sentyment rynku** — Gemini z narzędziem Google Search (grounding, w darmowym
  tierze) przeszukuje świeże artykuły i ocenia sentyment w skali −100…+100.
- **YouTube** — `yt-dlp` znajduje filmy o spółce (tytuł, kanał, data), a dla
  najnowszych próbuje pobrać transkrypty. ⚠️ Na serwerach chmurowych YouTube
  często blokuje transkrypty — wtedy analiza opiera się na tytułach i wyszukiwarce.
  Model **nie ogląda filmów** — czyta transkrypty/metadane.
- **Relacje inwestorskie** — grounding szuka raportów na stronie IR spółki.

Sentyment **nie wpływa** na Wynik Fishera (to zjawisko krótkoterminowe) — jest
wyświetlany osobno. Wyniki cache w `data/deep_<ticker>.json`. Wymaga `GEMINI_API_KEY`;
model przez `DEEP_MODEL` (domyślnie `gemini-flash-latest`).

---

## Wyszukiwarka spółek

Pole **🔍 Wyszukaj** w sekcji analizy obejmuje pełną pulę: ~5500 spółek Nasdaq
(oficjalny katalog nasdaqtrader.com, odświeżany co 7 dni) i ~370 spółek GPW
(lista w [gpw_tickers.py](gpw_tickers.py)). Wybrana spółka jest pobierana
i punktowana na żądanie, dołącza do rankingu w bieżącej sesji.

---

## Listy obserwacyjne

W panelu bocznym tworzysz własne listy (np. *Mój portfel*, *Do kupienia*),
dodajesz/usuwasz spółki z poziomu analizy i filtrujesz ranking po liście.

**Trwały zapis:** na Streamlit Cloud dysk jest ulotny — żeby listy przeżyły
restarty, dodaj w Secrets `GITHUB_TOKEN` (token ze scope **gist**) i `GIST_ID`
(patrz [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)).
Bez tego listy działają, ale znikają przy redeployu; w panelu jest też
eksport/import JSON jako ręczny backup.

---

## Kolumny analityków w rankingu

Tabela pokazuje obok wyniku Fishera: cenę, **średnią cenę docelową** analityków,
**% do celu** (kolorowany), **liczbę rekomendacji**, ocenę konsensusu
(1 = Strong Buy … 5 = Sell), C/Z i kapitalizację. Źródło: Yahoo Finance;
dla części spółek GPW konsensus jest niedostępny (puste pola).

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
├── config.py         # bazowe uniwersum spółek + wagi
├── data_fetch.py     # pobieranie fundamentów + analitycy (yfinance) + cache
├── fisher_score.py   # scoring ilościowy 0–100
├── ai_research.py    # szybka ocena jakościowa AI (Gemini / OpenAI-compatible)
├── research_deep.py  # deep research: sentyment + YouTube + IR (Gemini grounding)
├── universe.py       # pełna pula symboli Nasdaq+GPW (wyszukiwarka)
├── gpw_tickers.py    # lista spółek GPW (generowana)
├── watchlists.py     # listy obserwacyjne (GitHub Gist / plik lokalny)
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

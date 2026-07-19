# Dashboard inwestora — typowanie spółek Nasdaq + GPW

Dashboard rankingujący spółki według wybranej **strategii znanego inwestora**
(8 profili: Fisher, Lynch, Burry, Buffett, Dalio, Simons, Ackman, Soros).
Łączy mierzalne proxy fundamentalne z jakościową oceną AI.

> ⚠️ Narzędzie edukacyjne — **nie stanowi porady inwestycyjnej**.
> Strategie to przybliżenia filozofii inwestorów, nie ich prawdziwe algorytmy.

---

## Strategie inwestorów

Przełącznik **🧭 Strategia inwestora** w panelu bocznym zmienia wagi metryk
w scoringu ilościowym oraz „osobowość" researchu AI. Profile w [gurus.py](gurus.py)
(edytowalne — każdy to wagi sumujące się do 100 + prompt):

| Strategia | Akcent |
|---|---|
| Philip Fisher | wzrost sprzedaży, R&D, marże, jakość zarządu |
| Peter Lynch | wzrost w rozsądnej cenie (GARP), niskie C/Z przy wzroście |
| Michael Burry | głęboka wartość: tanio wg C/Z i FCF, twardy bilans |
| Warren Buffett | fosa, wysokie ROE bez długu, przewidywalne zyski |
| Ray Dalio | odporność: niski lewar, stabilne przepływy |
| James Simons* | momentum 6-mies. + dyscyplina liczb |
| Bill Ackman | skoncentrowane, proste biznesy z silnym FCF |
| George Soros* | momentum + zwroty nastrojów (refleksywność) |

\* Simons (quant/HFT) i Soros (makro) są z natury nieodtwarzalni z danych
fundamentalnych — te profile to świadome uproszczenia.

---

## Segmenty rynku

Filtr **Segment** w panelu bocznym: `Nasdaq`, `Nasdaq-AI` (kuratorowany
podzbiór ~36 spółek AI — edytuj w [gpw_indices.py](gpw_indices.py)), **`S&P500`**
(~500 spółek, lista w [sp500_tickers.py](sp500_tickers.py)), `WIG20`, `mWIG40`,
`sWIG80` oraz `WIG-pozostałe`. Domyślnie zaznaczone są indeksy GPW
(WIG20/mWIG40/sWIG80). Duże segmenty (`S&P500`, `WIG-pozostałe`) są **ładowane
leniwie** przy pierwszym wybraniu — pobranie ~500 spółek potrwa kilka minut,
potem działa z cache. Bazowe uniwersum = Nasdaq-24 + komplet WIG (~140 GPW).

Składy indeksów zmieniają się kwartalnie — wygenerowane 2026-07-09; aby
odświeżyć, uruchom ponownie generator (skrypt w historii projektu) lub popraw
listy ręcznie w `gpw_indices.py`.

---

## Dlaczego nie TradingView?

TradingView **nie udostępnia oficjalnego API** dla kont osobistych — nie da się
„podłączyć" do niego skryptu, żeby pobierał dane czy typował spółki. Dlatego dane
fundamentalne pochodzą z **Yahoo Finance** (biblioteka `yfinance`), darmowo, dla obu
giełd. TradingView używasz na końcu: eksportujesz ranking jako listę tickerów i
importujesz do watchlisty, żeby oglądać wykresy (patrz niżej).

### Źródła danych i świeżość

Wszędzie, gdzie dane są pobierane, aplikacja pokazuje **źródło + datę/godzinę
aktualizacji** (czas polski). Ceny na wykresie kursu można pobrać z niezależnego
źródła (selektor przy wykresie):

| Rynek | Źródła cen | Uwagi |
|---|---|---|
| GPW (.WA) | Yahoo Finance / **GPW (oficjalne)** | api wykresów gpw.pl (chart-json), bez klucza |
| Nasdaq/USA | Yahoo Finance / **Alpha Vantage** | darmowy klucz `ALPHAVANTAGE_API_KEY` w Secrets ([alphavantage.co](https://www.alphavantage.co/support/#api-key)), limit 25 zapytań/dobę |

Fundamenty (sprawozdania, prognozy analityków) mają tylko źródło Yahoo —
darmowej alternatywy brak. Stooq odpadł: od 2026 blokuje klientów HTTP
weryfikacją przeglądarki (JS challenge).

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

Otwórz http://localhost:8501. Pierwsze załadowanie pobiera fundamenty z Yahoo;
potem dane są cache'owane w `data/` na 24h. Przycisk **🔄 Odśwież dane** wymusza
ponowne pobranie.

**Szybkość pobierania.** Spółki pobierane są **równolegle** (yfinance robi ~10
zapytań HTTP na spółkę, więc wątki dają ~7× przyspieszenie: S&P500 ≈ 3 min
zamiast ~24 min). Liczbę wątków zmienisz zmienną `FETCH_WORKERS` (domyślnie 8;
przy 8–16 Yahoo nie odrzuca zapytań — sprawdzone).

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
jakościowe (zarząd, fosa, R&D, uczciwość) **przez pryzmat wybranej strategii**
i wypisze **Największe zalety** oraz **Największe wady i ryzyka** od myślników.
Wyniki cache'owane per strategia w `data/ai_<strategia>_<ticker>.json`.

**Limit darmowego Gemini:** przy przekroczeniu (błąd 429) aplikacja pokaże
czytelny komunikat i sama ponowi próbę po 20 s. Limit dzienny odnawia się
o północy czasu pacyficznego (~9:00 rano w Polsce). Grounding (deep research)
ma osobny, ciaśniejszy limit niż zwykłe zapytania.

**Wiele kluczy (rotacja).** Darmowe limity są per konto/projekt, więc możesz
podać klucze z kilku kont — gdy jeden wyczerpie limit, system automatycznie
przełącza się na następny. W Secrets: `GEMINI_API_KEYS = "klucz1,klucz2,klucz3"`
(albo `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`). W panelu bocznym widać liczbę
wykrytych kluczy. Rotacja nie omija limitów — sumuje niezależne pule.

**Rotacja modeli.** Każdy model Gemini ma **osobną** darmową pulę limitów
(np. Gemini 3.5 Flash ma tylko ~20 zapytań/dobę). Zamiast bić w jeden model,
system rotuje: domyślnie `gemini-flash-latest → gemini-2.5-flash →
gemini-2.5-flash-lite`. Przy błędzie 429 przechodzi do następnego modelu — więc
efektywna pojemność to **klucze × modele × ~20/dobę**. Kolejność/zestaw zmienisz
przez `LLM_MODELS = "model1,model2,..."` w Secrets. Grounding (deep research)
i transkrypcja audio używają tylko modeli Flash (bez Lite).

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

### Analiza wideo ([yt_transcribe.py](yt_transcribe.py))

Podsekcja **🎧 Analiza wideo (AI)**: wybierasz film z YouTube o spółce, a agent
wyciąga wnioski (kluczowe tezy, sentyment autora, ryzyka, cytaty). Kolejność:
najpierw **napisy** (szybkie i tanie); gdy ich brak — URL filmu trafia do
**Gemini, który ogląda/odsłuchuje film po stronie Google** (video
understanding). To rozwiązuje dawny problem blokady IP: nasz serwer nie pobiera
nic z YouTube, więc działa też na Streamlit Cloud bez proxy.

**Lista filmów**: przy ustawionym `YOUTUBE_API_KEY` (darmowy klucz w Google
Cloud → włącz *YouTube Data API v3*) wyszukiwanie idzie przez **oficjalne API**
— kilka zapytań (PL/EN: „akcje", „analiza", „wyniki", „stock analysis",
„earnings"), ostatnie **12 miesięcy**, z długością i liczbą wyświetleń,
bez Shorts. Bez klucza fallback na yt-dlp (działa lokalnie; na serwerach
bywa blokowany). Darmowy limit API: 10 000 jednostek/dobę ≈ ~25 spółek
dziennie (wyniki cache'owane 6 h).

> Ograniczenia: filmy > 60 min pomijane (tokeny); odsłuch przez Gemini zużywa
> pulę darmowego tieru (rotacja kluczy/modeli pomaga); cache w
> `data/ytt_<video_id>.json`. Napisy przez `YT_PROXY` nadal wspierane.

---

## Financial Charts

W sekcji analizy spółki (między oceną a deep research) moduł **📊 Financial Charts**:
na górze **interpretacja AI** (Financial Quality 0–100 + **wycena DCF/akcję** +
wycena AI Cheap/Fair/Expensive), która **uwzględnia Twoje prywatne notatki**
z sekcji „📝 Moje notatki" (model ocenia, czy metryki potwierdzają Twoje tezy,
czy im przeczą; gdy zmienisz notatki po wygenerowaniu analizy, aplikacja
oznaczy ją jako nieaktualną). Dalej blok **💰 Dywidenda** (ostatnia kwota
na akcję, dzień odcięcia, dzień wypłaty, stopa dywidendy + historia wypłat);
dla spółek, dla których Yahoo nie podaje **dnia wypłaty** (większość GPW),
przycisk *🔎 Znajdź dzień wypłaty* dociąga go przez AI z wyszukiwarką —
zawsze z linkami do źródeł do weryfikacji. Niżej kafelki KPI (Revenue/EPS CAGR, marża, ROE, P/E, dywidenda, FCF,
dług/EBITDA) i 15 wykresów Plotly w kartach 2-kolumnowych (przychody, wzrost,
zysk, marże, ROE, ROIC, FCF, dług netto, **P/E history z pasmami
i auto-komentarzem**, dywidendy, liczba akcji z wykryciem buyback/dilution,
EPS, book value, marża operacyjna).

Kod modularny w [charts/](charts/): `helpers.py` (kolory, layout, CAGR, format),
`data.py` (historia z yfinance, cache), `*_chart.py` (po jednej funkcji na wykres).

Pierwszy wykres to **kurs akcji** z okresami `1M/3M/6M/YTD/1R/3L/5L/10L/20L/Max`,
**wyborem źródła cen** (Yahoo / GPW / Alpha Vantage — patrz „Źródła danych")
i **nakładkami metryk** (multiselect): cena docelowa (konsensus), potencjał do
celu %, P/E, P/S, EV/EBITDA (z medianami 3-letnimi), marża operacyjna,
przychody/zysk netto/FCF oraz EPS z prognozami. Serie o tej samej jednostce
trafiają do wspólnych paneli pod wykresem ceny; ostatnie wartości mają etykiety
przy prawej krawędzi. Wskaźniki tygodniowe liczone są z ceny i rocznych
sprawozdań (przybliżenie). Wykresy Revenue i EPS pokazują też **prognozy
analityków** (kolejne ~2 lata obrachunkowe, z widełkami low/high) — z tego
samego źródła (yfinance).

> ⚠️ Darmowy yfinance daje ~5 lat rocznych sprawozdań (dywidendy, ceny i P/E —
> dłużej; prognozy analityków ~2 lata naprzód). Brak danych = komunikat, nie błąd.

---

## Panel decyzyjny (scenariusze 3Y, bramka, kill criteria)

W sekcji analizy spółki (za Financial Charts) moduł **🎯 Panel decyzyjny** —
natywna wersja dashboardu decyzyjnego w stylu Fisher/Lynch, dla każdej spółki:

- **Scenariusze 3-letnie** low/base/high: cena docelowa + prawdopodobieństwo
  (suwaki; base dopełnia się do 100%). Na żywo liczone: **wartość oczekiwana
  (EV)**, **CAGR vs hurdle rate 12–15%** i **asymetria zysk:strata (wymagane
  ≥ 2:1)** — z kolorowym pass/fail.
- **Bramka decyzyjna** — 6 warunków (wynik Fishera, variant perception,
  asymetria+EV, CAGR base case, katalizator 12–18M, płynność). Warunki
  policzalne oceniają się same z danych i suwaków; jakościowe ocenia AI,
  a każdy można nadpisać ręcznie.
- **Werdykt bramki** — reguła łącząca matematykę i jakość: `POZYCJA OK` /
  `OK Z ZASTRZEŻENIAMI — pół pozycji` / `SPEKULACJA ≤2% portfela` /
  `NIE KUPUJ`; złamane kill criteria wymuszają `WYJDŹ / NIE KUPUJ`.
- **Kill criteria** — edytowalna checklista sygnałów wyjścia z licznikiem
  „N/M złamanych"; zaznaczenia zapisują się od razu (to monitoring pozycji).
- **Oś czasu katalizatorów i ryzyk** + **licznik dni do raportu kwartalnego**.

Bazę jakościową (ceny scenariuszy, opisy, oceny bramki, kill criteria, oś
czasu) wypełnia **AI** (przycisk *🤖 Wygeneruj*, cache `data/decision_*.json`;
kontekst: dane Yahoo + wcześniejszy research AI i deep research). Bez klucza
API panel działa na **bazie mechanicznej** (base = konsensus analityków,
high/low = widełki) — wszystko uzupełniasz ręcznie. Twoje edycje i stan
checklisty zapisują się **per spółka trwale** w watchlists (GitHub Gist),
przyciskiem *💾 Zapisz panel*; *↺ Przywróć bazę* usuwa nadpisania.

Logika w [decision_panel.py](decision_panel.py) (funkcje czyste + UI),
testy w `decision_test.py`.

---

## Rekomendacje analityków GPW (PWPA)

Dla spółek objętych **Giełdowym Programem Wsparcia Pokrycia Analitycznego**
([gpw.pl/gpwpa](https://www.gpw.pl/gpwpa)) w analizie spółki pojawia się blok
z listą raportów maklerskich (data, dom maklerski, typ, **link do źródłowego PDF**).
Przycisk *🎯 Wyciągnij cenę docelową* czyta najnowszy raport (pypdf) i AI wyciąga
z niego **cenę docelową, rekomendację i uzasadnienie** — wszystko ze wskazaniem źródła.

Moduł [pwpa.py](pwpa.py): `list_reports()` (POST do ajaxindex.php, cache 12h),
`reports_for(ticker)`, `extract(report)` (PDF → tekst → JSON przez Gemini, cache).

> ⚠️ Program obejmuje ~70 spółek rynku głównego GPW — **nie całą GPW i nie Nasdaq**.
> Część raportów (komentarz, analiza wyników) nie zawiera formalnej ceny docelowej.
> Wyciąganie ceny wymaga `GEMINI_API_KEY`.

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
(1 = Strong Buy … 5 = Sell), **datę najbliższej PRZYSZŁEJ publikacji wyników**
(puste = spółka nie ogłosiła terminu) oraz **konsensus na najbliższy kwartał**:
oczekiwany wzrost przychodów i zysku (EPS) rok do roku, w procentach
(np. `+25%` / `−15%`), zielony przy wzroście i czerwony przy spadku.
Dalej **ostatnio opublikowane wyniki**: koniec kwartału, przychody, EPS oraz
**EPS vs konsensus** (o ile pobito oczekiwania; wstecznego konsensusu
przychodów darmowe Yahoo nie udostępnia). Następnie **dywidenda** wg reguły:
dane z bieżącego roku, a gdy ich brak — z ubiegłego (ex-date, dzień wypłaty,
kwota na akcję; dnia wypłaty dla większości spółek GPW Yahoo nie publikuje).
Do tego C/Z i kapitalizację.
Źródło: Yahoo Finance (kalendarz wyników/dywidend, historia wypłat, earnings
history + szacunki analityków); dla części spółek GPW dane są niedostępne
(puste pola).

**Układ tabeli (trwały).** W expanderze **⚙️ Ustawienia tabeli** kafelki kolumn
**przeciągasz myszką**: kolejność w „Widoczne" = kolejność kolumn w tabeli,
a przeciągnięcie do „Ukryte" usuwa kolumnę. Układ i wybrany segment zapisują się
w tym samym miejscu co listy (Gist/plik), więc przeżywają restart.

> ⚠️ Przeciąganie nagłówków **wewnątrz** tabeli Streamlit pokazuje zmianę tylko
> wizualnie — komponent nie zgłasza nowej kolejności do aplikacji, więc nie da
> się jej zapamiętać. Trwałą kolejność ustawia się kafelkami (wyżej).

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
├── fisher_score.py   # scoring ilościowy 0–100 (wagi parametryczne)
├── gurus.py          # 8 strategii inwestorów (wagi + prompty AI)
├── gpw_indices.py    # składy WIG20/mWIG40/sWIG80 + lista Nasdaq-AI
├── ai_research.py    # szybka ocena jakościowa AI (Gemini / OpenAI-compatible)
├── financial_charts.py # sekcja "Financial Charts" (KPI + 15 wykresow + AI)
├── charts/           # modularne wykresy Plotly (helpers, data, *_chart.py)
├── research_deep.py  # deep research: sentyment + YouTube + IR (Gemini grounding)
├── decision_panel.py # panel decyzyjny: scenariusze 3Y, bramka, kill criteria
├── decision_test.py  # testy panelu decyzyjnego (czyste funkcje + AppTest)
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

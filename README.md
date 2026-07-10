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

### Transkrypcja i analiza wideo ([yt_transcribe.py](yt_transcribe.py))

Podsekcja **🎧 Transkrypcja i analiza wideo**: wybierasz film z YouTube o spółce,
a agent bierze jego transkrypt i wyciąga wnioski (kluczowe tezy, sentyment autora,
ryzyka). Kolejność: najpierw **napisy** (szybko, w tym auto-ASR); gdy ich brak —
pobiera **audio** (yt-dlp) i **transkrybuje przez Gemini** (model multimodalny).
Wymaga `ffmpeg` (jest w [packages.txt](packages.txt), instalowany na Streamlit Cloud).

> ⚠️ **YouTube blokuje IP centrów danych** (błąd 403) — na Streamlit Cloud zarówno
> napisy, jak i audio zwykle się nie zaciągną. Ta funkcja działa pewnie:
> **(a) lokalnie** (`streamlit run app.py` z domowego IP), albo **(b) z proxy** —
> ustaw `YT_PROXY = "http://user:pass@host:port"` (residential) w Secrets.
> Deep research (findings z YouTube przez Google Search) działa na chmurze niezależnie.
>
> Pozostałe ograniczenia: pobieranie audio to szara strefa ToS YouTube; filmy > 30 min
> pomijane; audio-STT zużywa pulę Gemini (rotacja kluczy pomaga); cache w
> `data/ytt_<video_id>.json`. Whisper lokalny nie zmieści się na Streamlit Cloud.

---

## Financial Charts

W sekcji analizy spółki (między oceną a deep research) moduł **📊 Financial Charts**:
kafelki KPI (Revenue/EPS CAGR, marża, ROE, P/E, dywidenda, FCF, dług/EBITDA) i
15 wykresów Plotly w kartach 2-kolumnowych (przychody, wzrost, zysk, marże, ROE,
ROIC, FCF, dług netto, **P/E history z pasmami i auto-komentarzem**, dywidendy,
liczba akcji z wykryciem buyback/dilution, EPS, book value, marża operacyjna) oraz
**interpretacja AI** (Financial Quality 0–100 + wycena Cheap/Fair/Expensive).

Kod modularny w [charts/](charts/): `helpers.py` (kolory, layout, CAGR, format),
`data.py` (historia z yfinance, cache), `*_chart.py` (po jednej funkcji na wykres).

Pierwszy wykres to **kurs akcji** z przełącznikiem okresu (1 rok / 2 / 3 / 5 lat).
Wykresy Revenue i EPS pokazują też **prognozy analityków** (kolejne ~2 lata
obrachunkowe, z widełkami low/high) — z tego samego źródła (yfinance).

> ⚠️ Darmowy yfinance daje ~5 lat rocznych sprawozdań (dywidendy, ceny i P/E —
> dłużej; prognozy analityków ~2 lata naprzód). Brak danych = komunikat, nie błąd.

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
├── fisher_score.py   # scoring ilościowy 0–100 (wagi parametryczne)
├── gurus.py          # 8 strategii inwestorów (wagi + prompty AI)
├── gpw_indices.py    # składy WIG20/mWIG40/sWIG80 + lista Nasdaq-AI
├── ai_research.py    # szybka ocena jakościowa AI (Gemini / OpenAI-compatible)
├── financial_charts.py # sekcja "Financial Charts" (KPI + 15 wykresow + AI)
├── charts/           # modularne wykresy Plotly (helpers, data, *_chart.py)
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

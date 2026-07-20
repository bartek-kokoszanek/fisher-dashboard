# Układ modułów: pasek przeglądu + zakładki — plan wdrożenia

> **Dla wykonawcy:** WYMAGANY SUB-SKILL: użyj `superpowers:subagent-driven-development` (zalecane) albo `superpowers:executing-plans`, żeby wdrażać ten plan zadanie po zadaniu. Kroki mają checkboxy (`- [ ]`) do odhaczania.

**Cel:** Rozbić jedną 20-sekcyjną stronę analizy spółki na przypięty pasek przeglądu + 5 zakładek tematycznych, przenosząc sekcje z `app.py` (1084 linie) do pakietu `sections/`.

**Architektura:** `app.py` zostaje orkiestratorem (panel boczny, dane, ranking, wybór spółki, złożenie zakładek). Każda sekcja dostaje własny moduł w `sections/` z jednym wejściem `render(...)`. Moduły domenowe (`financial_charts`, `decision_panel`, `research_deep`, `pwpa*`, `charts/`) zostają bez zmian w odpowiedzialności — poza wymuszonym rozbiciem `financial_charts.render()`, którego części trafiają do dwóch różnych zakładek.

**Stack:** Python 3.11, Streamlit 1.59, pandas, Plotly. Testy: `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-07-20-uklad-modulow-design.md`

## Global Constraints

- **To refaktor, nie przepisywanie.** Ciała funkcji i logika przenoszone dosłownie. Jeśli kusi Cię „przy okazji poprawić" — nie rób tego, zgłoś jako osobne zadanie.
- **Motyw tylko ciemny** (`.streamlit/config.toml`, `base = "dark"`, brak `[theme.light]`) — nie ruszać.
- **Czerwień i zieleń są zarezerwowane dla znaczenia** (spadek/wzrost). Nie używać ich jako dekoracji UI.
- **Braki danych to komunikat, nie wyjątek.** Każda sekcja fail-soft: `st.info` / `st.caption`, nigdy nieobsłużony traceback.
- **W pasku przeglądu brak wartości pokazuje `—`; kolumna nigdy nie znika** (inaczej układ skacze przy przełączaniu spółek).
- **Po każdym zadaniu aplikacja musi się renderować** — `AppTest` bez wyjątków. Nie przechodź do następnego zadania z czerwonym testem.
- **Język interfejsu: polski.** Komentarze w kodzie bez polskich znaków diakrytycznych (konwencja tego repo).
- Testy uruchamiać z `PYTHONIOENCODING=utf-8`, bo konsola Windows (cp1250) wywraca się na emoji w wynikach.

**Konwencja zapisu przenosin (świadome odstępstwo od „pokaż cały kod w kroku").**
Tam, gdzie krok mówi `# <- przenies blok X z app.py (linie A-B)`, chodzi
o przeniesienie **istniejącego kodu bez zmian**, a nie o napisanie go od nowa.
Bloki mają po 40-60 linii i są już w repozytorium — przepisywanie ich do planu
zwiększałoby ryzyko literówek i rozjechania się z `app.py`, gdyby plik zmienił
się przed wykonaniem. Kroki, które tworzą **nowy** kod (pasek przeglądu, opakowania
sekcji, testy), mają pełny kod wprost.

---

### Task 1: Szkielet — pakiet `sections/`, pasek przeglądu, puste zakładki

**Files:**
- Create: `sections/__init__.py`
- Create: `sections/overview.py`
- Create: `tabs_test.py`
- Modify: `app.py` (blok analizy spółki: linie 844, 872-892 → zastąpione paskiem; dodanie `st.tabs`)

**Interfaces:**
- Consumes: `row` (dict wiersza rankingu), `wl` (watchlisty), `pwpa_targets.cell`, `research_deep.load_cached`, `financial_charts.dcf_per_share`, `financial_charts._hist`
- Produces: `sections.overview.render(ticker, row, hist) -> None` — pasek metryk. Zakładki tworzone w `app.py` jako `tab_fund, tab_val, tab_market, tab_dec, tab_notes = st.tabs([...])`

- [ ] **Krok 1: Napisz test, który sprawdza pasek i 5 zakładek**

Utwórz `tabs_test.py`:

```python
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
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `BLAD: zakladki [] != ['📊 Fundamenty', ...]` (zakładek jeszcze nie ma).

- [ ] **Krok 3: Utwórz `sections/__init__.py`**

```python
"""Sekcje ekranu analizy spolki.

Kazdy modul renderuje jedna zakladke (albo pasek przegladu) i ma jedno
wejscie render(...). app.py tylko sklada je w calosc.
"""
```

- [ ] **Krok 4: Utwórz `sections/overview.py`**

```python
"""Przypiety pasek przegladu — zawsze widoczny nad zakladkami.

Monitoring znanych spolek konczy sie na tym pasku (odpowiedz bez jednego
klikniecia), research ma te liczby na oczach podczas czytania kazdej
zakladki. Brak wartosci pokazuje '—' i kolumna NIE znika, zeby uklad nie
skakal przy przelaczaniu spolek.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import financial_charts
import fisher_score
import pwpa_targets
import research_deep
from charts import helpers as h
from charts.helpers import fmt_dt

DASH = "—"


def _dni_do(iso: str | None) -> str:
    """'2026-08-27' -> 'za 38 dni' / 'dzis' / '' gdy data minela lub brak."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso)).date()
    except (ValueError, TypeError):
        return ""
    delta = (d - date.today()).days
    if delta < 0:
        return ""
    return "dzis" if delta == 0 else f"za {delta} dni"


def render(ticker: str, row: dict, hist: dict) -> None:
    with st.container(border=True):
        c = st.columns(7)

        # 1. wynik + sygnal
        av = fisher_score.action_verdict(row.get("combined"))
        wynik = row.get("combined")
        c[0].metric("Wynik", DASH if wynik is None else f"{wynik:.0f}",
                    delta=f"{av['emoji']} {av['label']}", delta_color="off")

        # 2. wycena DCF na akcje
        dcf = financial_charts.dcf_per_share(hist) if hist else None
        cena = row.get("price")
        curr = row.get("currency") or ""
        if dcf and h.is_num(cena) and cena:
            c[1].metric("DCF / akcję", f"{dcf['value']:.2f} {curr}".strip(),
                        delta=f"{(dcf['value'] / cena - 1) * 100:+.0f}% vs cena")
        else:
            c[1].metric("DCF / akcję", DASH)

        # 3. cena docelowa z raportu PWPA
        c[2].metric("Cena docelowa PWPA", pwpa_targets.cell(ticker) or DASH)

        # 4. najblizsze wyniki kwartalne
        ned = row.get("next_earnings_date")
        c[3].metric("Najbliższe wyniki", str(ned) if ned else DASH,
                    delta=_dni_do(ned) or None, delta_color="off")

        # 5. dywidenda
        kwota, ex = row.get("last_dividend_value"), row.get("ex_dividend_date")
        c[4].metric("Dywidenda",
                    f"{kwota:.2f} {curr}".strip() if h.is_num(kwota) else DASH,
                    delta=f"ex {ex}" if ex else None, delta_color="off")

        # 6. sentyment rynku z deep researchu
        sent = (research_deep.load_cached(ticker) or {}).get("sentiment")
        c[5].metric("Sentyment", f"{sent:+d}" if isinstance(sent, int) else DASH)

        # 7. pokrycie danych
        c[6].metric("Pokrycie", f"{row.get('coverage', 0):.0f}%")

        st.caption(f"🗓 Yahoo Finance · zaktualizowano {fmt_dt(row.get('fetched_at'))}")
```

- [ ] **Krok 5: Wepnij pasek i zakładki w `app.py`**

W `app.py` usuń linię 844 (`st.info(f"📌 Analizowana spółka: ...")`) oraz blok metryk i sygnału (linie 872-892: od `c1, c2, c3, c4 = st.columns(4)` do końca bloku `if av["level"] ...`). W ich miejsce, **po** bloku przypisania do list (linia ~870), wstaw:

```python
    _hist_row = financial_charts._hist(pick)
    sections.overview.render(pick, row, _hist_row)

    tab_fund, tab_val, tab_market, tab_dec, tab_notes = st.tabs(
        ["📊 Fundamenty", "💰 Wycena", "🌐 Rynek", "🎯 Decyzja", "📝 Notatki"])
```

Dodaj import na górze `app.py`, przy pozostałych importach lokalnych:

```python
import sections.overview
```

- [ ] **Krok 6: Uruchom test — musi przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `[OK ] zakladki: [...]` i `[OK ] pasek przegladu zawiera komplet pol`, kod wyjścia 0.

- [ ] **Krok 7: Commit**

```bash
git add sections/ tabs_test.py app.py
git commit -m "feat: pasek przegladu + szkielet 5 zakladek

Pasek zastepuje 4 metryki i blok sygnalu; jest zawsze widoczny nad
zakladkami, wiec monitoring dostaje odpowiedz bez klikniecia, a research
ma kluczowe liczby na oczach przy kazdej zakladce."
```

---

### Task 2: Rozbicie `financial_charts.render()` na pięć funkcji

**Files:**
- Modify: `financial_charts.py` (funkcja `render`, linie ~396-530)

**Interfaces:**
- Produces:
  - `render_ai_interpretation(ticker, row, hist, notes) -> None`
  - `render_price_chart(ticker, row, hist) -> None`
  - `render_dividend(ticker, row, hist) -> None` (dziś prywatne `_render_dividend`)
  - `render_kpis(hist, row) -> None`
  - `render_charts(hist, row) -> None`
  - `render(ticker, row, notes=None) -> None` zostaje jako kompozycja powyższych (żeby nic nie urwać w tym kroku)

**Dlaczego:** dziś `render()` robi wszystko w jednym ciągu, a jego części trafiają do **dwóch różnych zakładek** (Fundamenty i Wycena). To jedyna wymuszona ingerencja w istniejący moduł.

- [ ] **Krok 1: Napisz test, który sprawdza, że pięć funkcji istnieje i są wywoływalne**

Dopisz na końcu `tabs_test.py`, przed `if __name__`:

```python
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
```

i wywołaj ją w `main()` tuż po sprawdzeniu paska:

```python
    rc = test_financial_charts_api()
    if rc:
        return rc
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `BLAD: brak funkcji w financial_charts: ['render_ai_interpretation', 'render_price_chart', 'render_kpis', 'render_charts']`.

- [ ] **Krok 3: Rozbij `render()` w `financial_charts.py`**

Zmień nazwę `_render_dividend` na `render_dividend` (i popraw jej wywołanie). Następnie zamień ciało `render()` na pięć funkcji, **przenosząc istniejący kod bez zmian**:

```python
def render_ai_interpretation(ticker: str, row: dict, hist: dict,
                             notes: str | None = None) -> None:
    """Interpretacja AI + Financial Quality + wycena DCF + wycena AI."""
    # <- tutaj przenies blok z dotychczasowego render():
    #    od 'st.markdown("**🤖 Automatyczna interpretacja AI**")'
    #    do konca bloku 'if fin:' wlacznie z podpisem generated_at


def render_price_chart(ticker: str, row: dict, hist: dict) -> None:
    """Kurs akcji: okres, zrodlo cen, nakladki metryk."""
    # <- przenies blok od 'st.markdown(f"**Kurs akcji — ...")'
    #    do st.caption z opisem zrodel cen


def render_kpis(hist: dict, row: dict) -> None:
    """Kafelki KPI (Revenue CAGR, ROE, P/E, dywidenda, FCF, dlug/EBITDA)."""
    kpis = _kpis(hist, row)
    cols = st.columns(3)
    for i, (label, val) in enumerate(kpis):
        cols[i % 3].metric(label, val)


def render_charts(hist: dict, row: dict) -> None:
    """15 wykresow w kartach 2-kolumnowych."""
    specs = _specs(hist, row)
    for i in range(0, len(specs), 2):
        c1, c2 = st.columns(2)
        _card(c1, *specs[i])
        if i + 1 < len(specs):
            _card(c2, *specs[i + 1])


def render(ticker: str, row: dict, notes: str | None = None) -> None:
    """Cala sekcja w dotychczasowej kolejnosci (zgodnosc wstecz).

    Po przepieciu zakladek w Task 3-4 ta funkcja przestaje byc uzywana
    przez app.py — zostaje, bo nie ma powodu jej usuwac w tym kroku.
    """
    st.subheader(f"📊 Financial Charts — {ticker} — {row.get('name', ticker)}")
    hist = _hist(ticker)
    render_ai_interpretation(ticker, row, hist, notes)
    st.divider()
    render_price_chart(ticker, row, hist)
    st.divider()
    render_dividend(ticker, row, hist)
    render_kpis(hist, row)
    st.divider()
    render_charts(hist, row)
```

- [ ] **Krok 4: Uruchom testy — muszą przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
```

Oczekiwane: oba bez wyjątków, `tabs_test.py` wypisuje `[OK ] financial_charts wystawia: ...`.

- [ ] **Krok 5: Commit**

```bash
git add financial_charts.py tabs_test.py
git commit -m "refactor: rozbicie financial_charts.render na piec funkcji

Czesci tej sekcji trafiaja do dwoch roznych zakladek (Fundamenty
i Wycena), wiec monolit musi sie rozpasc. render() zostaje jako
kompozycja — zgodnosc wstecz, zero zmian w logice."
```

---

### Task 3: Zakładka Fundamenty

**Files:**
- Create: `sections/fundamentals.py`
- Modify: `app.py` (usunięcie bloku „Rozbicie ilosciowe" z kolumny `left`, linie ~924-940; wpięcie w `tab_fund`)

**Interfaces:**
- Consumes: `financial_charts.render_price_chart/_kpis/_charts`, `fisher_score.RAW_KEY`, `METRIC_LABELS` z `app.py`
- Produces: `sections.fundamentals.render(ticker, row, hist, metric_labels, fmt_pct) -> None`

- [ ] **Krok 1: Dopisz do `tabs_test.py` sprawdzenie zawartości zakładki**

W `main()`, po sprawdzeniu paska, dodaj:

```python
    fund = " ".join(str(m.value) for m in at.tabs[0].markdown)
    if "Kurs akcji" not in fund:
        print("BLAD: zakladka Fundamenty nie zawiera kursu akcji")
        return 1
    print("[OK ] Fundamenty: kurs akcji obecny")
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `BLAD: zakladka Fundamenty nie zawiera kursu akcji`.

- [ ] **Krok 3: Utwórz `sections/fundamentals.py`**

```python
"""Zakladka Fundamenty: kurs, rozbicie ilosciowe, KPI, 15 wykresow.

Kolejnosc od tego, co widac najszybciej (kurs), przez to, z czego
sklada sie Wynik (subscore), po pelna historie finansowa.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import financial_charts
import fisher_score


def render(ticker: str, row: dict, hist: dict, metric_labels: dict,
           fmt_pct) -> None:
    financial_charts.render_price_chart(ticker, row, hist)
    st.divider()

    st.markdown("**Rozbicie ilościowe**")
    subs = row.get("subscores") or {}
    srows = [{"Metryka": label, "Pkt (0-100)": subs[m],
              "Wartosc surowa": fmt_pct(row.get(fisher_score.RAW_KEY[m]))}
             for m, label in metric_labels.items() if m in subs]
    st.dataframe(pd.DataFrame(srows), hide_index=True, width="stretch")
    st.caption(f"Sektor: {row.get('sector') or '—'} · "
               f"Kapitalizacja: {row.get('market_cap') or '—'} "
               f"{row.get('currency') or ''}")
    st.divider()

    financial_charts.render_kpis(hist, row)
    st.divider()
    financial_charts.render_charts(hist, row)
```

- [ ] **Krok 4: Wepnij w `app.py`**

Usuń z `app.py` blok `left, right = st.columns(2)` **wraz z zawartością kolumny `left`** (Rozbicie ilościowe). Kolumnę `right` (Ocena jakościowa) zostaw na razie nietkniętą — przenosi ją Task 6. Dodaj import `import sections.fundamentals` i wpięcie:

```python
    with tab_fund:
        sections.fundamentals.render(pick, row, _hist_row, METRIC_LABELS, fmt_pct)
```

- [ ] **Krok 5: Uruchom testy — muszą przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
```

- [ ] **Krok 6: Commit**

```bash
git add sections/fundamentals.py app.py tabs_test.py
git commit -m "feat: zakladka Fundamenty (kurs, subscore, KPI, wykresy)"
```

---

### Task 4: Zakładka Wycena

**Files:**
- Create: `sections/valuation.py`
- Modify: `app.py` (usunięcie wywołania `render_pwpa` z linii ~920-922 i `financial_charts.render` z ~977-979; wpięcie w `tab_val`)

**Interfaces:**
- Consumes: `financial_charts.render_ai_interpretation/render_dividend`, `render_pwpa` z `app.py`
- Produces: `sections.valuation.render(ticker, row, hist, notes, render_pwpa_fn, label) -> None`

- [ ] **Krok 1: Dopisz sprawdzenie do `tabs_test.py`**

```python
    val = " ".join(str(m.value) for m in at.tabs[1].markdown)
    if "Dywidenda" not in val:
        print("BLAD: zakladka Wycena nie zawiera bloku dywidendy")
        return 1
    print("[OK ] Wycena: dywidenda obecna")
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `BLAD: zakladka Wycena nie zawiera bloku dywidendy`.

- [ ] **Krok 3: Utwórz `sections/valuation.py`**

```python
"""Zakladka Wycena: interpretacja AI, dywidenda, raporty PWPA.

Dywidenda mieszka tutaj, a nie w fundamentach, bo jest skladnikiem stopy
zwrotu, nie fundamentem operacyjnym (patrz spec).
"""
from __future__ import annotations

import streamlit as st

import financial_charts


def render(ticker: str, row: dict, hist: dict, notes: str | None,
           render_pwpa_fn, label: str) -> None:
    financial_charts.render_ai_interpretation(ticker, row, hist, notes)
    st.divider()
    financial_charts.render_dividend(ticker, row, hist)
    if ticker.endswith(".WA"):
        render_pwpa_fn(ticker, label)
```

- [ ] **Krok 4: Wepnij w `app.py`**

**UWAGA — poprawka odkryta przy wykonaniu Task 3:** pierwotny plan zakładał,
że do Task 4 w `app.py` przetrwa jedno wywołanie `financial_charts.render(...)`
(cała kompozycja). W praktyce Task 3 musiał je zastąpić wywołaniem TYLKO
`render_ai_interpretation` + `render_dividend` — bo `render_price_chart`/
`render_kpis`/`render_charts` trafiły już do zakładki Fundamenty, a wywołanie
ich DRUGI RAZ przez starą kompozycję `render()` dawało
`StreamlitDuplicateElementKey` (ten sam `key=f"pxper_{ticker}"` w dwóch
miejscach na jednym renderze). Szukaj więc w `app.py` bloku:
```python
    # ---------------- Financial Charts ----------------
    st.divider()
    financial_charts.render_ai_interpretation(pick, row, _hist_row,
                                              wl.get("notes", {}).get(pick))
    financial_charts.render_dividend(pick, row, _hist_row)
```
(a nie starego `financial_charts.render(pick, row, notes=...)`).

Usuń z `app.py` blok `if pick.endswith(".WA"): render_pwpa(...)` (linie ~920-922) oraz cały powyższy blok Financial Charts. Dodaj import `import sections.valuation` i wpięcie:

```python
    with tab_val:
        sections.valuation.render(pick, row, _hist_row,
                                  wl.get("notes", {}).get(pick),
                                  render_pwpa, co_label(pick, row))
```

- [ ] **Krok 5: Uruchom testy — muszą przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
```

- [ ] **Krok 6: Commit**

```bash
git add sections/valuation.py app.py tabs_test.py
git commit -m "feat: zakladka Wycena (interpretacja AI, dywidenda, PWPA)"
```

---

### Task 5: Zakładka Rynek

**Files:**
- Create: `sections/market.py`
- Modify: `app.py` (przeniesienie bloków deep research ~985-1040 i analizy wideo ~1041-1102)

**Interfaces:**
- Consumes: `research_deep`, `yt_transcribe`, `yt_videos` (cache'owana funkcja z `app.py`), `fmt_dt`
- Produces: `sections.market.render(ticker, row, label, yt_videos_fn) -> None`

- [ ] **Krok 1: Dopisz sprawdzenie do `tabs_test.py`**

```python
    mkt = " ".join(str(m.value) for m in at.tabs[2].markdown) + \
          " ".join(str(s.value) for s in at.tabs[2].subheader)
    if "Deep research" not in mkt:
        print("BLAD: zakladka Rynek nie zawiera deep researchu")
        return 1
    print("[OK ] Rynek: deep research obecny")
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

- [ ] **Krok 3: Utwórz `sections/market.py`**

Przenieś **dosłownie** obydwa bloki z `app.py` (deep research i analiza wideo) do:

```python
"""Zakladka Rynek: deep research (sentyment, newsy, IR) + analiza wideo."""
from __future__ import annotations

import os

import streamlit as st

import research_deep
import yt_transcribe
from charts.helpers import fmt_dt


def render(ticker: str, row: dict, label: str, yt_videos_fn) -> None:
    # <- przenies blok '🔎 Deep research' z app.py (od st.subheader
    #    do st.caption z data researched_at)
    # <- pod nim przenies blok '🎧 Analiza wideo (AI)' z app.py
    ...
```

- [ ] **Krok 4: Wepnij w `app.py`**

Usuń oba przeniesione bloki, dodaj `import sections.market` i:

```python
    with tab_market:
        sections.market.render(pick, row, co_label(pick, row), yt_videos)
```

- [ ] **Krok 5: Uruchom testy — muszą przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
```

- [ ] **Krok 6: Commit**

```bash
git add sections/market.py app.py tabs_test.py
git commit -m "feat: zakladka Rynek (deep research + analiza wideo)"
```

---

### Task 6: Zakładka Decyzja

**Files:**
- Create: `sections/decision.py`
- Modify: `app.py` (kolumna `right` z oceną jakościową ~941-964, zalety/wady ~965-976, panel decyzyjny ~981-983)

**Interfaces:**
- Consumes: `ai_research`, `gurus`, `decision_panel.render`
- Produces: `sections.decision.render(ticker, row, wl, save_wl, guru_key, label) -> None`

**Uwaga:** ocena jakościowa i zalety/wady mieszkają tutaj, bo karmią jakościowe warunki bramki („wariant", „katalizator") — patrz spec.

- [ ] **Krok 1: Dopisz sprawdzenie do `tabs_test.py`**

```python
    dec = " ".join(str(s.value) for s in at.tabs[3].subheader) + \
          " ".join(str(m.value) for m in at.tabs[3].markdown)
    if "Panel decyzyjny" not in dec:
        print("BLAD: zakladka Decyzja nie zawiera panelu decyzyjnego")
        return 1
    print("[OK ] Decyzja: panel decyzyjny obecny")
```

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

- [ ] **Krok 3: Utwórz `sections/decision.py`**

```python
"""Zakladka Decyzja: ocena jakosciowa AI, zalety/wady, panel decyzyjny.

Ocena jakosciowa stoi tutaj, a nie przy fundamentach, bo to ona karmi
jakosciowe warunki bramki decyzyjnej ('wariant', 'katalizator').
"""
from __future__ import annotations

import streamlit as st

import ai_research
import decision_panel
import gurus
from charts.helpers import fmt_dt


def render(ticker: str, row: dict, wl: dict, save_wl, guru_key: str,
           label: str) -> None:
    # <- przenies blok 'Ocena jakosciowa (...)' z kolumny right w app.py
    # <- pod nim blok 'Najwieksze zalety / wady'
    st.divider()
    decision_panel.render(ticker, row, wl, save_wl)
```

- [ ] **Krok 4: Wepnij w `app.py`**

Usuń resztkę `left, right = st.columns(2)` (po Task 3 zostaje sama kolumna `right`) razem z blokiem zalet/wad i wywołaniem `decision_panel.render`. Dodaj `import sections.decision` i:

```python
    with tab_dec:
        sections.decision.render(pick, row, wl, save_wl, guru_key,
                                 co_label(pick, row))
```

- [ ] **Krok 5: Uruchom testy — muszą przejść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe decision_test.py
```

Oczekiwane: `decision_test.py` nadal wypisuje `Render OK — panel decyzyjny dziala.`

- [ ] **Krok 6: Commit**

```bash
git add sections/decision.py app.py tabs_test.py
git commit -m "feat: zakladka Decyzja (ocena jakosciowa, zalety/wady, panel)"
```

---

### Task 7: Zakładka Notatki + sprzątanie `app.py`

**Files:**
- Create: `sections/notes.py`
- Modify: `app.py` (blok notatek ~893-919, usunięcie martwych importów)

**Interfaces:**
- Produces: `sections.notes.render(ticker, wl, save_wl) -> None`

- [ ] **Krok 1: Dopisz sprawdzenie do `tabs_test.py`**

```python
    notes_txt = " ".join(str(m.value) for m in at.tabs[4].markdown) + \
                " ".join(str(c.value) for c in at.tabs[4].caption)
    if "notatk" not in notes_txt.lower():
        print("BLAD: zakladka Notatki jest pusta")
        return 1
    print("[OK ] Notatki: sekcja obecna")

    # Prog ostrzegawczy z zapasem, zeby test nie pekal przy kazdej drobnej
    # zmianie w app.py (zobacz uwage nizej o pierwotnym, blednym celu ~350/600).
    dlugosc = len(open("app.py", encoding="utf-8").read().splitlines())
    if dlugosc > 950:
        print(f"BLAD: app.py ma {dlugosc} linii, prog to 950")
        return 1
    print(f"[OK ] app.py: {dlugosc} linii")
```

**UWAGA — poprawka odkryta przy wykonaniu Task 7:** pierwotny plan zakladal
cel ~350 linii / prog 600 dla `app.py` po tym zadaniu. W praktyce app.py
zmniejszylo sie z 1111 linii (przed Task 1) do 905 linii (po usunieciu bloku
notatek w tym zadaniu) — realna redukcja tylko z tych czesci, ktore ten plan
faktycznie przenosil (fundamenty, wycena, rynek, decyzja, notatki). Reszta
app.py (sidebar, filtry, tabela rankingowa, watchlisty, mostek Secrets) NIGDY
nie byla w zakresie tego planu (spec projektowy mowil tylko o podziale sekcji
"per spolka"), wiec proba zejscia do 350/600 linii bylaby wymyslonym celem bez
pokrycia w zakresie zadan. Prog skorygowany na 950 (realne 905 + margines na
drobne przyszle zmiany) — dziala jako regresyjny alarm przed rozrostem, nie
jako fikcyjny cel architektoniczny.

- [ ] **Krok 2: Uruchom test — musi paść**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

- [ ] **Krok 3: Utwórz `sections/notes.py`**

Przenieś blok notatek z `app.py` (expander „📝 Moje notatki / wnioski z analiz" wraz z zapisem):

```python
"""Zakladka Notatki: prywatne wnioski uzytkownika (zapis w Giscie).

Notatki zasilaja interpretacje AI w zakladce Wycena — dlatego sekcja
mowi o tym wprost, zeby nie trzeba bylo tego zgadywac.
"""
from __future__ import annotations

import streamlit as st

import watchlists


def render(ticker: str, wl: dict, save_wl) -> None:
    # <- przenies zawartosc expandera z app.py (text_area + zapis)
    st.caption("Te notatki trafiają do interpretacji AI w zakładce "
               "💰 Wycena — po ich zmianie przelicz podsumowanie tam.")
```

- [ ] **Krok 4: Wepnij w `app.py` i posprzątaj**

```python
    with tab_notes:
        sections.notes.render(pick, wl, save_wl)
```

Usuń z `app.py` importy, które przestały być używane (sprawdź: `research_deep`, `yt_transcribe`, `ai_research`, `decision_panel`, `os` — zostaw te, których nadal używa ranking albo mostek Secrets).

- [ ] **Krok 4b: Usuń martwą funkcję kompozycji z `financial_charts.py`**

Task 2 zostawił `render(ticker, row, notes=None)` jako kompozycję pięciu nowych
funkcji — wyłącznie po to, żeby `app.py` działał przez chwilę między Task 2
a Task 4 (jedyne wywołanie usunęło Task 4). Sprawdź, że to prawda, zanim
usuniesz:

```bash
grep -rn "financial_charts\.render(" --include="*.py" .
```

Oczekiwane: brak wyników (poza samą definicją w `financial_charts.py`). Jeśli
coś się znajdzie — **nie usuwaj**, tylko zgłoś to jako rozbieżność z planem.

Jeśli pusto: usuń funkcję `render(...)` z `financial_charts.py` w całości
(cała funkcja dodana w Task 2, krok 3, ostatni blok „def render").

- [ ] **Krok 5: Uruchom pełny zestaw testów**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe ui_test.py
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe decision_test.py
./.venv/Scripts/python.exe smoke_test.py
```

- [ ] **Krok 6: Commit**

```bash
git add sections/notes.py app.py tabs_test.py
git commit -m "feat: zakladka Notatki + sprzatanie app.py"
```

---

### Task 8: Test braków danych w pasku + dokumentacja

**Files:**
- Modify: `tabs_test.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `sections.overview.render`

- [ ] **Krok 1: Dopisz test paska dla spółki ubogiej w dane**

```python
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
```

i wywołaj w `main()`.

- [ ] **Krok 2: Uruchom test**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe tabs_test.py
```

Oczekiwane: `[OK ] pasek: brakujace wartosci obsluzone`.

- [ ] **Krok 3: Zaktualizuj `README.md`**

W sekcji o analizie spółki opisz nowy układ: przypięty pasek przeglądu i pięć zakładek (Fundamenty / Wycena / Rynek / Decyzja / Notatki), z adnotacją, że dywidenda mieszka w Wycenie, a ocena jakościowa w Decyzji.

- [ ] **Krok 4: Commit**

```bash
git add tabs_test.py README.md
git commit -m "test: braki danych w pasku przegladu + opis ukladu w README"
```

---

## Weryfikacja końcowa

- [ ] `tabs_test.py`, `ui_test.py`, `decision_test.py`, `smoke_test.py` — wszystkie zielone
- [ ] `app.py` poniżej 950 linii (patrz uwaga o skorygowanym progu w Task 7)
- [ ] Aplikacja odpalona lokalnie: pasek widoczny nad zakładkami, pięć zakładek przełącza się, żadna nie jest pusta
- [ ] PR z opisem, co się przeniosło i gdzie; w razie problemów rewert całego PR-a zamiast punktowych łatek

"""Ceny docelowe z raportow GPW PWPA — automatyczna ekstrakcja w tle (24 h).

Kolumna "GPW PWPA" w rankingu pokazuje CENE DOCELOWA i DATE wyceny. Cena
docelowa istnieje wylacznie w tresci PDF raportu maklerskiego, wiec wyciaga
ja AI (pwpa.extract -> pypdf + Gemini). To o wiele za drogo, zeby robic przy
kazdym renderze tabeli, stad ten modul:

  * ekstrakcja jest URUCHAMIANA RECZNIE (przycisk nad tabela), nigdy sama
    z siebie — kazde zapytanie do modelu jest swiadoma decyzja uzytkownika,
  * wyniki trzymamy w JEDNYM malym pliku {ticker: {...}} — nie w 70 osobnych,
  * plik lezy w GISCIE (jak listy obserwacyjne), bo dysk Streamlit Cloud jest
    ulotny: bez tego kazdy redeploy kasowalby wyniki i kazda kolejna ekstrakcja
    ruszalaby od zera, palac limit Gemini,
  * liczymy TYLKO to, co nowe: jesli najnowszy raport spolki ma ten sam
    pdf_url co zapisany wynik, nie ruszamy modelu w ogole.
"""
from __future__ import annotations

from datetime import datetime, timezone

import ai_research
import pwpa
import watchlists

FILE_NAME = "pwpa_targets.json"
MAX_PER_RUN = 70        # twardy limit zapytan do modelu na jeden przebieg
RETRY_FAILED_DAYS = 7   # nieczytelny PDF (skan) — nie probuj codziennie
_MEMO_S = 60            # pamiec podreczna w procesie (Gist to zapytanie HTTP)

_memo: tuple[float, dict] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat(timespec="seconds")


def _age_h(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        return (_now() - datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:
        return 1e9


def load(force: bool = False) -> dict:
    """{"targets": {TICKER: {...}}, "failed": {url: iso}, "updated_at": iso}."""
    global _memo
    import time
    if not force and _memo and (time.time() - _memo[0]) < _MEMO_S:
        return _memo[1]
    data = watchlists.load_file(FILE_NAME) or {}
    data.setdefault("targets", {})
    data.setdefault("failed", {})
    _memo = (time.time(), data)
    return data


def _save(data: dict) -> None:
    global _memo
    import time
    data["updated_at"] = _iso()
    watchlists.save_file(FILE_NAME, data)
    _memo = (time.time(), data)


def missing_for(tickers) -> list[str]:
    """Tickery GPW objete PWPA, dla ktorych nie mamy jeszcze aktualnej ceny.

    Sluzy do policzenia, ile zapytan do modelu kosztowalby przycisk — zanim
    uzytkownik go kliknie.
    """
    data = load()
    targets, failed = data["targets"], data["failed"]
    try:
        reports = pwpa.list_reports()
    except Exception:
        return []
    latest: dict[str, dict] = {}
    for r in reports:
        cur = latest.get(r["ticker"])
        if cur is None or r["date"] > cur["date"]:
            latest[r["ticker"]] = r
    out = []
    for t in tickers:
        if not str(t).endswith(".WA"):
            continue
        base = pwpa._base_ticker(t)
        rep = latest.get(base)
        if rep is None:
            continue
        have = targets.get(base)
        if have and have.get("source_url") == rep["pdf_url"]:
            continue
        if _age_h(failed.get(rep["pdf_url"])) < RETRY_FAILED_DAYS * 24:
            continue
        out.append(base)
    return out


def cell(ticker: str) -> str | None:
    """Tekst do kolumny: '125.00 PLN · 2026-05-22'.

    Stany: cena wyciagnieta / raport bez formalnej ceny docelowej /
    jeszcze nieprzetworzony ('…'). Puste = spolka spoza programu PWPA.
    """
    if not ticker.endswith(".WA"):
        return None
    base = pwpa._base_ticker(ticker)
    entry = load().get("targets", {}).get(base)
    if entry:
        price, curr = entry.get("target_price"), entry.get("currency") or ""
        date = entry.get("date") or ""
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            return f"{price:.2f} {curr} · {date}".replace("  ", " ").strip()
        return f"brak ceny · {date}"
    # brak wpisu — pokazujemy sam fakt pokrycia i date najnowszego raportu
    try:
        reps = pwpa.reports_for(ticker, limit=1)
    except Exception:
        return None
    return f"… · {reps[0]['date']}" if reps else None


def refresh(max_items: int = MAX_PER_RUN, log=None, only=None,
            progress=None) -> dict:
    """Uzupelnia ceny docelowe dla spolek objetych PWPA. Zwraca statystyki.

    only:     lista tickerow do przetworzenia (None = wszystkie objete PWPA).
              Uzywane przez przycisk "wyciagnij dla widocznych spolek".
    progress: callback(i, n, ticker) — do paska postepu w UI.

    Liczy tylko brakujace/nieaktualne wpisy (nowy raport = inny pdf_url).
    Kazdy blad jest lokalny — jedna spolka nie przerywa calosci.
    """
    stats = {"checked": 0, "extracted": 0, "skipped": 0, "errors": 0}
    if not ai_research.available():
        stats["error"] = "brak GEMINI_API_KEY"
        return stats

    data = load(force=True)
    targets, failed = data["targets"], data["failed"]

    try:
        reports = pwpa.list_reports()
    except Exception as e:
        stats["error"] = f"indeks PWPA niedostepny: {e}"
        return stats

    latest: dict[str, dict] = {}
    for r in reports:
        cur = latest.get(r["ticker"])
        if cur is None or r["date"] > cur["date"]:
            latest[r["ticker"]] = r

    wanted = None if only is None else {pwpa._base_ticker(t) for t in only}
    todo = [(tk, rep) for tk, rep in sorted(latest.items())
            if wanted is None or tk in wanted]

    for _i, (tk, rep) in enumerate(todo):
        if stats["extracted"] >= max_items:
            break
        if progress:
            progress(_i, len(todo), tk)
        stats["checked"] += 1
        have = targets.get(tk)
        if have and have.get("source_url") == rep["pdf_url"]:
            stats["skipped"] += 1          # ten sam raport — zero kosztu
            continue
        if _age_h(failed.get(rep["pdf_url"])) < RETRY_FAILED_DAYS * 24:
            stats["skipped"] += 1          # znany nieczytelny PDF
            continue
        try:
            ex = pwpa.extract(rep)
            targets[tk] = {
                "target_price": ex.get("target_price"),
                "currency": ex.get("currency"),
                "recommendation": ex.get("recommendation"),
                "date": rep["date"], "firm": rep["firm"],
                "source_url": rep["pdf_url"], "extracted_at": _iso(),
            }
            failed.pop(rep["pdf_url"], None)
            stats["extracted"] += 1
            if log:
                log(f"{tk}: {ex.get('target_price')} {ex.get('currency') or ''}")
        except Exception as e:
            failed[rep["pdf_url"]] = _iso()
            stats["errors"] += 1
            if log:
                log(f"{tk}: BLAD {e}")
        _save(data)                        # zapis po kazdej spolce — restart
                                           # procesu nie kasuje juz zrobionej pracy
    _save(data)
    return stats


def status() -> str:
    d = load()
    n = len(d.get("targets", {}))
    withp = sum(1 for v in d["targets"].values()
                if isinstance(v.get("target_price"), (int, float)))
    return (f"{withp}/{n} spolek z ceną docelową · odświeżono "
            f"{d.get('updated_at') or 'nigdy'}")


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        print(refresh(max_items=int(sys.argv[sys.argv.index("--refresh") + 1])
                      if len(sys.argv) > sys.argv.index("--refresh") + 1 else 3,
                      log=print))
    else:
        print(status())
        for tk in ("TXT.WA", "11B.WA", "ALR.WA"):
            print(f"  {tk}: {cell(tk)}")

"""Ceny docelowe z raportow GPW PWPA — automatyczna ekstrakcja w tle (24 h).

Kolumna "GPW PWPA" w rankingu pokazuje CENE DOCELOWA i DATE wyceny. Cena
docelowa istnieje wylacznie w tresci PDF raportu maklerskiego, wiec wyciaga
ja AI (pwpa.extract -> pypdf + Gemini). To o wiele za drogo, zeby robic przy
kazdym renderze tabeli, stad ten modul:

  * wyniki trzymamy w JEDNYM malym pliku {ticker: {...}} — nie w 70 osobnych,
  * plik lezy w GISCIE (jak listy obserwacyjne), bo dysk Streamlit Cloud jest
    ulotny: bez tego kazdy redeploy kasowalby wyniki i ekstrakcja ruszalaby
    od zera, palac limit Gemini (~70 zapytan na kazdy deploy),
  * odswiezanie chodzi w WATKU W TLE (nie blokuje UI), najwyzej raz na 24 h,
  * przy odswiezeniu liczymy TYLKO to, co nowe: jesli najnowszy raport spolki
    ma ten sam pdf_url co zapisany wynik, nie ruszamy modelu w ogole.

Watek w tle nie ma ScriptRunContext Streamlita, wiec nie wola st.* — pisze
do pliku, a kolejny rerun po prostu widzi swiezsze dane.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import ai_research
import pwpa
import watchlists

FILE_NAME = "pwpa_targets.json"
TTL_H = 24              # jak czesto wolno odswiezac calosc
MAX_PER_RUN = 70        # twardy limit zapytan do modelu na jeden przebieg
RETRY_FAILED_DAYS = 7   # nieczytelny PDF (skan) — nie probuj codziennie
_MEMO_S = 60            # pamiec podreczna w procesie (Gist to zapytanie HTTP)

_lock = threading.Lock()
_running = False
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


def is_stale(data: dict | None = None) -> bool:
    data = data if data is not None else load()
    return _age_h(data.get("updated_at")) >= TTL_H


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


def refresh(max_items: int = MAX_PER_RUN, log=None) -> dict:
    """Uzupelnia ceny docelowe dla spolek objetych PWPA. Zwraca statystyki.

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

    for tk, rep in sorted(latest.items()):
        if stats["extracted"] >= max_items:
            break
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


def ensure_fresh() -> bool:
    """Startuje odswiezanie w tle, jesli dane sa starsze niz TTL_H.

    Nie blokuje. Zwraca True, jesli watek wystartowal w tym wywolaniu.
    Guard chroni przed zdublowaniem watku przez kolejne reruny Streamlita.
    """
    global _running
    if not ai_research.available():
        return False
    with _lock:
        if _running or not is_stale():
            return False
        _running = True

    def _work():
        global _running
        try:
            refresh()
        except Exception:
            pass
        finally:
            with _lock:
                _running = False

    threading.Thread(target=_work, name="pwpa-targets", daemon=True).start()
    return True


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

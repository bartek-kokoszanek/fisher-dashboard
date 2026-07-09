"""Rekomendacje z Giełdowego Programu Wsparcia Pokrycia Analitycznego (GPW PWPA).

Zrodlo: https://www.gpw.pl/gpwpa — raporty analityczne (PDF) dla ~65 spolek
rynku glownego GPW. Z raportow wyciagamy cene docelowa + uzasadnienie przez AI.

Przeplyw:
  list_reports()  -> lista raportow (data, ticker, nazwa, pdf_url, typ, dom makl.),
                     cache data/pwpa_index.json (12h). Zrodlo: POST ajaxindex.php.
  reports_for(tk) -> raporty dla spolki (ticker bez '.WA'), najnowsze pierwsze.
  extract(rep)    -> {target_price, currency, recommendation, rationale[], ...}
                     z tekstu PDF (pypdf) strukturyzowanego przez Gemini; cache.

UWAGA: PWPA obejmuje tylko czesc GPW (nie Nasdaq). Czesc raportow (komentarz,
analiza wynikow) nie ma formalnej ceny docelowej -> target_price = None.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

import ai_research
import config

BASE = "https://www.gpw.pl"
LIST_URL = f"{BASE}/ajaxindex.php"
INDEX_CACHE = os.path.join(config.CACHE_DIR, "pwpa_index.json")
INDEX_TTL_H = 12

_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/gpwpa",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HDRS)
    try:
        s.get(f"{BASE}/gpwpa", timeout=30)  # cookies
    except Exception:
        pass
    return s


def _clean(html_cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_cell)).strip()


def _fetch_index() -> list[dict]:
    s = _session()
    r = s.post(LIST_URL, timeout=40, data={
        "action": "GPWPWPA", "start": "list", "ajax": 1, "limit": 800, "offset": 0})
    r.raise_for_status()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S)
    out = []
    for row in rows:
        cells = [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 6:
            continue
        date, ticker, name, pdf_file, rtype, firm = cells[:6]
        if not re.match(r"\d{4}-\d{2}-\d{2}", date):
            continue
        out.append({
            "date": date, "ticker": ticker.upper().strip(), "name": name,
            "pdf_url": f"{BASE}/pub/pwpa/{pdf_file}", "type": rtype, "firm": firm,
        })
    return out


def list_reports(force: bool = False) -> list[dict]:
    if not force and os.path.exists(INDEX_CACHE):
        try:
            with open(INDEX_CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = datetime.fromisoformat(cached["fetched_at"])
            if (datetime.now(timezone.utc) - ts).total_seconds() / 3600 <= INDEX_TTL_H:
                return cached["reports"]
        except Exception:
            pass
    reports = _fetch_index()
    if reports:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(INDEX_CACHE, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(),
                       "reports": reports}, f, ensure_ascii=False, indent=2)
    return reports


def _base_ticker(ticker: str) -> str:
    return ticker.replace(".WA", "").upper().strip()


def covered_tickers() -> set[str]:
    return {r["ticker"] for r in list_reports()}


def reports_for(ticker: str, limit: int = 3) -> list[dict]:
    """Najnowsze raporty dla spolki GPW (pusto dla Nasdaq / spoza PWPA)."""
    if not ticker.endswith(".WA"):
        return []
    base = _base_ticker(ticker)
    reps = [r for r in list_reports() if r["ticker"] == base]
    reps.sort(key=lambda r: r["date"], reverse=True)
    return reps[:limit]


# ----------------------------------------------------- ekstrakcja z PDF ---

def _pdf_text(url: str, max_chars: int = 12000) -> str:
    import io

    from pypdf import PdfReader
    s = _session()
    r = s.get(url, timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    parts = []
    for page in reader.pages[:8]:  # cena docelowa jest zwykle na 1-2 stronie
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(len(p) for p in parts) > max_chars:
            break
    return "\n".join(parts)[:max_chars]


def _extract_cache(url: str) -> str:
    hid = hashlib.md5(url.encode()).hexdigest()[:12]
    return os.path.join(config.CACHE_DIR, f"pwpa_{hid}.json")


SYSTEM = ("Jestes analitykiem. Z tekstu raportu maklerskiego wyciagasz konkretne "
          "fakty. Nie zgadujesz — czego nie ma, oznaczasz jako null.")


def extract(report: dict, force: bool = False) -> dict:
    """Zwraca strukture rekomendacji z raportu PWPA (cena docelowa + powody)."""
    path = _extract_cache(report["pdf_url"])
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    text = _pdf_text(report["pdf_url"])
    if len(text.strip()) < 100:
        raise RuntimeError("Nie udalo sie odczytac tekstu z PDF (skan lub blokada).")

    prompt = f"""Oto tekst raportu maklerskiego ({report['firm']}, {report['date']},
spolka {report['name']} [{report['ticker']}]). Wyciagnij fakty i zwroc WYLACZNIE JSON:
{{
  "target_price": <liczba lub null, cena docelowa/wycena za akcje>,
  "currency": "<PLN/EUR/... lub null>",
  "recommendation": "<kupuj/akumuluj/trzymaj/redukuj/sprzedaj/brak — jak w raporcie, lub null>",
  "horizon": "<horyzont ceny docelowej, jesli podany, lub null>",
  "rationale": ["<kluczowy powod 1>", "<powod 2>", "... 3-5 pkt, po polsku"],
  "summary": "<1-2 zdania podsumowania tezy inwestycyjnej>"
}}

TEKST RAPORTU:
{text}"""

    data = ai_research.complete_json(SYSTEM, prompt, max_tokens=2048)
    data["firm"] = report["firm"]
    data["date"] = report["date"]
    data["type"] = report["type"]
    data["source_url"] = report["pdf_url"]
    data["ticker"] = report["ticker"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_extract(url: str) -> dict | None:
    path = _extract_cache(url)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    import sys
    reps = list_reports()
    print(f"raportow w indeksie: {len(reps)} | spolek: {len(covered_tickers())}")
    tk = sys.argv[1] if len(sys.argv) > 1 else "TXT.WA"
    for r in reports_for(tk):
        print(f"  {r['date']} {r['ticker']} {r['type']} — {r['firm']}")
        print(f"     {r['pdf_url']}")

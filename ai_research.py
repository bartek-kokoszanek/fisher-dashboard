"""Jakosciowy research wg Fishera z pomoca modelu LLM.

Punktuje te wymiary Fishera, ktorych NIE ma w danych finansowych:
  - jakosc i uczciwosc zarzadu (pkt 7, 8, 9, 14, 15)
  - przewaga konkurencyjna / fosa (pkt 4, 11)
  - kultura R&D i innowacji (pkt 2, 3)
  - horyzont dlugoterminowy (pkt 12)

Domyslnie uzywa DARMOWEGO Google Gemini przez jego endpoint kompatybilny z OpenAI.
Konfiguracja przez zmienne srodowiskowe:
  - GEMINI_API_KEY (lub LLM_API_KEY) — klucz; darmowy z https://aistudio.google.com/apikey
  - LLM_BASE_URL  — domyslnie endpoint Gemini; mozna przekierowac na Groq/OpenRouter/OpenAI
  - LLM_MODEL     — domyslnie "gemini-flash-latest"

Poniewaz uzywamy klienta OpenAI, ten sam kod dziala z dowolnym providerem
kompatybilnym z OpenAI — wystarczy zmienic LLM_BASE_URL, LLM_MODEL i klucz.
Wyniki cache'owane do data/ai_<ticker>.json.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import config

BASE_URL = os.environ.get(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL = os.environ.get("LLM_MODEL", "gemini-flash-latest")


def _api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")


DIMENSIONS = {
    "management_quality": "Jakosc, glebia i kompetencje zarzadu (pkt 8-9 Fishera)",
    "integrity_candor": "Uczciwosc zarzadu i szczerosc w trudnych czasach (pkt 14-15)",
    "moat": "Trwala przewaga konkurencyjna / fosa (pkt 4, 11)",
    "innovation_rnd": "Kultura innowacji i efektywnosc R&D (pkt 2, 3)",
    "long_term_focus": "Nastawienie dlugoterminowe vs krotkoterminowe (pkt 12)",
}

SYSTEM = (
    "Jestes analitykiem inwestycyjnym stosujacym metode Philipa Fishera "
    "z ksiazki 'Common Stocks and Uncommon Profits'. Oceniasz JAKOSCIOWE "
    "aspekty spolki, ktorych nie widac w liczbach. Badz konkretny, ostrozny "
    "i szczery co do niepewnosci. Jesli czegos nie wiesz, obniz confidence."
)

PROMPT_TMPL = """Ocen spolke: {name} ({ticker}, gielda {market}).

Dla kazdego z ponizszych wymiarow Fishera przyznaj wynik 0-100
(0 = bardzo slabo, 50 = przecietnie, 100 = wybitnie) oraz krotkie uzasadnienie:

{dims}

Zwroc WYLACZNIE poprawny JSON w formacie:
{{
  "scores": {{ "management_quality": <int>, "integrity_candor": <int>,
              "moat": <int>, "innovation_rnd": <int>, "long_term_focus": <int> }},
  "notes": {{ "management_quality": "<1 zdanie>", ... }},
  "summary": "<2-3 zdania podsumowania inwestycyjnego wg Fishera>",
  "confidence": <0-100, jak pewny jestes tej oceny>
}}
Bez tekstu przed ani po JSON."""


def _cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"ai_{ticker.replace('.', '_')}.json")


def available() -> bool:
    return bool(_api_key())


def _extract_json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Brak JSON w odpowiedzi modelu")
    return json.loads(text[start:end + 1])


def research(ticker: str, name: str, market: str, force: bool = False) -> dict:
    path = _cache_path(ticker)
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    key = _api_key()
    if not key:
        raise RuntimeError("Brak GEMINI_API_KEY (ani LLM_API_KEY) w srodowisku.")

    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=BASE_URL)

    dims = "\n".join(f"- {k}: {v}" for k, v in DIMENSIONS.items())
    prompt = PROMPT_TMPL.format(name=name, ticker=ticker, market=market, dims=dims)

    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    text = resp.choices[0].message.content or ""
    data = _extract_json(text)
    data["ticker"] = ticker
    data["model"] = MODEL
    data["researched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # sredni wynik jakosciowy 0-100
    scores = data.get("scores", {})
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    data["quality_score"] = round(sum(vals) / len(vals), 1) if vals else None

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_cached(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(json.dumps(research(tk, config.NAMES.get(tk, tk),
                              config.market_of(tk), force=True),
                     ensure_ascii=False, indent=2))

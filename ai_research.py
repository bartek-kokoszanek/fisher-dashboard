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

PROMPT_TMPL = """Ocen spolke: {name} ({ticker}, gielda {market}).

Dla kazdego z ponizszych wymiarow przyznaj wynik 0-100
(0 = bardzo slabo, 50 = przecietnie, 100 = wybitnie) oraz krotkie uzasadnienie:

{dims}

Nastepnie wypisz najwieksze ZALETY i najwieksze WADY/RYZYKA spolki
(3-6 pozycji kazda, konkretne, po polsku, przez pryzmat Twojej filozofii).

Zwroc WYLACZNIE poprawny JSON w formacie:
{{
  "scores": {{ "management_quality": <int>, "integrity_candor": <int>,
              "moat": <int>, "innovation_rnd": <int>, "long_term_focus": <int> }},
  "notes": {{ "management_quality": "<1 zdanie>", ... }},
  "strengths": ["<konkretna zaleta>", "..."],
  "weaknesses": ["<konkretna wada lub ryzyko>", "..."],
  "summary": "<2-3 zdania podsumowania inwestycyjnego>",
  "confidence": <0-100, jak pewny jestes tej oceny>
}}
Bez tekstu przed ani po JSON."""


def friendly_429(e: Exception) -> str | None:
    """Czytelny komunikat PL dla przekroczonego limitu darmowego Gemini."""
    s = str(e)
    if "429" in s or "RESOURCE_EXHAUSTED" in s or "rate limit" in s.lower():
        return ("Wyczerpany darmowy limit Gemini (na minute lub na dzien). "
                "Odczekaj ~1 minute i sprobuj ponownie. Limit dzienny odnawia "
                "sie o polnocy czasu pacyficznego (ok. 9:00 rano w Polsce).")
    return None


def _cache_path(ticker: str, guru: str = "fisher") -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR,
                        f"ai_{guru}_{ticker.replace('.', '_')}.json")


def _legacy_path(ticker: str) -> str:
    # pliki sprzed strategii guru (traktowane jako Fisher)
    return os.path.join(config.CACHE_DIR, f"ai_{ticker.replace('.', '_')}.json")


def available() -> bool:
    return bool(_api_key())


def _loads_lenient(s: str) -> dict:
    """json.loads odporne na typowe usterki LLM (brak/nadmiar przecinkow).

    Dekoder podaje dokladna pozycje brakujacego przecinka, wiec wstawiamy go
    tam i ponawiamy. Dodatkowo usuwamy trailing commas przed } / ].
    """
    import re
    s = re.sub(r",(\s*[}\]])", r"\1", s)  # trailing commas
    for _ in range(60):
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            if "Expecting ',' delimiter" in e.msg and 0 < e.pos <= len(s):
                s = s[:e.pos] + "," + s[e.pos:]
                continue
            raise
    return json.loads(s)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    # model czasem owija JSON w ```json ... ``` — utnij ploty
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Brak JSON w odpowiedzi modelu")
    return _loads_lenient(text[start:end + 1])


def research(ticker: str, name: str, market: str, guru: str = "fisher",
             force: bool = False) -> dict:
    import gurus

    path = _cache_path(ticker, guru)
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
    system = gurus.system_prompt(guru)

    def _call(json_mode: bool):
        kwargs = dict(
            model=MODEL,
            # Modele Gemini "mysla" — rozumowanie tez zuzywa max_tokens. Za niski
            # limit konczyl sie pustym contentem ("Brak JSON"). Stad duzy limit
            # i reasoning_effort=low.
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            extra_body={"reasoning_effort": "low"},
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    try:
        resp = _call(json_mode=True)
    except Exception as e:
        msg = friendly_429(e)
        if not msg:
            raise
        # limit minutowy? jedna proba ponowienia po 20 s
        import time
        time.sleep(20)
        try:
            resp = _call(json_mode=True)
        except Exception as e2:
            raise RuntimeError(friendly_429(e2) or str(e2)) from e2
    text = resp.choices[0].message.content or ""
    if not text.strip():
        # retry bez wymuszonego JSON — niektore modele zwracaja pusto z json_object
        resp = _call(json_mode=False)
        text = resp.choices[0].message.content or ""
    if not text.strip():
        fr = getattr(resp.choices[0], "finish_reason", "?")
        raise RuntimeError(
            f"Model zwrocil pusta odpowiedz (finish_reason={fr}, model={MODEL}). "
            "Sprobuj ponownie lub ustaw inny model przez LLM_MODEL."
        )
    data = _extract_json(text)
    data["ticker"] = ticker
    data["guru"] = guru
    data["model"] = MODEL
    data["researched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # sredni wynik jakosciowy 0-100
    scores = data.get("scores", {})
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    data["quality_score"] = round(sum(vals) / len(vals), 1) if vals else None

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_cached(ticker: str, guru: str = "fisher") -> dict | None:
    path = _cache_path(ticker, guru)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    if guru == "fisher":  # migracja: stare pliki sprzed strategii
        legacy = _legacy_path(ticker)
        if os.path.exists(legacy):
            with open(legacy, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    guru = sys.argv[2] if len(sys.argv) > 2 else "fisher"
    print(json.dumps(research(tk, config.NAMES.get(tk, tk),
                              config.market_of(tk), guru=guru, force=True),
                     ensure_ascii=False, indent=2))

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


def _keys() -> list[str]:
    """Wszystkie dostepne klucze Gemini w kolejnosci prob (z deduplikacja).

    Zrodla: GEMINI_API_KEYS (lista po przecinku), GEMINI_API_KEY,
    GEMINI_API_KEY_2.._5, LLM_API_KEY. Rozne klucze = niezalezne darmowe pule,
    wiec przy limicie 429 rotujemy na kolejny.
    """
    raw = []
    raw += [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",")]
    raw.append(os.environ.get("GEMINI_API_KEY", ""))
    for i in range(2, 6):
        raw.append(os.environ.get(f"GEMINI_API_KEY_{i}", ""))
    raw.append(os.environ.get("LLM_API_KEY", ""))
    seen, out = set(), []
    for k in raw:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _api_key() -> str | None:
    keys = _keys()
    return keys[0] if keys else None


def key_count() -> int:
    return len(_keys())


# Domyslny lancuch modeli do rotacji. Kazdy model ma OSOBNA darmowa pule limitow,
# wiec przy 429 przechodzimy do kolejnego -> sumujemy niezalezne pule.
DEFAULT_CHAIN = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _models(primary: str, extra_default: list[str] | None = None) -> list[str]:
    """Lista modeli do rotacji. Env LLM_MODELS (po przecinku) nadpisuje domyslny
    lancuch [primary] + tansze modele fallback."""
    override = os.environ.get("LLM_MODELS", "")
    if override.strip():
        return _dedup(override.split(","))
    return _dedup([primary] + (extra_default if extra_default is not None
                               else DEFAULT_CHAIN))


def models_active() -> list[str]:
    return _models(MODEL)


def _is_transient(e) -> bool:
    """Przejsciowy blad serwera (503/500/przeciazenie) — warto ponowic ten sam klucz."""
    s = str(e).lower()
    return any(x in s for x in ("503", "500", "unavailable", "overloaded",
                                "high demand", "try again later", "internal error"))


def _with_rotation(fn, models=None):
    """Wywoluje fn(key, model) dla kombinacji MODEL × KLUCZ, odpornie na bledy.

    Kazdy model i kazdy klucz ma osobna pule limitow -> przy 429 przechodzimy
    do kolejnej kombinacji (najpierw wszystkie klucze danego modelu, potem
    nastepny model). To sumuje niezalezne pule.
    - Przejsciowy blad 503 -> retry tej samej kombinacji z backoff (2 proby).
    - 429 -> nastepna kombinacja. Inny blad -> od razu przekazany.
    """
    import time
    keys = _keys()
    if not keys:
        raise RuntimeError("Brak GEMINI_API_KEY (ani LLM_API_KEY) w srodowisku.")
    models = models or _models(MODEL)
    combos = [(m, k) for m in models for k in keys]

    last_err, last_transient = None, False
    for idx, (model, key) in enumerate(combos):
        for attempt in range(3):  # retry przejsciowych bledow na tej kombinacji
            try:
                return fn(key, model)
            except Exception as e:
                if _is_transient(e) and attempt < 2:
                    last_err, last_transient = e, True
                    time.sleep(3 * (attempt + 1))  # 3 s, 6 s
                    continue
                if friendly_429(e):
                    last_err, last_transient = e, False
                    if idx == len(combos) - 1:  # ostatnia kombinacja: proba po 20 s
                        time.sleep(20)
                        try:
                            return fn(key, model)
                        except Exception as e2:
                            last_err = e2
                    break  # nastepna kombinacja (model/klucz)
                if _is_transient(e):
                    last_err, last_transient = e, True
                    break
                raise  # inny, trwaly blad
    if last_transient:
        raise RuntimeError(
            "Serwer Gemini jest chwilowo przeciazony (503). To przejsciowe — "
            "sprobuj ponownie za chwile.")
    raise RuntimeError(
        f"Wyczerpano limity wszystkich modeli ({len(models)}) i kluczy "
        f"({len(keys)}). " + (friendly_429(last_err) or "Limit Gemini wyczerpany.")
    )


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


def complete_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    """Uniwersalne wywolanie modelu zwracajacego JSON (odporne na 429 i usterki).

    Uzywane m.in. przez modul Financial Charts. Rzuca czytelny blad przy limicie.
    """
    from openai import OpenAI

    def _do(key: str, model: str) -> str:
        client = OpenAI(api_key=key, base_url=BASE_URL)

        def _call(json_mode: bool):
            kwargs = dict(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                extra_body={"reasoning_effort": "low"},
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            return client.chat.completions.create(**kwargs)

        resp = _call(True)
        text = resp.choices[0].message.content or ""
        if not text.strip():
            resp = _call(False)
            text = resp.choices[0].message.content or ""
        return text

    return _extract_json(_with_rotation(_do))


def research(ticker: str, name: str, market: str, guru: str = "fisher",
             force: bool = False) -> dict:
    import gurus

    path = _cache_path(ticker, guru)
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    from openai import OpenAI

    dims = "\n".join(f"- {k}: {v}" for k, v in DIMENSIONS.items())
    prompt = PROMPT_TMPL.format(name=name, ticker=ticker, market=market, dims=dims)
    system = gurus.system_prompt(guru)

    used = {"model": MODEL}

    def _do(key: str, model: str) -> str:
        used["model"] = model
        client = OpenAI(api_key=key, base_url=BASE_URL)

        def _call(json_mode: bool):
            kwargs = dict(
                model=model,
                # Modele Gemini "mysla" — rozumowanie tez zuzywa max_tokens.
                # Za niski limit konczyl sie pustym contentem. Stad duzy limit.
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

        resp = _call(json_mode=True)
        text = resp.choices[0].message.content or ""
        if not text.strip():
            resp = _call(json_mode=False)
            text = resp.choices[0].message.content or ""
        if not text.strip():
            fr = getattr(resp.choices[0], "finish_reason", "?")
            raise RuntimeError(
                f"Model zwrocil pusta odpowiedz (finish_reason={fr}, model={model}). "
                "Sprobuj ponownie lub ustaw inny model przez LLM_MODEL.")
        return text

    data = _extract_json(_with_rotation(_do))
    data["ticker"] = ticker
    data["guru"] = guru
    data["model"] = used["model"]
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

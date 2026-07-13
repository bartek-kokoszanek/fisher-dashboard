"""Agent: analiza filmow z YouTube o spolce (napisy albo odsluch przez Gemini).

Przeplyw dla wybranego filmu:
  1. NAPISY (szybkie i tanie) — youtube-transcript-api; gdy dostepne,
     analizujemy tekst zwyklym modelem.
  2. Gdy napisow brak — wysylamy URL filmu do GEMINI, ktory OGLADA/ODSLUCHUJE
     film po swojej stronie (video understanding, file_uri). Dziala takze
     z serwerow chmurowych, bo to Google pobiera film — nasz serwer nie
     dotyka YouTube (rozwiazuje blokade IP, ktora psula stare audio-STT).

Lista filmow: yt_transcribe.find_videos -> research_deep (oficjalne YouTube
Data API v3 przy YOUTUBE_API_KEY — kilka zapytan PL/EN, ostatnie 12 miesiecy;
fallback yt-dlp lokalnie).

Wyniki cache'owane w data/ytt_<video_id>.json. Klucze/rotacja jak w ai_research.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import ai_research
import config
import research_deep

MAX_MINUTES = 60          # dluzsze filmy pomijamy (tokeny/limity darmowego tieru)
TRANSCRIPT_CHARS = 12000
VIDEO_MONTHS = 12         # lista filmow: ostatnie 12 miesiecy
STT_MODEL = os.environ.get("STT_MODEL", os.environ.get("DEEP_MODEL", "gemini-flash-latest"))


def available() -> bool:
    return ai_research.available()


def _cache_path(video_id: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"ytt_{video_id}.json")


def load_cached(video_id: str) -> dict | None:
    p = _cache_path(video_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ----------------------------------------------------- wyszukiwanie ---

def find_videos(name: str, ticker: str, market: str) -> list[dict]:
    """Filmy o spolce z ostatnich VIDEO_MONTHS miesiecy.

    Oficjalne YouTube Data API (bogata lista, dziala z chmury), fallback
    yt-dlp przez research_deep.yt_research.
    """
    yt = research_deep.yt_research(name, ticker, market, months=VIDEO_MONTHS)
    return yt.get("videos", [])


def videos_note() -> str | None:
    """Podpowiedz dla UI, gdy lista filmow moze byc uboga."""
    if research_deep._yt_api_key():
        return None
    return ("Lista filmów działa teraz przez yt-dlp, który bywa blokowany na "
            "serwerach chmurowych. Dodaj darmowy **YOUTUBE_API_KEY** "
            "(Google Cloud → YouTube Data API v3) w Secrets — lista będzie "
            "bogatsza (kilka zapytań PL/EN, 12 miesięcy) i niezawodna.")


# ----------------------------------------------------- analiza ---

SYSTEM = ("Jestes analitykiem inwestycyjnym. Na podstawie filmu/transkrypcji "
          "wyciagasz to, co dotyczy KONKRETNEJ spolki. Ignorujesz dygresje "
          "i tresci reklamowe. Piszesz po polsku.")

_JSON_SCHEMA = """{{
  "key_points": ["<najwazniejsze tezy o spolce, 3-6 pkt>"],
  "claims_about_company": ["<konkretne stwierdzenia/fakty padajace w filmie>"],
  "sentiment": <int -100..100 wobec spolki>,
  "thesis": "<teza inwestycyjna autora, 1-2 zdania, lub 'brak'>",
  "risks": ["<wymienione ryzyka, jesli sa>"],
  "speaker_stance": "<byk/niedzwiedz/neutralny>",
  "transcript_excerpt": "<2-4 doslowne, najwazniejsze cytaty z filmu>"
}}"""


def analyze(transcript: str, name: str, ticker: str) -> dict:
    """Analiza gotowego transkryptu (sciezka: napisy)."""
    prompt = f"""Transkrypcja filmu o spolce {name} ({ticker}). Wyciagnij wnioski
dotyczace TEJ spolki i zwroc WYLACZNIE JSON:
{_JSON_SCHEMA}

TRANSKRYPCJA:
{transcript}"""
    return ai_research.complete_json(SYSTEM, prompt, max_tokens=2048)


def analyze_video_url(url: str, name: str, ticker: str) -> dict:
    """Gemini oglada/odsluchuje film bezposrednio z URL (video understanding).

    Google pobiera film po swojej stronie — dziala z chmury bez proxy.
    Niska rozdzielczosc medialna ogranicza zuzycie tokenow (liczy sie audio).
    """
    from google import genai
    from google.genai import types

    prompt = f"""{SYSTEM}

Obejrzyj/odsluchaj ten film o spolce {name} ({ticker}). Wyciagnij wnioski
dotyczace TEJ spolki i zwroc WYLACZNIE JSON:
{_JSON_SCHEMA}"""

    # niska rozdzielczosc medialna = mniej tokenow (liczy sie glownie audio);
    # konstrukcja configu osobno, by starsze SDK bez tego pola nie wywracaly
    # samego wywolania
    try:
        _cfg = types.GenerateContentConfig(
            media_resolution="MEDIA_RESOLUTION_LOW")
    except Exception:
        _cfg = None

    def _do(key: str, model: str) -> str:
        client = genai.Client(api_key=key)
        contents = types.Content(parts=[
            types.Part(file_data=types.FileData(file_uri=url)),
            types.Part(text=prompt),
        ])
        kwargs = {"config": _cfg} if _cfg is not None else {}
        resp = client.models.generate_content(model=model, contents=contents,
                                              **kwargs)
        return resp.text or ""

    # wideo wspieraja modele Flash (bez Lite)
    models = ai_research._models(STT_MODEL, ["gemini-2.5-flash"])
    text = ai_research._with_rotation(_do, models=models)
    return research_deep._extract_json(text)


def run(video: dict, name: str, ticker: str, force: bool = False) -> dict:
    """Pelny przeplyw dla jednego filmu: napisy -> analiza tekstu, a gdy
    napisow brak -> Gemini oglada film z URL. Wynik z cache."""
    vid = video["id"]
    url = f"https://www.youtube.com/watch?v={vid}"
    if not force:
        cached = load_cached(vid)
        if cached:
            return cached

    caps = research_deep._yt_transcript(vid)
    if caps and len(caps) > 200:
        data = analyze(caps[:TRANSCRIPT_CHARS], name, ticker)
        source = "napisy"
        excerpt = data.pop("transcript_excerpt", "") or caps[:1500]
    else:
        minutes = video.get("minutes")
        if minutes and minutes > MAX_MINUTES:
            raise RuntimeError(
                f"Film trwa {minutes:.0f} min (limit {MAX_MINUTES} min) — "
                "za dlugi na analize w darmowym tierze. Wybierz krotszy film.")
        data = analyze_video_url(url, name, ticker)
        source = "Gemini (odsłuch filmu z URL)"
        excerpt = data.pop("transcript_excerpt", "") or ""

    data["video_id"] = vid
    data["title"] = video.get("title")
    data["channel"] = video.get("channel")
    data["date"] = video.get("date")
    data["url"] = url
    data["transcript_source"] = source
    data["transcript_excerpt"] = excerpt
    data["analyzed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(_cache_path(vid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    vids = find_videos(config.NAMES.get(tk, tk), tk, config.market_of(tk))
    print(f"znaleziono {len(vids)} filmow")
    for v in vids[:8]:
        mins = f"{v['minutes']:.0f} min" if v.get("minutes") else "?"
        print(f"  {v['date']} [{mins}] {str(v['title'])[:60]}")
    if vids and "--analyze" in sys.argv:
        print(json.dumps(run(vids[0], config.NAMES.get(tk, tk), tk, force=True),
                         ensure_ascii=False, indent=2))

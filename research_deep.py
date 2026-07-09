"""Deep research spolki: YouTube + sentyment z artykulow + relacje inwestorskie.

Trzy zrodla (wszystkie darmowe):
  A. YouTube — yt-dlp wyszukuje filmy o spolce z ostatnich ~6 miesiecy
     (tytul, kanal, data), a youtube-transcript-api probuje pobrac transkrypty
     kilku najnowszych. UWAGA: na serwerach chmurowych YouTube czesto blokuje
     pobieranie transkryptow — wtedy zostaja metadane + wyszukiwarka Google.
  B. Artykuly / sentyment — Gemini z narzedziem Google Search (grounding,
     w darmowym tierze) przeszukuje swieze artykuly i ocenia sentyment rynku.
  C. Relacje inwestorskie — grounding szuka raportow na stronie IR spolki
     (domena z yfinance).

Wymaga GEMINI_API_KEY (grounding dziala tylko z Gemini — niezaleznie od tego,
na jakiego providera przekierowano szybki research w ai_research.py).
Model: env DEEP_MODEL, domyslnie gemini-flash-latest.
Cache: data/deep_<ticker>.json. Sentyment NIE wplywa na Wynik Fishera.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import config

DEEP_MODEL = os.environ.get("DEEP_MODEL", "gemini-flash-latest")
MONTHS_BACK = 6
MAX_TRANSCRIPTS = 3
TRANSCRIPT_CHARS = 4000


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"deep_{ticker.replace('.', '_')}.json")


def load_cached(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------- YouTube ---

def _yt_transcript(video_id: str) -> str | None:
    """Transkrypt filmu (pl/en) albo None. Fail-soft — chmura bywa blokowana."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:  # API >= 1.0
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=["pl", "en"])
            text = " ".join(s.text for s in fetched)
        except AttributeError:  # starsze API
            segs = YouTubeTranscriptApi.get_transcript(video_id, languages=["pl", "en"])
            text = " ".join(s["text"] for s in segs)
        return text[:TRANSCRIPT_CHARS]
    except Exception:
        return None


def yt_research(name: str, ticker: str, market: str) -> dict:
    """Filmy o spolce z ostatnich MONTHS_BACK miesiecy + transkrypty (best-effort)."""
    out = {"videos": [], "transcripts": {}, "note": None}
    try:
        from yt_dlp import YoutubeDL
    except Exception as e:
        out["note"] = f"yt-dlp niedostepny: {e}"
        return out

    query = (f"{name} akcje analiza" if market == "GPW"
             else f"{name} {ticker} stock analysis")
    cutoff = datetime.now(timezone.utc) - timedelta(days=MONTHS_BACK * 30)

    flat_opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                 "skip_download": True, "noprogress": True}
    try:
        with YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(f"ytsearch12:{query}", download=False)
        entries = [e for e in (info.get("entries") or []) if e]
    except Exception as e:
        out["note"] = f"Wyszukiwanie YouTube nie powiodlo sie: {e}"
        return out

    # plaskie wyniki nie maja daty publikacji — dociagamy metadane top wynikow
    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                 "noprogress": True}
    checked = 0
    for e in entries:
        if checked >= 8 or len(out["videos"]) >= 6:
            break
        vid = e.get("id")
        if not vid:
            continue
        checked += 1
        try:
            with YoutubeDL(full_opts) as ydl:
                meta = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}",
                                        download=False)
        except Exception:
            continue
        ud = meta.get("upload_date")  # "YYYYMMDD"
        if not ud:
            continue
        dt = datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc)
        if dt < cutoff:
            continue
        out["videos"].append({
            "id": vid,
            "title": meta.get("title"),
            "channel": meta.get("channel") or meta.get("uploader"),
            "date": dt.date().isoformat(),
            "views": meta.get("view_count"),
        })

    for v in out["videos"][:MAX_TRANSCRIPTS]:
        t = _yt_transcript(v["id"])
        if t:
            out["transcripts"][v["id"]] = t
    if out["videos"] and not out["transcripts"]:
        out["note"] = ("Transkrypty niedostepne (typowe na serwerach w chmurze) — "
                       "analiza oparta o tytuly filmow i wyszukiwarke.")
    return out


# ----------------------------------------------------------------- Gemini ---

def _extract_json(text: str) -> dict:
    from ai_research import _loads_lenient
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Brak JSON w odpowiedzi modelu")
    return _loads_lenient(text[start:end + 1])


PROMPT = """Jestes analitykiem inwestycyjnym. Zbadaj AKTUALNY (ostatnie {months} miesiecy,
dzis jest {today}) obraz spolki {name} ({ticker}, gielda {market}) w trzech obszarach.
Uzyj wyszukiwarki Google, by znalezc swieze zrodla:

1. SENTYMENT RYNKU: przejrzyj najnowsze artykuly, analizy i komentarze o spolce.
   Ocen wypadkowy sentyment rynku w skali od -100 (skrajnie negatywny) do +100
   (skrajnie pozytywny). Uwzglednij powody (wyniki, guidance, rekomendacje, ryzyka).

2. RELACJE INWESTORSKIE: poszukaj najnowszych raportow i komunikatow spolki
   (strona IR{website_hint}, raporty kwartalne/polroczne z ostatnich {months} miesiecy).
   Streszcz najwazniejsze fakty: wyniki, prognozy, dywidendy/buybacki, zmiany w zarzadzie.

3. YOUTUBE: ponizej metadane{transcript_note} filmow z YouTube o spolce z ostatnich
   {months} miesiecy. Wyciagnij z nich glowne tezy i nastroje tworcow.

{yt_section}

Zwroc WYLACZNIE poprawny JSON (bez tekstu przed/po):
{{
  "sentiment": <int -100..100>,
  "sentiment_summary": "<3-4 zdania: wypadkowy sentyment i dlaczego>",
  "key_news": [{{"title": "<naglowek>", "date": "<YYYY-MM lub przyblizona>", "takeaway": "<1 zdanie>"}}],
  "ir_findings": "<3-5 zdan: co wynika z raportow/komunikatow IR>",
  "youtube_findings": [{{"title": "<tytul>", "channel": "<kanal>", "date": "<data>", "takeaway": "<1 zdanie>"}}],
  "confidence": <0-100>
}}"""


def research(ticker: str, name: str, market: str, website: str | None = None,
             force: bool = False) -> dict:
    path = _cache_path(ticker)
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    import ai_research
    if not ai_research.available():
        raise RuntimeError("Deep research wymaga GEMINI_API_KEY.")

    yt = yt_research(name, ticker, market)

    yt_lines = []
    for v in yt["videos"]:
        line = f"- [{v['date']}] \"{v['title']}\" (kanal: {v['channel']}, {v.get('views') or '?'} wyswietlen)"
        yt_lines.append(line)
        if v["id"] in yt["transcripts"]:
            yt_lines.append(f"  Transkrypt (fragment): {yt['transcripts'][v['id']]}")
    yt_section = "\n".join(yt_lines) if yt_lines else \
        "(Brak wynikow z YouTube — poszukaj opinii o spolce w wyszukiwarce, w tym na youtube.com)"

    prompt = PROMPT.format(
        months=MONTHS_BACK,
        today=datetime.now(timezone.utc).date().isoformat(),
        name=name, ticker=ticker, market=market,
        website_hint=f", prawdopodobnie {website}" if website else "",
        transcript_note=" i transkrypty" if yt["transcripts"] else "",
        yt_section=yt_section,
    )

    from google import genai
    from google.genai import types

    def _generate(key: str):
        client = genai.Client(api_key=key)
        return client.models.generate_content(
            model=DEEP_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                # UWAGA: grounding nie laczy sie z wymuszonym JSON
                # (response_mime_type) — JSON egzekwujemy promptem
                # i parsujemy defensywnie.
            ),
        )

    # rotacja kluczy przy 429 (grounding ma osobny, ciasniejszy limit darmowy)
    resp = ai_research._with_rotation(_generate)

    data = _extract_json(resp.text or "")

    # zrodla z metadanych groundingu
    sources = []
    try:
        for cand in resp.candidates or []:
            gm = getattr(cand, "grounding_metadata", None)
            for ch in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(ch, "web", None)
                if web and web.uri:
                    sources.append({"title": web.title or web.uri, "url": web.uri})
    except Exception:
        pass
    data["sources"] = sources[:15]
    data["yt_note"] = yt.get("note")
    data["ticker"] = ticker
    data["model"] = DEEP_MODEL
    data["researched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    if "--yt-only" in sys.argv:
        print(json.dumps(yt_research(config.NAMES.get(tk, tk), tk,
                                     config.market_of(tk)),
                         ensure_ascii=False, indent=2)[:3000])
    else:
        print(json.dumps(research(tk, config.NAMES.get(tk, tk),
                                  config.market_of(tk), force=True),
                         ensure_ascii=False, indent=2))

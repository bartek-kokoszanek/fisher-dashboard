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
    # te same zrodla kluczy co ai_research (GEMINI_API_KEY/KEYS/_2.., LLM_API_KEY)
    import ai_research
    return ai_research.available()


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

def _yt_api_key() -> str | None:
    return os.environ.get("YOUTUBE_API_KEY", "").strip() or None


def _parse_iso_duration(s: str | None) -> float:
    """ISO-8601 'PT1H2M3S' -> minuty (YouTube Data API, contentDetails)."""
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0.0
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 60 + mi + se / 60


def yt_search_api(name: str, ticker: str, market: str,
                  months: int = MONTHS_BACK) -> list[dict]:
    """Filmy o spolce przez OFICJALNE YouTube Data API v3 (env YOUTUBE_API_KEY).

    Dziala niezawodnie z serwerow chmurowych (w przeciwienstwie do yt-dlp,
    ktore YouTube blokuje po IP). Kilka zapytan (PL/EN, rozne ujecia) daje
    bogatsza liste; wyniki laczone i deduplikowane. Koszt: ~100 jednostek
    na zapytanie przy darmowym limicie 10 000/dobe — wyniki cache'uje UI.
    Odfiltrowuje Shorts (<2 min).
    """
    import requests

    key = _yt_api_key()
    if not key:
        raise RuntimeError("Brak YOUTUBE_API_KEY.")
    after = (datetime.now(timezone.utc)
             - timedelta(days=months * 30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if market == "GPW":
        queries = [(f"{name} akcje", "relevance"),
                   (f"{name} analiza", "relevance"),
                   (f"{name} wyniki", "date"),
                   (f"{name} GPW", "date")]
    else:
        queries = [(f"{name} stock analysis", "relevance"),
                   (f"{ticker} stock", "date"),
                   (f"{name} earnings", "relevance"),
                   (f"{name} stock news", "date")]

    seen: dict[str, dict] = {}
    for q, order in queries:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "q": q, "type": "video",
                        "order": order, "publishedAfter": after,
                        "maxResults": 15, "key": key},
                timeout=30)
            r.raise_for_status()
            items = r.json().get("items", [])
        except Exception:
            continue  # pojedyncze zapytanie moze pasc (limit) — bierz reszte
        for it in items:
            vid = (it.get("id") or {}).get("videoId")
            sn = it.get("snippet") or {}
            if vid and vid not in seen:
                seen[vid] = {"id": vid, "title": sn.get("title"),
                             "channel": sn.get("channelTitle"),
                             "date": (sn.get("publishedAt") or "")[:10],
                             "views": None, "minutes": None}
    if not seen:
        return []

    # szczegoly: dlugosc + wyswietlenia (1 jednostka na 50 filmow)
    ids = list(seen)
    for i in range(0, len(ids), 50):
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "contentDetails,statistics",
                        "id": ",".join(ids[i:i + 50]), "key": key},
                timeout=30)
            r.raise_for_status()
            for it in r.json().get("items", []):
                v = seen.get(it["id"])
                if v is None:
                    continue
                v["minutes"] = _parse_iso_duration(
                    (it.get("contentDetails") or {}).get("duration"))
                try:
                    v["views"] = int((it.get("statistics") or {})
                                     .get("viewCount") or 0)
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass

    videos = [v for v in seen.values()
              if v.get("minutes") is None or 2 <= v["minutes"] <= 240]
    videos.sort(key=lambda v: v.get("date") or "", reverse=True)
    return videos[:30]


def _yt_transcript(video_id: str) -> str | None:
    """Transkrypt filmu (pl/en) albo None. Fail-soft — chmura bywa blokowana.

    Uzywa proxy z YT_PROXY, gdy ustawione (obejscie blokady IP na Streamlit Cloud).
    """
    proxy = os.environ.get("YT_PROXY") or None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:  # API >= 1.0 (opcjonalne proxy_config)
            kwargs = {}
            if proxy:
                try:
                    from youtube_transcript_api.proxies import GenericProxyConfig
                    kwargs["proxy_config"] = GenericProxyConfig(
                        http_url=proxy, https_url=proxy)
                except Exception:
                    pass
            fetched = YouTubeTranscriptApi(**kwargs).fetch(
                video_id, languages=["pl", "en"])
            text = " ".join(s.text for s in fetched)
        except AttributeError:  # starsze API
            segs = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["pl", "en"],
                proxies=({"http": proxy, "https": proxy} if proxy else None))
            text = " ".join(s["text"] for s in segs)
        return text[:TRANSCRIPT_CHARS]
    except Exception:
        return None


def yt_research(name: str, ticker: str, market: str,
                months: int = MONTHS_BACK) -> dict:
    """Filmy o spolce z ostatnich `months` miesiecy + transkrypty (best-effort).

    Wyszukiwanie: najpierw oficjalne YouTube Data API (YOUTUBE_API_KEY —
    dziala z chmury, kilka zapytan = bogatsza lista), fallback yt-dlp
    (dziala lokalnie; na serwerach czesto blokowany po IP).
    """
    out = {"videos": [], "transcripts": {}, "note": None}

    if _yt_api_key():
        try:
            out["videos"] = yt_search_api(name, ticker, market, months)
        except Exception as e:
            out["note"] = f"YouTube Data API nie powiodlo sie: {e}"
    if out["videos"]:
        for v in out["videos"][:MAX_TRANSCRIPTS]:
            t = _yt_transcript(v["id"])
            if t:
                out["transcripts"][v["id"]] = t
        return out

    try:
        from yt_dlp import YoutubeDL
    except Exception as e:
        out["note"] = f"yt-dlp niedostepny: {e}"
        return out

    query = (f"{name} akcje analiza" if market == "GPW"
             else f"{name} {ticker} stock analysis")
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

    flat_opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                 "skip_download": True, "noprogress": True}
    try:
        with YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(f"ytsearch30:{query}", download=False)
        entries = [e for e in (info.get("entries") or []) if e]
    except Exception as e:
        out["note"] = ("Wyszukiwanie YouTube nie powiodlo sie (yt-dlp bywa "
                       "blokowany z serwerow). Dodaj YOUTUBE_API_KEY w Secrets "
                       f"— oficjalne API dziala z chmury. Blad: {e}")
        return out

    # plaskie wyniki nie maja daty publikacji — dociagamy metadane
    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                 "noprogress": True}
    checked = 0
    for e in entries:
        # sprawdzamy wiecej wynikow, by zlapac WSZYSTKIE z ostatnich 6 mies.
        if checked >= 30 or len(out["videos"]) >= 25:
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

    # od najnowszego do najstarszego
    out["videos"].sort(key=lambda v: v["date"], reverse=True)

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
    for v in yt["videos"][:8]:  # do promptu bierzemy najnowsze 8 (pelna lista -> UI)
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

    used = {"model": DEEP_MODEL}

    def _generate(key: str, model: str):
        used["model"] = model
        client = genai.Client(api_key=key)
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                # UWAGA: grounding nie laczy sie z wymuszonym JSON
                # (response_mime_type) — JSON egzekwujemy promptem
                # i parsujemy defensywnie.
            ),
        )

    # rotacja modeli × kluczy (grounding: tylko Flash, bez Lite)
    resp = ai_research._with_rotation(
        _generate, models=ai_research._models(DEEP_MODEL, ["gemini-2.5-flash"]))

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


# ------------------------------------------------------ dywidenda (grounding) ---

DIV_PROMPT = """Znajdz w internecie (wyszukiwarka Google) informacje o OSTATNIEJ
wyplaconej dywidendzie spolki {name} ({ticker}, gielda {market}). Dzis jest {today}.

Interesuja mnie fakty z BIEZACEGO roku ({year}), a jesli w tym roku spolka jeszcze
nie wyplacala/nie ustalila dywidendy — z roku poprzedniego ({prev}).

Szukaj w wiarygodnych zrodlach: komunikaty spolki (ESPI/relacje inwestorskie),
gpw.pl, serwisy gieldowe (np. Bankier, Stooq, StockWatch, Strefa Inwestorow).

Zwroc WYLACZNIE poprawny JSON (bez tekstu przed/po). Pola, ktorych NIE udalo Ci sie
potwierdzic w zrodlach, ustaw na null — NIE zgaduj:
{{
  "amount": <kwota dywidendy na 1 akcje, liczba, lub null>,
  "currency": "<PLN/USD lub null>",
  "ex_date": "<YYYY-MM-DD: dzien odciecia prawa do dywidendy / ostatni dzien
               z prawem — dzien ustalenia prawa, lub null>",
  "pay_date": "<YYYY-MM-DD: dzien wyplaty dywidendy na rachunek, lub null>",
  "year": <rok, ktorego dotyczy wyplata>,
  "note": "<1-2 zdania po polsku: czego dotyczy wyplata i co ustalono>",
  "confidence": <0-100>
}}"""


def _div_cache_path(ticker: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"div_{ticker.replace('.', '_')}.json")


def load_dividend_details(ticker: str) -> dict | None:
    p = _div_cache_path(ticker)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def dividend_details(ticker: str, name: str, market: str,
                     force: bool = False) -> dict:
    """Szczegoly ostatniej dywidendy przez Gemini + Google Search (grounding).

    Uzupelnia luke w danych Yahoo: dzien WYPLATY dywidendy, ktorego dla
    wiekszosci spolek GPW Yahoo nie publikuje. Wynik zawsze ze zrodlami
    (grounding_chunks) — do weryfikacji przez uzytkownika. Cache: data/div_*.
    """
    path = _div_cache_path(ticker)
    if not force and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    import ai_research
    if not ai_research.available():
        raise RuntimeError("Wyszukiwanie dywidendy wymaga GEMINI_API_KEY.")

    from google import genai
    from google.genai import types

    today = datetime.now(timezone.utc).date()
    prompt = DIV_PROMPT.format(name=name, ticker=ticker, market=market,
                               today=today.isoformat(), year=today.year,
                               prev=today.year - 1)

    def _generate(key: str, model: str):
        client = genai.Client(api_key=key)
        return client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]),
        )

    resp = ai_research._with_rotation(
        _generate, models=ai_research._models(DEEP_MODEL, ["gemini-2.5-flash"]))
    data = _extract_json(resp.text or "")

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
    data["sources"] = sources[:8]
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

"""Agent: transkrypcja dzwieku z YouTube -> analiza spolki.

Uzupelnia research_deep (ktory bierze tylko gotowe napisy). Tutaj, gdy film NIE
ma napisow, pobieramy audio (yt-dlp + ffmpeg), transkrybujemy przez Gemini
(model multimodalny obsluguje audio) i wyciagamy informacje o spolce.

Backend STT: Gemini audio (google-genai) — uzywa istniejacych kluczy + rotacji
(ai_research._with_rotation). Whisper lokalny odpada na Streamlit Cloud (RAM/CPU).

UWAGA (ToS): pobieranie audio z YouTube jest w szarej strefie regulaminu YT i bywa
blokowane z IP chmurowych. Dlatego DOMYSLNIE probujemy napisow (lzejsze, w tym
auto-ASR); audio-STT to fallback tylko na wyrazne zadanie uzytkownika.
Wyniki cache'owane w data/ytt_<video_id>.json.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import ai_research
import config
import research_deep

MAX_MINUTES = 30          # dluzsze filmy pomijamy (limit audio/tokenow)
TRANSCRIPT_CHARS = 12000
STT_MODEL = os.environ.get("STT_MODEL", os.environ.get("DEEP_MODEL", "gemini-flash-latest"))


def available() -> bool:
    return ai_research.available()


def _proxy() -> str | None:
    """Opcjonalne proxy (residential) dla obejscia blokady IP YouTube na chmurze."""
    return os.environ.get("YT_PROXY") or None


def _is_block(msg: str) -> bool:
    m = str(msg).lower()
    return any(s in m for s in ("403", "forbidden", "sign in", "blocked",
                                "not a bot", "unable to download"))


_BLOCK_HINT = (
    "YouTube blokuje IP serwera (typowe na Streamlit Cloud). Rozwiazania: "
    "uruchom aplikacje LOKALNIE (streamlit run app.py) albo ustaw YT_PROXY "
    "(residential proxy) w Secrets. Napisy i deep research nadal dzialaja."
)


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
    """Filmy o spolce z ostatnich miesiecy (reuse research_deep.yt_research)."""
    yt = research_deep.yt_research(name, ticker, market)
    return yt.get("videos", [])


# ----------------------------------------------------- audio -> tekst ---

def download_audio(video_id: str) -> tuple[str, float]:
    """Pobiera audio filmu do temp (mono, niski bitrate). Zwraca (sciezka, minuty).

    Rzuca RuntimeError przy zbyt dlugim filmie, braku ffmpeg lub blokadzie YT.
    """
    from yt_dlp import YoutubeDL

    tmpdir = tempfile.mkdtemp(prefix="ytaudio_")
    out = os.path.join(tmpdir, "%(id)s.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "retries": 3,
        # rozne klienty YouTube jako fallback (czasem omija czesc blokad 403)
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
        "postprocessors": [{"key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3", "preferredquality": "48"}],
        "postprocessor_args": ["-ac", "1", "-ar", "16000"],  # mono 16 kHz
    }
    if _proxy():
        opts["proxy"] = _proxy()
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            dur = (info.get("duration") or 0) / 60.0
            if dur > MAX_MINUTES:
                raise RuntimeError(
                    f"Film trwa {dur:.0f} min (limit {MAX_MINUTES} min) — pomijam "
                    "transkrypcje audio, by nie przekroczyc limitow.")
            ydl.download([url])
    except RuntimeError:
        raise
    except Exception as e:
        if _is_block(e):
            raise RuntimeError(_BLOCK_HINT)
        raise RuntimeError(f"Nie udalo sie pobrac audio (brak ffmpeg?): {e}")
    path = os.path.join(tmpdir, f"{video_id}.mp3")
    if not os.path.exists(path):
        raise RuntimeError("Audio nie zostalo zapisane (prawdopodobnie brak ffmpeg).")
    return path, dur


def transcribe_audio(path: str) -> str:
    """Transkrybuje plik audio przez Gemini (audio input) z rotacja kluczy."""
    from google import genai
    from google.genai import types

    with open(path, "rb") as f:
        audio_bytes = f.read()

    def _do(key: str, model: str) -> str:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents=[
                "Dokonaj wiernej transkrypcji mowy z tego nagrania (jezyk polski "
                "lub angielski). Zwroc sam tekst transkrypcji, bez komentarzy.",
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3"),
            ],
        )
        return (resp.text or "").strip()

    # audio wspieraja modele Flash (bez Lite)
    models = ai_research._models(STT_MODEL, ["gemini-2.5-flash"])
    return ai_research._with_rotation(_do, models=models)[:TRANSCRIPT_CHARS]


def get_transcript(video_id: str, allow_audio: bool = True) -> dict:
    """Zwraca {text, source}. source: 'napisy' albo 'audio-STT'.

    Najpierw probuje napisow (tanio), potem — jesli allow_audio — audio-STT.
    """
    caps = research_deep._yt_transcript(video_id)
    if caps and len(caps) > 200:
        return {"text": caps[:TRANSCRIPT_CHARS], "source": "napisy"}
    if not allow_audio:
        raise RuntimeError("Film nie ma napisow (transkrypcja audio wylaczona).")
    path, _dur = download_audio(video_id)
    try:
        text = transcribe_audio(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if len(text) < 50:
        raise RuntimeError("Transkrypcja audio zwrocila pusty tekst.")
    return {"text": text, "source": "audio-STT"}


# ----------------------------------------------------- analiza ---

SYSTEM = ("Jestes analitykiem inwestycyjnym. Na podstawie transkrypcji filmu "
          "wyciagasz to, co dotyczy KONKRETNEJ spolki. Ignorujesz dygresje "
          "i tresci reklamowe. Piszesz po polsku.")


def analyze(transcript: str, name: str, ticker: str) -> dict:
    prompt = f"""Transkrypcja filmu o spolce {name} ({ticker}). Wyciagnij wnioski
dotyczace TEJ spolki i zwroc WYLACZNIE JSON:
{{
  "key_points": ["<najwazniejsze tezy o spolce, 3-6 pkt>"],
  "claims_about_company": ["<konkretne stwierdzenia/fakty padajace w filmie>"],
  "sentiment": <int -100..100 wobec spolki>,
  "thesis": "<teza inwestycyjna autora, 1-2 zdania, lub 'brak'>",
  "risks": ["<wymienione ryzyka, jesli sa>"],
  "speaker_stance": "<byk/niedzwiedz/neutralny>"
}}

TRANSKRYPCJA:
{transcript}"""
    return ai_research.complete_json(SYSTEM, prompt, max_tokens=2048)


def run(video: dict, name: str, ticker: str, allow_audio: bool = True,
        force: bool = False) -> dict:
    """Pelny przeplyw dla jednego filmu: transkrypt -> analiza, z cache."""
    vid = video["id"]
    if not force:
        cached = load_cached(vid)
        if cached:
            return cached
    tr = get_transcript(vid, allow_audio=allow_audio)
    data = analyze(tr["text"], name, ticker)
    data["video_id"] = vid
    data["title"] = video.get("title")
    data["channel"] = video.get("channel")
    data["date"] = video.get("date")
    data["url"] = f"https://www.youtube.com/watch?v={vid}"
    data["transcript_source"] = tr["source"]
    data["transcript_excerpt"] = tr["text"][:1500]
    data["analyzed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(_cache_path(vid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    vids = find_videos(config.NAMES.get(tk, tk), tk, config.market_of(tk))
    print(f"znaleziono {len(vids)} filmow")
    for v in vids[:5]:
        print(f"  {v['date']} {v['id']} {v['title'][:60]}")

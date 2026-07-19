"""Wlasne listy obserwacyjne (Moj portfel, Do kupienia...) z trwalym zapisem.

Backend zapisu:
  1. GitHub Gist (zalecany w chmurze) — wymaga env: GITHUB_TOKEN (PAT ze scope
     "gist") oraz GIST_ID (id prywatnego gista z plikiem watchlists.json).
     Dysk Streamlit Cloud jest ulotny, Gist przezywa restarty i deploye.
  2. Fallback lokalny: data/watchlists.json (dziala od reki na wlasnym komputerze).

Struktura danych: {"lists": {"Moj portfel": ["NVDA", "DNP.WA"], ...}}
"""
from __future__ import annotations

import json
import os

import requests

import config

GIST_FILE = "watchlists.json"
LOCAL_PATH = os.path.join(config.CACHE_DIR, "watchlists.json")
_API = "https://api.github.com/gists/{gist_id}"

# notes = wlasne notatki uzytkownika per spolka {ticker: tekst} (uzytek osobisty)
EMPTY = {"lists": {}, "notes": {}}


def _gist_conf() -> tuple[str, str] | None:
    token = os.environ.get("GITHUB_TOKEN")
    gist_id = os.environ.get("GIST_ID")
    if token and gist_id:
        return token, gist_id
    return None


def backend() -> str:
    return "gist" if _gist_conf() else "local"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"}


def load() -> dict:
    """Wczytuje listy z Gista (jesli skonfigurowany) albo z pliku lokalnego."""
    conf = _gist_conf()
    if conf:
        token, gist_id = conf
        try:
            r = requests.get(_API.format(gist_id=gist_id),
                             headers=_headers(token), timeout=15)
            r.raise_for_status()
            files = r.json().get("files", {})
            if GIST_FILE in files:
                content = files[GIST_FILE].get("content") or "{}"
                data = json.loads(content)
                if isinstance(data.get("lists"), dict):
                    return data
        except Exception:
            pass  # spadamy na lokalny fallback
    if os.path.exists(LOCAL_PATH):
        try:
            with open(LOCAL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("lists"), dict):
                return data
        except Exception:
            pass
    return json.loads(json.dumps(EMPTY))


def save(data: dict) -> str | None:
    """Zapisuje listy. Zwraca None przy sukcesie, tekst bledu przy problemie z Gistem."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    conf = _gist_conf()
    if not conf:
        return None
    token, gist_id = conf
    try:
        r = requests.patch(
            _API.format(gist_id=gist_id), headers=_headers(token),
            json={"files": {GIST_FILE: {
                "content": json.dumps(data, ensure_ascii=False, indent=2)}}},
            timeout=15,
        )
        r.raise_for_status()
        return None
    except Exception as e:
        return f"Zapis do Gista nie powiodl sie ({e}); listy zapisane tylko lokalnie."


# --------------------------------------------------- dowolny plik w Giscie ---
# Ten sam Gist trzyma tez inne male, trwale dane aplikacji (np. ceny docelowe
# PWPA). Dysk Streamlit Cloud jest ulotny, wiec bez tego kazdy redeploy
# kasowalby wyniki i kazalby liczyc je od nowa.

def load_file(name: str) -> dict | None:
    """Wczytuje <name>.json z Gista (fallback: data/<name>). None = brak."""
    conf = _gist_conf()
    if conf:
        token, gist_id = conf
        try:
            r = requests.get(_API.format(gist_id=gist_id),
                             headers=_headers(token), timeout=15)
            r.raise_for_status()
            files = r.json().get("files", {})
            if name in files:
                return json.loads(files[name].get("content") or "{}")
        except Exception:
            pass  # spadamy na lokalny fallback
    path = os.path.join(config.CACHE_DIR, name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_file(name: str, data: dict) -> str | None:
    """Zapisuje <name>.json lokalnie i (gdy skonfigurowany) do Gista.

    PATCH na Giscie dotyka tylko tego jednego pliku, wiec nie kasuje list.
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(os.path.join(config.CACHE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    conf = _gist_conf()
    if not conf:
        return None
    token, gist_id = conf
    try:
        r = requests.patch(
            _API.format(gist_id=gist_id), headers=_headers(token),
            json={"files": {name: {
                "content": json.dumps(data, ensure_ascii=False, indent=2)}}},
            timeout=20,
        )
        r.raise_for_status()
        return None
    except Exception as e:
        return f"Zapis {name} do Gista nie powiodl sie ({e}); zapisano lokalnie."


def all_listed_tickers(data: dict) -> set[str]:
    out: set[str] = set()
    for tickers in data.get("lists", {}).values():
        out.update(tickers)
    return out

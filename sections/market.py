"""Zakladka Rynek: deep research (sentyment, newsy, IR) + analiza wideo."""
from __future__ import annotations

import streamlit as st

import research_deep
import yt_transcribe
from charts.helpers import fmt_dt


def render(ticker: str, row: dict, label: str, yt_videos_fn) -> None:
    st.subheader(f"🔎 Deep research: sentyment rynku + YouTube + relacje inwestorskie — {label}")
    st.caption(f"Analiza ostatnich {research_deep.MONTHS_BACK} miesiecy: artykuly "
               "(Google Search), filmy z YouTube (tytuly + transkrypty, gdy dostepne) "
               "i raporty z dzialu IR spolki. Sentyment NIE wplywa na Wynik strategii. "
               "Trwa 1-3 min.")
    deep = research_deep.load_cached(ticker)
    if st.button("🔎 Uruchom deep research dla tej spolki",
                 disabled=not research_deep.available()):
        with st.spinner("Szukam filmow, artykulow i raportow IR..."):
            try:
                deep = research_deep.research(ticker, row.get("name", ticker),
                                              row.get("market", ""),
                                              row.get("website"), force=True)
            except Exception as e:
                st.error(f"Blad deep research: {e}")
    if not research_deep.available():
        st.caption("Wymaga GEMINI_API_KEY (grounding dziala tylko z Gemini).")
    if deep:
        s = deep.get("sentiment")
        dm1, dm2 = st.columns([1, 3])
        with dm1:
            if s is not None:
                st.metric("Sentyment rynku", f"{s:+d}", delta=int(s),
                          help="-100 skrajnie negatywny ... +100 skrajnie pozytywny")
            st.caption(f"Pewnosc: {deep.get('confidence', '—')}%")
        with dm2:
            st.info(deep.get("sentiment_summary", ""))
        if deep.get("key_news"):
            with st.expander(f"📰 Najwazniejsze newsy ({len(deep['key_news'])})",
                             expanded=True):
                for n in deep["key_news"]:
                    st.write(f"**{n.get('title', '')}** _{n.get('date', '')}_")
                    st.caption(n.get("takeaway", ""))
        if deep.get("youtube_findings"):
            with st.expander(f"▶️ YouTube ({len(deep['youtube_findings'])})"):
                if deep.get("yt_note"):
                    st.caption(f"ℹ️ {deep['yt_note']}")
                for v in deep["youtube_findings"]:
                    st.write(f"**{v.get('title', '')}** — {v.get('channel', '')} "
                             f"_{v.get('date', '')}_")
                    st.caption(v.get("takeaway", ""))
        if deep.get("ir_findings"):
            with st.expander("🏢 Relacje inwestorskie / raporty"):
                st.write(deep["ir_findings"])
        if deep.get("sources"):
            with st.expander(f"🔗 Zrodla ({len(deep['sources'])})"):
                for src in deep["sources"]:
                    st.markdown(f"- [{src.get('title', src['url'])}]({src['url']})")
        st.caption(f"🗓 Źródła: Google Search (grounding) + YouTube + strona IR · "
                   f"model: {deep.get('model')} · wygenerowano "
                   f"{fmt_dt(deep.get('researched_at'))}")
    else:
        st.caption("Brak deep researchu dla tej spolki. Uruchom przyciskiem powyzej.")

    st.divider()
    st.subheader(f"🎧 Analiza wideo (AI) — {label}")
    st.caption("Agent najpierw próbuje napisów; gdy ich brak, wysyła film do "
               "Gemini, który **ogląda/odsłuchuje go po stronie Google** "
               "(działa też z chmury — nasz serwer nie pobiera nic z YouTube).")
    _vn = yt_transcribe.videos_note()
    if _vn:
        st.caption(f"ℹ️ {_vn}")
    if not yt_transcribe.available():
        st.caption("Wymaga GEMINI_API_KEY.")
    else:
        vids = yt_videos_fn(ticker, row.get("name", ticker), row.get("market", ""))
        if not vids:
            st.caption("Nie znaleziono filmów o spółce z ostatnich 12 miesięcy"
                       + ("" if not _vn else
                          " — bez YOUTUBE_API_KEY wyszukiwanie z serwera "
                          "zwykle nie działa."))
        else:
            def _vid_label(v):
                mins = f" · {v['minutes']:.0f} min" if v.get("minutes") else ""
                views = (f" · {v['views']:,} wyśw.".replace(",", " ")
                         if v.get("views") else "")
                return (f"{v.get('date', '')} · {str(v.get('title', ''))[:60]} "
                        f"— {v.get('channel', '')}{mins}{views}")
            labels = {v["id"]: _vid_label(v) for v in vids}
            vid = st.selectbox(f"Film ({len(vids)} znalezionych, 12 mies.)",
                               [v["id"] for v in vids],
                               format_func=lambda i: labels.get(i, i),
                               key=f"ytt_sel_{ticker}")
            video = next(v for v in vids if v["id"] == vid)
            res = yt_transcribe.load_cached(vid)
            if st.button("🎧 Przeanalizuj film", key=f"ytt_btn_{ticker}"):
                with st.spinner("Analizuję film (napisy albo odsłuch przez "
                                "Gemini — do ~2 min)..."):
                    try:
                        res = yt_transcribe.run(video, row.get("name", ticker),
                                                ticker, force=True)
                    except Exception as e:
                        st.error(f"Nie udalo sie: {e}")
            if res:
                st.markdown(f"**[{res.get('title', 'film')}]({res.get('url')})** — "
                            f"źródło transkryptu: *{res.get('transcript_source')}*")
                sc = res.get("sentiment")
                if sc is not None:
                    st.metric("Sentyment autora wobec spółki", f"{sc:+d}")
                if res.get("thesis") and res["thesis"].lower() != "brak":
                    st.info(res["thesis"])
                if res.get("key_points"):
                    st.markdown("**Kluczowe tezy:**")
                    for p in res["key_points"]:
                        st.markdown(f"- {p}")
                if res.get("risks"):
                    st.markdown("**Ryzyka wg autora:**")
                    for p in res["risks"]:
                        st.markdown(f"- {p}")
                with st.expander("Fragment transkryptu"):
                    st.write(res.get("transcript_excerpt", ""))
                st.caption(f"🗓 Źródło: YouTube (transkrypt: "
                           f"{res.get('transcript_source', '—')}) · "
                           f"postawa: {res.get('speaker_stance', '—')} · "
                           f"przeanalizowano {fmt_dt(res.get('analyzed_at'))}")

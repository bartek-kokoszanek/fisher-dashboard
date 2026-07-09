"""8 strategii selekcji inspirowanych znanymi inwestorami.

Kazda strategia = inne rozlozenie wag na tych samych, mierzalnych metrykach
(fisher_score.SCORERS) + wlasny prompt dla researchu AI. Suma wag = 100.

UCZCIWA ADNOTACJA: to edukacyjne PRZYBLIZENIA filozofii, nie prawdziwe
algorytmy tych inwestorow. Szczegolnie Simons (quant/HFT na wzorcach cenowych)
i Soros (makro/refleksywnosc) sa nieodtwarzalne z danych fundamentalnych —
ich profile to swiadome uproszczenia (momentum / sentyment + jakosc).

Metryki: revenue_cagr, revenue_growth_yoy, gross_margin, operating_margin,
margin_trend, rnd_intensity, roe, fcf_margin, low_dilution, low_leverage,
value_pe (niskie C/Z), momentum (zwrot 6-mies.).
"""
from __future__ import annotations

_BASE_SYSTEM = (
    "Jestes analitykiem inwestycyjnym oceniajacym JAKOSCIOWE aspekty spolki, "
    "ktorych nie widac w liczbach. Badz konkretny, ostrozny i szczery co do "
    "niepewnosci. Jesli czegos nie wiesz, obniz confidence. {persona}"
)

GURUS = {
    "fisher": {
        "name": "Philip Fisher",
        "desc": "Wybitne spolki wzrostowe trzymane latami: sprzedaz, R&D, marze, jakosc zarzadu.",
        "weights": {
            "revenue_cagr": 18, "revenue_growth_yoy": 10, "gross_margin": 8,
            "operating_margin": 12, "margin_trend": 10, "rnd_intensity": 12,
            "roe": 12, "fcf_margin": 10, "low_dilution": 4, "low_leverage": 4,
        },
        "persona": ("Stosujesz metode Philipa Fishera z 'Common Stocks and Uncommon "
                    "Profits': 15 punktow, nacisk na trwaly wzrost sprzedazy, kulture "
                    "R&D, marze i uczciwosc zarzadu."),
    },
    "lynch": {
        "name": "Peter Lynch",
        "desc": "Wzrost w rozsadnej cenie (GARP): dynamiczny wzrost, ale bez przeplacania za C/Z.",
        "weights": {
            "revenue_cagr": 20, "revenue_growth_yoy": 15, "value_pe": 20,
            "operating_margin": 10, "roe": 10, "fcf_margin": 10,
            "low_leverage": 10, "low_dilution": 5,
        },
        "persona": ("Stosujesz podejscie Petera Lyncha z 'One Up on Wall Street': "
                    "wzrost za rozsadna cene (GARP), proste zrozumiale biznesy, "
                    "kategorie spolek (stalwarts, fast growers), sila bilansu."),
    },
    "burry": {
        "name": "Michael Burry",
        "desc": "Gleboka wartosc kontrarianska: tanio wg C/Z i FCF, twardy bilans, marginal bezpieczenstwa.",
        "weights": {
            "value_pe": 30, "fcf_margin": 25, "low_leverage": 20,
            "roe": 10, "operating_margin": 10, "low_dilution": 5,
        },
        "persona": ("Stosujesz kontrarianskie deep value Michaela Burry'ego: "
                    "szukasz niedowartosciowania wzgledem przeplywow pienieznych, "
                    "marginesu bezpieczenstwa i sytuacji, ktorych rynek unika. "
                    "Jestes sceptyczny wobec modnych narracji i baniek."),
    },
    "buffett": {
        "name": "Warren Buffett",
        "desc": "Swietne biznesy z fosa w uczciwej cenie: wysokie ROE, stabilne marze, malo dlugu.",
        "weights": {
            "roe": 25, "operating_margin": 15, "gross_margin": 10,
            "fcf_margin": 15, "margin_trend": 5, "revenue_cagr": 10,
            "low_leverage": 10, "value_pe": 5, "low_dilution": 5,
        },
        "persona": ("Stosujesz filozofie Warrena Buffetta: trwala przewaga "
                    "konkurencyjna (fosa), wysokie ROE bez dzwigni, przewidywalne "
                    "zyski, uczciwy i racjonalny zarzad, cena ponizej wartosci "
                    "wewnetrznej."),
    },
    "dalio": {
        "name": "Ray Dalio",
        "desc": "Odpornosc i stabilnosc: niski dlug, stabilne marze i gotowka na kazda pogode.",
        "weights": {
            "low_leverage": 25, "fcf_margin": 20, "operating_margin": 15,
            "margin_trend": 10, "roe": 10, "revenue_cagr": 10,
            "value_pe": 5, "low_dilution": 5,
        },
        "persona": ("Stosujesz myslenie Raya Dalio (All Weather / Principles): "
                    "odpornosc na rozne scenariusze makro, niski lewar, "
                    "przewidywalnosc przeplywow, dywersyfikacja ryzyk."),
    },
    "simons": {
        "name": "James Simons",
        "desc": "PRZYBLIZENIE quant: momentum ceny + dyscyplina liczb (prawdziwy Renaissance to HFT na wzorcach).",
        "weights": {
            "momentum": 40, "revenue_growth_yoy": 15, "roe": 10,
            "fcf_margin": 10, "operating_margin": 10, "value_pe": 10,
            "low_leverage": 5,
        },
        "persona": ("Oceniasz jak analityk quant: licza sie tylko mierzalne sygnaly "
                    "i statystyka, zero narracji. Zaznacz w podsumowaniu, ze "
                    "prawdziwa metoda Renaissance (wzorce cenowe, HFT) jest "
                    "nieodtwarzalna z fundamentow — to uproszczenie."),
    },
    "ackman": {
        "name": "Bill Ackman",
        "desc": "Skoncentrowane pozycje w prostych, przewidywalnych biznesach wysokiej jakosci z silnym FCF.",
        "weights": {
            "fcf_margin": 25, "operating_margin": 15, "roe": 15,
            "gross_margin": 10, "revenue_cagr": 10, "margin_trend": 10,
            "value_pe": 10, "low_leverage": 5,
        },
        "persona": ("Stosujesz podejscie Billa Ackmana (Pershing Square): "
                    "nieliczne, skoncentrowane pozycje w prostych, przewidywalnych, "
                    "generujacych gotowke biznesach z barierami wejscia; aktywizm "
                    "gdy zarzad niszczy wartosc."),
    },
    "soros": {
        "name": "George Soros",
        "desc": "PRZYBLIZENIE makro: momentum + nastroje rynku (refleksywnosc); fundamenty w tle.",
        "weights": {
            "momentum": 30, "revenue_growth_yoy": 15, "margin_trend": 15,
            "operating_margin": 10, "fcf_margin": 10, "value_pe": 10,
            "low_leverage": 10,
        },
        "persona": ("Myslisz jak George Soros: refleksywnosc — ceny ksztaltuja "
                    "fundamenty, a fundamenty ceny; szukasz punktow zwrotnych "
                    "nastrojow i nierownowag. Zaznacz w podsumowaniu, ze prawdziwa "
                    "metoda Sorosa (makro, waluty, timing) wykracza poza analize "
                    "pojedynczej spolki — to uproszczenie."),
    },
}

DEFAULT = "fisher"


def get(key: str) -> dict:
    return GURUS.get(key, GURUS[DEFAULT])


def system_prompt(key: str) -> str:
    return _BASE_SYSTEM.format(persona=get(key)["persona"])


def options() -> list[str]:
    return list(GURUS.keys())

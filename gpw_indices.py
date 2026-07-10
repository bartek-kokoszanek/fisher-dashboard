"""Sklady indeksow GPW (tickery Yahoo .WA) + segment Nasdaq-AI.

Sklady WIG20/mWIG40/sWIG80 wygenerowane z biznesradar.pl (2026-07-09).
Sklady zmieniaja sie kwartalnie - odswiezenie: patrz README.
"""

WIG20 = {
    "ALE.WA",
    "ALR.WA",
    "BDX.WA",
    "CDR.WA",
    "DNP.WA",
    "EBP.WA",
    "KGH.WA",
    "KRU.WA",
    "KTY.WA",
    "LPP.WA",
    "MBK.WA",
    "MDV.WA",
    "PCO.WA",
    "PEO.WA",
    "PGE.WA",
    "PKN.WA",
    "PKO.WA",
    "PZU.WA",
    "TPE.WA",
    "ZAB.WA",
}

MWIG40 = {
    "ABE.WA",
    "ACP.WA",
    "APR.WA",
    "ASB.WA",
    "ASE.WA",
    "ATT.WA",
    "BFT.WA",
    "BHW.WA",
    "BNP.WA",
    "CAR.WA",
    "CBF.WA",
    "CPS.WA",
    "CRI.WA",
    "DIA.WA",
    "DOM.WA",
    "DVL.WA",
    "EAT.WA",
    "ENA.WA",
    "GPP.WA",
    "GPW.WA",
    "ING.WA",
    "JSW.WA",
    "LBW.WA",
    "MBR.WA",
    "MIL.WA",
    "MRB.WA",
    "MUR.WA",
    "NEU.WA",
    "NWG.WA",
    "OPL.WA",
    "PEP.WA",
    "PXM.WA",
    "RBW.WA",
    "SNT.WA",
    "TEN.WA",
    "TXT.WA",
    "VOX.WA",
    "VRC.WA",
    "WPL.WA",
    "XTB.WA",
}

SWIG80 = {
    "11B.WA",
    "1AT.WA",
    "ABS.WA",
    "ACG.WA",
    "AGO.WA",
    "ALL.WA",
    "AMB.WA",
    "AMC.WA",
    "ANR.WA",
    "APT.WA",
    "ARH.WA",
    "ARL.WA",
    "AST.WA",
    "ATC.WA",
    "ATR.WA",
    "BCX.WA",
    "BIO.WA",
    "BLO.WA",
    "BMC.WA",
    "BOS.WA",
    "BRS.WA",
    "CIG.WA",
    "CLN.WA",
    "CMP.WA",
    "COG.WA",
    "CRJ.WA",
    "CRQ.WA",
    "CTX.WA",
    "DAD.WA",
    "DAT.WA",
    "DCR.WA",
    "DIG.WA",
    "ECH.WA",
    "ELT.WA",
    "ENT.WA",
    "ERB.WA",
    "EUR.WA",
    "FRO.WA",
    "FTE.WA",
    "GRX.WA",
    "HUG.WA",
    "ICE.WA",
    "KGN.WA",
    "LWB.WA",
    "MCI.WA",
    "MDG.WA",
    "MLG.WA",
    "MNC.WA",
    "MRC.WA",
    "MSZ.WA",
    "OND.WA",
    "OPN.WA",
    "PCR.WA",
    "PLW.WA",
    "QRS.WA",
    "RVU.WA",
    "SCP.WA",
    "SCW.WA",
    "SEL.WA",
    "SGN.WA",
    "SHO.WA",
    "SKA.WA",
    "SLV.WA",
    "SNK.WA",
    "STP.WA",
    "STX.WA",
    "SVE.WA",
    "TAR.WA",
    "TOA.WA",
    "TOR.WA",
    "UNI.WA",
    "UNT.WA",
    "VGO.WA",
    "VOT.WA",
    "VRG.WA",
    "WLT.WA",
    "WTN.WA",
    "WWL.WA",
    "ZEP.WA",
    "ZRE.WA",
}


# Spolki AI notowane na Nasdaq (kuratorowane recznie: producenci ukladow,
# infrastruktura AI, oprogramowanie/platformy AI). Edytuj swobodnie.
NASDAQ_AI = {
    "NVDA", "AMD", "AVGO", "INTC", "QCOM", "MU", "MRVL", "ARM", "SMCI",
    "AMAT", "LRCX", "KLAC", "ASML", "SNPS", "CDNS",
    "MSFT", "GOOGL", "META", "AMZN", "PLTR", "CRWD", "PANW", "NOW",
    "ADBE", "INTU", "TEAM", "DDOG", "SNOW", "MDB", "AI", "SOUN", "PATH",
    "TSLA", "ISRG", "ABNB", "APP",
}

from sp500_tickers import SP500 as _SP500_NAMES
SP500 = set(_SP500_NAMES)

SEGMENTS_GPW = ("WIG20", "mWIG40", "sWIG80", "WIG-pozostale")
SEGMENTS_US = ("Nasdaq", "Nasdaq-AI", "S&P500")
ALL_SEGMENTS = SEGMENTS_US + SEGMENTS_GPW


def segments_of(ticker: str) -> set[str]:
    """Zbior segmentow spolki (moze nalezec do kilku, np. Nasdaq + Nasdaq-AI + S&P500)."""
    if ticker.endswith(".WA"):
        if ticker in WIG20:
            return {"WIG20"}
        if ticker in MWIG40:
            return {"mWIG40"}
        if ticker in SWIG80:
            return {"sWIG80"}
        return {"WIG-pozostale"}
    segs = {"Nasdaq"}
    if ticker in NASDAQ_AI:
        segs.add("Nasdaq-AI")
    if ticker in SP500:
        segs.add("S&P500")
    return segs


def segment_label(ticker: str) -> str:
    """Etykieta do tabeli (najbardziej szczegolowy segment)."""
    segs = segments_of(ticker)
    for pref in ("Nasdaq-AI", "S&P500"):
        if pref in segs:
            return pref
    return next(iter(segs))

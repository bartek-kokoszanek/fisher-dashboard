"""Szybki smoke test scoringu na probce spolek."""
import data_fetch
import fisher_score

TICKERS = ["AAPL", "NVDA", "MSFT", "CDR.WA", "DNP.WA", "PKO.WA", "PZU.WA", "TXT.WA"]

for t in TICKERS:
    r = data_fetch.get(t)
    if "error" in r:
        print(f"{t:10} ERROR: {r['error']}")
        continue
    res = fisher_score.compute_score(r)
    tgt = r.get("target_mean")
    ups = r.get("target_upside")
    print(f"{t:10} score={str(res['score']):>5}  cov={res['coverage']:>3.0f}%  "
          f"cena={r.get('price')!s:>8}  cel={tgt!s:>8}  "
          f"do_celu={'—' if ups is None else f'{ups*100:+.1f}%':>7}  "
          f"rekom={r.get('analyst_count')!s:>4}  {fisher_score.verdict(res['score'])}")

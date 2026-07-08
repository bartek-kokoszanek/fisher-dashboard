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
    print(f"{t:10} score={str(res['score']):>5}  cov={res['coverage']:>3.0f}%  "
          f"fin={r.get('is_financial')!s:>5}  {fisher_score.verdict(res['score'])}")

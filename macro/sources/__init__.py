"""Source registry: name -> fetch(ind, start) -> pd.Series."""
from . import bis, boe, ecb, files, fred, nyfed, sec, tiingo, treasury

SOURCES = {
    "fred": fred.fetch,
    "treasury": treasury.fetch,
    "nyfed": nyfed.fetch,
    "ecb": ecb.fetch,
    "boe": boe.fetch,
    "bis": bis.fetch,
    "sec": sec.fetch,
    "tiingo": tiingo.fetch,
    "files": files.fetch,
}

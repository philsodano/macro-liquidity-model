"""Live check: every fetchable registry series has data in the store (run after `python -m macro refresh`)."""
import pytest

from macro.registry import load_registry
from macro.store import Store

pytestmark = pytest.mark.network


def test_every_fetchable_series_has_data():
    store, reg = Store(), load_registry()
    missing, blocked = [], []
    for sid, ind in reg.items():
        if ind.source == "derived" or ind.unavailable:
            continue
        if store.read(sid).empty:
            err = store.meta(sid).get("last_error") or ""
            (blocked if ind.source == "tiingo" and "403" in err else missing).append(f"{sid}: {err[:80]}")
    if blocked:
        print(f"\n{len(blocked)} Tiingo series blocked by an invalid API key (credential issue, not code)")
    assert not missing, "\n".join(missing)

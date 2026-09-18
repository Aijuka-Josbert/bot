"""Strategy registry. Add new strategies here to make them discoverable by name."""
from .bollinger import BollingerBreakout
from .rsi_mean_reversion import RsiMeanReversion
from .sma_crossover import SmaCrossover

REGISTRY: dict[str, type] = {
    "sma_crossover": SmaCrossover,
    "rsi_mean_reversion": RsiMeanReversion,
    "bollinger_breakout": BollingerBreakout,
}


def make(name: str, params: dict | None = None):
    if name not in REGISTRY:
        raise KeyError(f"Unknown strategy: {name!r}. Known: {sorted(REGISTRY)}")
    return REGISTRY[name](params)